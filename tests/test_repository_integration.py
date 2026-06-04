"""End-to-end integration tests for the REAL SupabaseClaimRepository.

The offline `test_api.py` suite runs the engine + service against an in-memory
fake repository, so the *column mapping* and *write/read I/O* of
`SupabaseClaimRepository` (save_claim, get_claim, save_accumulators,
load_policy_context, create_dispute, apply_resolution, apply_review, ...) is
exercised here against live Postgres — the one path the fake cannot cover.

Like `test_schema_constraints.py`, these require a live Supabase project and are
SKIPPED unless SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are configured. There is
no transaction rollback over PostgREST, so each test seeds its own isolated
plan/policy graph and a fixture teardown deletes it (claims cascade to line
items / adjudications / reasons / history / disputes; the policy cascades to
accumulators). Test data uses a random suffix to avoid collisions.
"""
import uuid
from decimal import Decimal

import pytest

pytest.importorskip("supabase")

from app import claims_service as svc
from app.claims_repository import SupabaseClaimRepository
from app.schemas import ClaimIn, DisputeIn


def _have_creds() -> bool:
    try:
        from app.config import get_settings

        s = get_settings()
        return bool(s.supabase_url and s.supabase_service_role_key)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _have_creds(),
    reason="integration test: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to run",
)


class _Tracker:
    """Inserts rows (and registers service-created claims) so teardown deletes them."""

    def __init__(self, client):
        self.client = client
        self._rows: list[tuple[str, str]] = []

    def add(self, table: str, row_id: str) -> None:
        self._rows.append((table, row_id))

    def insert(self, table: str, payload: dict) -> dict:
        row = self.client.table(table).insert(payload).execute().data[0]
        self.add(table, row["id"])
        return row

    def cleanup(self) -> None:
        # Reverse insertion order: claims first (cascade), then policy (cascade
        # accumulators), then member, coverage rules, and plan.
        for table, row_id in reversed(self._rows):
            try:
                self.client.table(table).delete().eq("id", row_id).execute()
            except Exception:
                pass


@pytest.fixture
def tracker():
    from app.db import get_supabase

    t = _Tracker(get_supabase())
    try:
        yield t
    finally:
        t.cleanup()


def _seed_policy(tracker: _Tracker, *, deductible=0, rules) -> dict:
    """Seed plan + coverage rules + member + policy. `rules` = [(code, fields), ...]."""
    sfx = uuid.uuid4().hex[:8]
    codes = [code for code, _ in rules]
    st = {r["code"]: r["id"]
          for r in tracker.client.table("service_type").select("id,code").in_("code", codes).execute().data}
    plan = tracker.insert("plan", {"name": f"IT Plan {sfx}", "annual_deductible_amount": deductible})
    rule_ids = {}
    for code, fields in rules:
        row = tracker.insert("coverage_rule", {
            "plan_id": plan["id"], "service_type_id": st[code], "effective_from": "2026-01-01", **fields,
        })
        rule_ids[code] = row["id"]
    member = tracker.insert("member", {"full_name": "IT Member"})
    policy = tracker.insert("policy", {
        "policy_number": f"IT-POL-{sfx}", "member_id": member["id"], "plan_id": plan["id"],
        "benefit_period_start": "2026-01-01", "benefit_period_end": "2026-12-31",
    })
    return {"policy_id": policy["id"], "plan_id": plan["id"], "rule_ids": rule_ids}


def _submit(repo, tracker, policy_id, line_items):
    out = svc.submit_claim(repo, ClaimIn.model_validate({"policy_id": policy_id, "line_items": line_items}))
    tracker.add("claim", str(out.claim_id))
    return out


def _adjudications(client, line_id):
    return (client.table("adjudication").select("sequence,is_current,decision,triggered_by")
            .eq("line_item_id", line_id).order("sequence").execute().data)


