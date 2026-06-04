"""API tests for the claims + dispute endpoints, run fully offline.

A fake in-memory repository is injected via FastAPI's dependency override, so the
real adjudication engine runs but no database is touched.
"""
from datetime import date
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient

from app.claims_repository import PolicyContextData
from app.domain.models import CoverageRule, Plan, PolicyContext
from app.main import app, get_repository

POLICY_ID = "11111111-1111-1111-1111-111111111111"


def _dec(value) -> Decimal:
    return Decimal(str(value))


def make_context(deductible="0", rules=None) -> PolicyContextData:
    rules = rules if rules is not None else {
        "PHYSIO": CoverageRule(service_type_code="PHYSIO"),          # fully covered
        "DENTAL": CoverageRule(service_type_code="DENTAL", is_covered=False),  # not covered
    }
    return PolicyContextData(
        policy_id=POLICY_ID,
        plan=Plan(annual_deductible_amount=Decimal(deductible)),
        policy=PolicyContext(benefit_period_start=date(2026, 1, 1), benefit_period_end=date(2026, 12, 31)),
        rules=rules,
        service_type_ids={"PHYSIO": "st-physio", "DENTAL": "st-dental", "OPTICAL": "st-optical"},
    )


class FakeRepo:
    def __init__(self, context):
        self.context = context
        self._claims: dict = {}
        self._disputes: dict = {}
        self.saved_accumulators = None

    def load_policy_context(self, policy_id):
        return self.context if str(policy_id) == POLICY_ID else None

    def save_claim(self, saved):
        claim_id = str(uuid.uuid4())
        for line in saved.lines:
            line.line_id, line.current_sequence = str(uuid.uuid4()), 1
        self._claims[claim_id] = saved
        return claim_id

    def save_accumulators(self, policy_id, ps, pe, deductible_met, usage, service_type_ids):
        self.saved_accumulators = {"deductible_met": deductible_met, "usage": dict(usage)}

    def get_claim(self, claim_id):
        return self._claims.get(str(claim_id))

    def create_dispute(self, claim_id, line_item_id, reason):
        if str(claim_id) not in self._claims:
            return None
        did = str(uuid.uuid4())
        self._disputes[did] = {"id": did, "claim_id": str(claim_id), "line_item_id": line_item_id,
                               "reason": reason, "status": "open", "resolution_outcome": None}
        self._claims[str(claim_id)].status = "disputed"
        return self._disputes[did]

    def get_dispute(self, dispute_id):
        return self._disputes.get(str(dispute_id))

    def apply_resolution(self, *, dispute_id, claim_id, line_id, prev_sequence, new_line,
                         new_claim_status, new_total, outcome, deductible_met, usage, **_):
        claim = self._claims[str(claim_id)]
        for line in claim.lines:
            if line.line_id == line_id:
                line.decision, line.reasons = new_line.decision, new_line.reasons
                line.covered_amount, line.payable_amount = new_line.covered_amount, new_line.payable_amount
                line.deductible_applied = new_line.deductible_applied
                line.copay_amount, line.coinsurance_amount = new_line.copay_amount, new_line.coinsurance_amount
                line.current_sequence = prev_sequence + 1
        claim.status, claim.total_payable_amount = new_claim_status, new_total
        self._disputes[str(dispute_id)].update(status="resolved", resolution_outcome=outcome)
        self.saved_accumulators = {"deductible_met": deductible_met, "usage": dict(usage)}


@pytest.fixture
def make_client():
    def _make(context=None):
        repo = FakeRepo(context or make_context())
        app.dependency_overrides[get_repository] = lambda: repo
        return TestClient(app), repo
    yield _make
    app.dependency_overrides.clear()


def _submit(client, lines):
    return client.post("/claims", json={"policy_id": POLICY_ID, "line_items": lines})


