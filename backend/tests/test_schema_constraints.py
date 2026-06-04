"""Data-integrity tests for the database schema (integration).

These verify the migration's guarantees actually hold in Postgres: CHECK
constraints, the "exactly one current adjudication per line" partial unique
index, accumulator uniqueness for the policy-wide deductible row, status
domains, and FK cascade. They are the safety net behind the domain layer.

They require a live database and are SKIPPED unless DATABASE_URL is set:

    DATABASE_URL=postgresql+psycopg://... pytest tests/test_schema_constraints.py

Every test runs inside a transaction that is rolled back, so nothing persists.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="integration test: set DATABASE_URL to run",
)

pytest.importorskip("sqlalchemy")
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402


@pytest.fixture
def conn():
    """A connection inside a transaction that is always rolled back."""
    from app.db import get_engine

    engine = get_engine()
    with engine.connect() as connection:
        trans = connection.begin()
        try:
            yield connection
        finally:
            trans.rollback()


def _seed_claim(conn) -> dict:
    """Insert a minimal valid plan->member->policy->claim->line_item graph."""
    service_type_id = conn.execute(
        text("select id from service_type where code = 'PHYSIO'")
    ).scalar_one()
    plan_id = conn.execute(
        text("insert into plan (name) values ('Test Plan') returning id")
    ).scalar_one()
    member_id = conn.execute(
        text("insert into member (full_name) values ('Test Member') returning id")
    ).scalar_one()
    policy_id = conn.execute(
        text(
            """
            insert into policy (policy_number, member_id, plan_id,
                                benefit_period_start, benefit_period_end)
            values ('TEST-POL', :m, :p, '2026-01-01', '2026-12-31')
            returning id
            """
        ),
        {"m": member_id, "p": plan_id},
    ).scalar_one()
    claim_id = conn.execute(
        text(
            "insert into claim (claim_number, policy_id) "
            "values ('TEST-CLM', :pol) returning id"
        ),
        {"pol": policy_id},
    ).scalar_one()
    line_item_id = conn.execute(
        text(
            """
            insert into claim_line_item
                (claim_id, line_number, service_type_id, service_date, billed_amount)
            values (:c, 1, :st, '2026-03-01', 100)
            returning id
            """
        ),
        {"c": claim_id, "st": service_type_id},
    ).scalar_one()
    return {
        "service_type_id": service_type_id,
        "plan_id": plan_id,
        "policy_id": policy_id,
        "claim_id": claim_id,
        "line_item_id": line_item_id,
    }


def test_coinsurance_rate_above_one_is_rejected(conn):
    ids = _seed_claim(conn)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text(
                    "insert into coverage_rule (plan_id, service_type_id, coinsurance_rate) "
                    "values (:p, :st, 1.5)"
                ),
                {"p": ids["plan_id"], "st": ids["service_type_id"]},
            )


def test_invalid_claim_status_is_rejected(conn):
    ids = _seed_claim(conn)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text("update claim set status = 'bogus' where id = :c"),
                {"c": ids["claim_id"]},
            )


def test_negative_billed_amount_is_rejected(conn):
    ids = _seed_claim(conn)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text(
                    "insert into claim_line_item "
                    "(claim_id, line_number, service_type_id, service_date, billed_amount) "
                    "values (:c, 2, :st, '2026-03-01', -10)"
                ),
                {"c": ids["claim_id"], "st": ids["service_type_id"]},
            )


def test_only_one_current_adjudication_per_line_item(conn):
    ids = _seed_claim(conn)
    conn.execute(
        text(
            "insert into adjudication (line_item_id, sequence, is_current, decision) "
            "values (:li, 1, true, 'approved')"
        ),
        {"li": ids["line_item_id"]},
    )
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text(
                    "insert into adjudication (line_item_id, sequence, is_current, decision) "
                    "values (:li, 2, true, 'denied')"
                ),
                {"li": ids["line_item_id"]},
            )


def test_one_policy_wide_accumulator_row_per_period(conn):
    ids = _seed_claim(conn)
    conn.execute(
        text(
            "insert into accumulator (policy_id, service_type_id, period_start, period_end) "
            "values (:p, null, '2026-01-01', '2026-12-31')"
        ),
        {"p": ids["policy_id"]},
    )
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text(
                    "insert into accumulator (policy_id, service_type_id, period_start, period_end) "
                    "values (:p, null, '2026-01-01', '2026-12-31')"
                ),
                {"p": ids["policy_id"]},
            )


def test_deleting_claim_cascades_to_line_items(conn):
    ids = _seed_claim(conn)
    conn.execute(text("delete from claim where id = :c"), {"c": ids["claim_id"]})
    remaining = conn.execute(
        text("select count(*) from claim_line_item where claim_id = :c"),
        {"c": ids["claim_id"]},
    ).scalar_one()
    assert remaining == 0