def test_submit_persists_and_reads_back(tracker):
    repo = SupabaseClaimRepository(tracker.client)
    ids = _seed_policy(tracker, rules=[
        ("PHYSIO", {"copay_amount": 20}),
        ("OPTICAL", {"review_threshold_amount": 500}),
    ])
    out = _submit(repo, tracker, ids["policy_id"], [
        {"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 100},
        {"service_type_code": "OPTICAL", "service_date": "2026-03-02", "billed_amount": 600},
    ])
    assert out.status == "under_review"

    # Read back through a fresh repo call to verify the persisted column mapping.
    fetched = svc.get_claim(repo, str(out.claim_id))
    by_code = {li.service_type_code: li for li in fetched.line_items}
    assert by_code["PHYSIO"].decision == "approved"
    assert by_code["PHYSIO"].payable_amount == Decimal("80.00")          # 100 - 20 copay
    assert "COPAY_APPLIED" in [r.code for r in by_code["PHYSIO"].reasons]
    assert by_code["OPTICAL"].decision == "needs_review"
    assert "OVER_REVIEW_THRESHOLD" in [r.code for r in by_code["OPTICAL"].reasons]
    # A needs_review line's payable is provisionally included in the claim total
    # (80 PHYSIO + 600 OPTICAL); review-deny later removes it (see deny test).
    assert fetched.total_payable_amount == Decimal("680.00")


def test_accumulators_persist_across_claims(tracker):
    repo = SupabaseClaimRepository(tracker.client)
    ids = _seed_policy(tracker, deductible=200, rules=[("PHYSIO", {})])
    lines = [{"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 100}]

    first = _submit(repo, tracker, ids["policy_id"], lines)
    assert first.line_items[0].payable_amount == Decimal("0.00")         # 100 -> deductible

    second = _submit(repo, tracker, ids["policy_id"],
                     [{"service_type_code": "PHYSIO", "service_date": "2026-04-01", "billed_amount": 100}])
    assert second.line_items[0].payable_amount == Decimal("0.00")        # remaining 100 -> deductible

    third = _submit(repo, tracker, ids["policy_id"],
                    [{"service_type_code": "PHYSIO", "service_date": "2026-05-01", "billed_amount": 100}])
    assert third.line_items[0].payable_amount == Decimal("100.00")       # deductible met -> full pay


def test_dispute_resolution_overturns_and_versions(tracker):
    repo = SupabaseClaimRepository(tracker.client)
    ids = _seed_policy(tracker, rules=[("DENTAL", {"is_covered": False})])
    out = _submit(repo, tracker, ids["policy_id"],
                  [{"service_type_code": "DENTAL", "service_date": "2026-03-01", "billed_amount": 100}])
    assert out.status == "denied"
    line = out.line_items[0]

    dispute = svc.open_dispute(repo, str(out.claim_id),
                               DisputeIn.model_validate({"reason": "Dental is covered", "line_item_id": str(line.id)}))
    assert svc.get_claim(repo, str(out.claim_id)).status == "disputed"

    # Correct coverage out-of-band, then resolve -> re-adjudication overturns.
    tracker.client.table("coverage_rule").update({"is_covered": True}).eq("id", ids["rule_ids"]["DENTAL"]).execute()
    resolved = svc.resolve_dispute(repo, str(dispute.id))
    assert resolved.status == "approved"
    assert resolved.line_items[0].payable_amount == Decimal("100.00")

    adjs = _adjudications(tracker.client, str(line.id))
    assert [a["triggered_by"] for a in adjs] == ["submission", "dispute"]
    assert adjs[-1]["is_current"] is True and adjs[-1]["decision"] == "approved"
    assert adjs[0]["is_current"] is False                                # prior version preserved
    d = repo.get_dispute(str(dispute.id))
    assert d["status"] == "resolved" and d["resolution_outcome"] == "overturned"


def test_manual_review_approve_persists_and_versions(tracker):
    repo = SupabaseClaimRepository(tracker.client)
    ids = _seed_policy(tracker, rules=[("OPTICAL", {"review_threshold_amount": 500})])
    out = _submit(repo, tracker, ids["policy_id"],
                  [{"service_type_code": "OPTICAL", "service_date": "2026-03-01", "billed_amount": 600}])
    assert out.status == "under_review"
    line = out.line_items[0]

    reviewed = svc.complete_review(repo, str(out.claim_id), str(line.id), "approved", note="valid")
    assert reviewed.status == "approved"
    assert reviewed.line_items[0].payable_amount == Decimal("600.00")    # breakdown preserved
    assert "MANUAL_REVIEW_APPROVED" in [r.code for r in reviewed.line_items[0].reasons]

    adjs = _adjudications(tracker.client, str(line.id))
    assert [a["triggered_by"] for a in adjs] == ["submission", "review"]
    assert adjs[-1]["is_current"] is True and adjs[-1]["decision"] == "approved"

    hist = (tracker.client.table("claim_status_history").select("from_status,to_status,changed_by")
            .eq("claim_id", str(out.claim_id)).order("changed_at").execute().data)
    assert hist[-1]["from_status"] == "under_review"
    assert hist[-1]["to_status"] == "approved" and hist[-1]["changed_by"] == "reviewer"


def test_manual_review_deny_reconciles_accumulator(tracker):
    repo = SupabaseClaimRepository(tracker.client)
    ids = _seed_policy(tracker, rules=[("DENTAL", {"annual_limit_amount": 1000, "review_threshold_amount": 50})])
    out = _submit(repo, tracker, ids["policy_id"],
                  [{"service_type_code": "DENTAL", "service_date": "2026-03-01", "billed_amount": 100}])
    assert out.status == "under_review"                                  # 100 > review threshold 50
    line = out.line_items[0]

    # A needs_review line counts against usage at submission...
    before = repo.load_policy_context(ids["policy_id"])
    assert before.usage.get("DENTAL", (Decimal("0"), 0))[0] == Decimal("100.00")

    # ...and a denial on review must remove that contribution.
    reviewed = svc.complete_review(repo, str(out.claim_id), str(line.id), "denied")
    assert reviewed.status == "denied"
    assert reviewed.line_items[0].payable_amount == Decimal("0.00")
    assert "MANUAL_REVIEW_DENIED" in [r.code for r in reviewed.line_items[0].reasons]

    after = repo.load_policy_context(ids["policy_id"])
    assert after.usage.get("DENTAL", (Decimal("0"), 0)) == (Decimal("0.00"), 0)