def test_fully_covered_claim_is_approved(make_client):
    client, _ = make_client()
    body = _submit(client, [{"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 100}]).json()
    assert body["status"] == "approved"
    assert _dec(body["total_payable_amount"]) == _dec(100)
    assert "COVERED_IN_FULL" in [r["code"] for r in body["line_items"][0]["reasons"]]


def test_mixed_lines_produce_partial_approval(make_client):
    client, _ = make_client()
    body = _submit(client, [
        {"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 100},
        {"service_type_code": "DENTAL", "service_date": "2026-03-01", "billed_amount": 50},
    ]).json()
    assert body["status"] == "partially_approved"
    assert _dec(body["total_payable_amount"]) == _dec(100)
    assert {li["service_type_code"]: li["decision"] for li in body["line_items"]} == \
        {"PHYSIO": "approved", "DENTAL": "denied"}


def test_plan_deductible_threads_across_line_items(make_client):
    client, _ = make_client(make_context(deductible="150"))
    body = _submit(client, [
        {"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 100},
        {"service_type_code": "PHYSIO", "service_date": "2026-04-01", "billed_amount": 100},
    ]).json()
    assert [_dec(li["payable_amount"]) for li in body["line_items"]] == [_dec(0), _dec(50)]


def test_accumulators_are_written_back(make_client):
    client, repo = make_client(make_context(deductible="200"))
    _submit(client, [{"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 250}])
    assert repo.saved_accumulators["deductible_met"] == _dec(200)
    assert repo.saved_accumulators["usage"]["PHYSIO"] == (_dec(50), 1)


def test_unknown_policy_returns_404(make_client):
    client, _ = make_client()
    resp = client.post("/claims", json={"policy_id": "22222222-2222-2222-2222-222222222222",
                                        "line_items": [{"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 100}]})
    assert resp.status_code == 404


def test_unknown_service_type_returns_422(make_client):
    client, _ = make_client()
    assert _submit(client, [{"service_type_code": "MRI", "service_date": "2026-03-01", "billed_amount": 100}]).status_code == 422


def test_empty_line_items_is_rejected(make_client):
    client, _ = make_client()
    assert client.post("/claims", json={"policy_id": POLICY_ID, "line_items": []}).status_code == 422


def test_billed_amount_over_column_limit_is_rejected(make_client):
    # Above NUMERIC(12,2) range -> rejected at validation (422), never a 500 on insert.
    client, _ = make_client()
    assert _submit(client, [{"service_type_code": "PHYSIO", "service_date": "2026-03-01",
                             "billed_amount": 999999999999}]).status_code == 422


def test_submit_then_get_returns_same_claim(make_client):
    client, _ = make_client()
    created = _submit(client, [{"service_type_code": "PHYSIO", "service_date": "2026-03-01", "billed_amount": 100}]).json()
    fetched = client.get(f"/claims/{created['claim_id']}")
    assert fetched.status_code == 200 and fetched.json()["claim_number"] == created["claim_number"]


def test_get_missing_claim_returns_404(make_client):
    client, _ = make_client()
    assert client.get(f"/claims/{uuid.uuid4()}").status_code == 404


# --- disputes -------------------------------------------------------------

def _submit_optical_denied(client):
    # OPTICAL has no coverage rule in the default context -> denied NOT_COVERED.
    return _submit(client, [{"service_type_code": "OPTICAL", "service_date": "2026-03-01", "billed_amount": 100}]).json()


def test_open_dispute_marks_claim_disputed(make_client):
    client, _ = make_client()
    claim = _submit_optical_denied(client)
    line_id = claim["line_items"][0]["id"]
    resp = client.post(f"/claims/{claim['claim_id']}/disputes", json={"reason": "Should be covered", "line_item_id": line_id})
    assert resp.status_code == 201 and resp.json()["status"] == "open"
    assert client.get(f"/claims/{claim['claim_id']}").json()["status"] == "disputed"


def test_open_dispute_on_foreign_line_is_422(make_client):
    client, _ = make_client()
    claim = _submit_optical_denied(client)
    resp = client.post(f"/claims/{claim['claim_id']}/disputes",
                       json={"reason": "x", "line_item_id": str(uuid.uuid4())})
    assert resp.status_code == 422


def test_resolve_dispute_overturns_when_rule_corrected(make_client):
    client, repo = make_client()
    claim = _submit_optical_denied(client)
    assert claim["line_items"][0]["decision"] == "denied"
    line_id = claim["line_items"][0]["id"]
    dispute = client.post(f"/claims/{claim['claim_id']}/disputes",
                          json={"reason": "Optical is covered", "line_item_id": line_id}).json()

    # Correct the coverage out-of-band, then resolve -> re-adjudication overturns.
    repo.context.rules["OPTICAL"] = CoverageRule(service_type_code="OPTICAL")
    resolved = client.post(f"/disputes/{dispute['id']}/resolve")
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "approved"
    assert _dec(body["line_items"][0]["payable_amount"]) == _dec(100)
    assert repo.get_dispute(dispute["id"])["resolution_outcome"] == "overturned"


def test_resolve_already_resolved_is_409(make_client):
    client, repo = make_client()
    claim = _submit_optical_denied(client)
    line_id = claim["line_items"][0]["id"]
    dispute = client.post(f"/claims/{claim['claim_id']}/disputes",
                          json={"reason": "x", "line_item_id": line_id}).json()
    client.post(f"/disputes/{dispute['id']}/resolve")
    assert client.post(f"/disputes/{dispute['id']}/resolve").status_code == 409


def test_resolve_unknown_dispute_is_404(make_client):
    client, _ = make_client()
    assert client.post(f"/disputes/{uuid.uuid4()}/resolve").status_code == 404
