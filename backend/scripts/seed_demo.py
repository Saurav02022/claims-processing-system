"""Seed one demo plan + coverage rules + member + policy for the walkthrough.

There is no enrollment/management API by design (out of scope), so this script
provides the data needed to exercise POST /claims against a live database.
Idempotent: re-running reuses existing rows.

Run from the backend/ directory (requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY):

    python -m scripts.seed_demo
"""
from app.db import get_supabase

PLAN_NAME = "Demo Health Plan"
MEMBER_REF = "DEMO-MEMBER-001"
POLICY_NUMBER = "DEMO-POL-001"

# (service_type_code, coverage-rule fields) — chosen to show varied outcomes.
RULES = [
    ("PHYSIO", {"copay_amount": 20, "annual_visit_limit": 10}),
    ("DENTAL", {"annual_limit_amount": 1000, "coinsurance_rate": 0.20}),
    ("OPTICAL", {"review_threshold_amount": 500}),
    ("MENTAL_HEALTH", {"is_covered": False}),
]


def _get_or_create(client, table, match, payload):
    query = client.table(table).select("*")
    for key, value in match.items():
        query = query.eq(key, value)
    existing = query.limit(1).execute().data
    if existing:
        return existing[0]
    return client.table(table).insert({**match, **payload}).execute().data[0]


def main():
    c = get_supabase()
    plan = _get_or_create(c, "plan", {"name": PLAN_NAME}, {"annual_deductible_amount": 200})
    service_types = {r["code"]: r["id"] for r in c.table("service_type").select("id,code").execute().data}

    for code, fields in RULES:
        service_type_id = service_types.get(code)
        if service_type_id is None:
            continue
        _get_or_create(
            c, "coverage_rule",
            {"plan_id": plan["id"], "service_type_id": service_type_id, "effective_from": "2026-01-01"},
            fields,
        )

    member = _get_or_create(c, "member", {"external_member_ref": MEMBER_REF}, {"full_name": "Demo Member"})
    policy = _get_or_create(
        c, "policy", {"policy_number": POLICY_NUMBER},
        {
            "member_id": member["id"],
            "plan_id": plan["id"],
            "benefit_period_start": "2026-01-01",
            "benefit_period_end": "2026-12-31",
        },
    )

    print("Demo data ready.")
    print(f"  policy_id     = {policy['id']}")
    print(f"  policy_number = {POLICY_NUMBER}")
    print("Try: POST /claims with that policy_id and line items for "
          "PHYSIO / DENTAL / OPTICAL / MENTAL_HEALTH.")


if __name__ == "__main__":
    main()
