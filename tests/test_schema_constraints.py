"""Data-integrity tests for the database schema (integration, via Supabase REST).

These verify the migration's guarantees actually hold in Postgres: CHECK
constraints, the "exactly one current adjudication per line" partial unique
index, the policy-wide accumulator uniqueness, and FK cascade.

They require a live Supabase project and are SKIPPED unless SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY are configured (via .env or the environment).

There is no transaction rollback over PostgREST, so each test cleans up the rows
it created in a fixture teardown (children cascade from the claim; remaining
parents are deleted explicitly). Test data uses a random suffix to avoid
colliding with leftovers from a previous interrupted run.
"""
import uuid

import pytest

pytest.importorskip("supabase")
try:
    from postgrest.exceptions import APIError
except Exception:  # pragma: no cover - import shape varies by version
    APIError = Exception


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


class Seeder:
    """Inserts rows and remembers them so teardown can delete them."""

    def __init__(self, client):
        self.client = client
        self._created: list[tuple[str, str]] = []

    def insert(self, table: str, payload: dict) -> dict:
        row = self.client.table(table).insert(payload).execute().data[0]
        self._created.append((table, row["id"]))
        return row

    def forget(self, table: str, row_id: str) -> None:
        # Stop tracking a row we deleted ourselves (e.g. cascade tests).
        self._created = [(t, i) for (t, i) in self._created if not (t == table and i == row_id)]

    def cleanup(self) -> None:
        for table, row_id in reversed(self._created):
            try:
                self.client.table(table).delete().eq("id", row_id).execute()
            except Exception:
                pass


@pytest.fixture
def seeder():
    from app.db import get_supabase

    s = Seeder(get_supabase())
    try:
        yield s
    finally:
        s.cleanup()


def _service_type_id(client) -> str:
    return client.table("service_type").select("id").eq("code", "PHYSIO").single().execute().data["id"]


def _seed_claim(seeder: Seeder) -> dict:
    """Insert a minimal valid plan->member->policy->claim->line_item graph."""
    sfx = uuid.uuid4().hex[:8]
    service_type_id = _service_type_id(seeder.client)
    plan = seeder.insert("plan", {"name": f"Test Plan {sfx}"})
    member = seeder.insert("member", {"full_name": "Test Member"})
    policy = seeder.insert(
        "policy",
        {
            "policy_number": f"TEST-POL-{sfx}",
            "member_id": member["id"],
            "plan_id": plan["id"],
            "benefit_period_start": "2026-01-01",
            "benefit_period_end": "2026-12-31",
        },
    )
    claim = seeder.insert(
        "claim", {"claim_number": f"TEST-CLM-{sfx}", "policy_id": policy["id"]}
    )
    line_item = seeder.insert(
        "claim_line_item",
        {
            "claim_id": claim["id"],
            "line_number": 1,
            "service_type_id": service_type_id,
            "service_date": "2026-03-01",
            "billed_amount": 100,
        },
    )
    return {
        "service_type_id": service_type_id,
        "plan_id": plan["id"],
        "policy_id": policy["id"],
        "claim_id": claim["id"],
        "line_item_id": line_item["id"],
    }


def test_coinsurance_rate_above_one_is_rejected(seeder):
    sfx = uuid.uuid4().hex[:8]
    plan = seeder.insert("plan", {"name": f"Test Plan {sfx}"})
    with pytest.raises(APIError):
        seeder.client.table("coverage_rule").insert(
            {
                "plan_id": plan["id"],
                "service_type_id": _service_type_id(seeder.client),
                "coinsurance_rate": 1.5,  # violates CHECK (0..1)
            }
        ).execute()


def test_invalid_claim_status_is_rejected(seeder):
    ids = _seed_claim(seeder)
    with pytest.raises(APIError):
        seeder.client.table("claim").update({"status": "bogus"}).eq("id", ids["claim_id"]).execute()


def test_only_one_current_adjudication_per_line_item(seeder):
    ids = _seed_claim(seeder)
    seeder.insert(
        "adjudication",
        {"line_item_id": ids["line_item_id"], "sequence": 1, "is_current": True, "decision": "approved"},
    )
    with pytest.raises(APIError):
        seeder.client.table("adjudication").insert(
            {"line_item_id": ids["line_item_id"], "sequence": 2, "is_current": True, "decision": "denied"}
        ).execute()


def test_one_policy_wide_accumulator_row_per_period(seeder):
    ids = _seed_claim(seeder)
    base = {
        "policy_id": ids["policy_id"],
        "service_type_id": None,  # policy-wide (deductible) row
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
    }
    seeder.insert("accumulator", base)
    with pytest.raises(APIError):
        seeder.client.table("accumulator").insert(base).execute()


def test_deleting_claim_cascades_to_line_items(seeder):
    ids = _seed_claim(seeder)
    seeder.client.table("claim").delete().eq("id", ids["claim_id"]).execute()
    seeder.forget("claim", ids["claim_id"])
    seeder.forget("claim_line_item", ids["line_item_id"])  # cascaded away

    remaining = (
        seeder.client.table("claim_line_item")
        .select("id")
        .eq("claim_id", ids["claim_id"])
        .execute()
        .data
    )
    assert remaining == []
