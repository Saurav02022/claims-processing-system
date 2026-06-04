"""Shared builders for adjudication domain tests.

These helpers create domain inputs with sensible defaults so each test only
states the fields relevant to the rule it exercises. All money is Decimal.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.domain.models import (
    AccumulatorState,
    CoverageRule,
    LineItemInput,
    Plan,
    PolicyContext,
)

# A service date that falls inside the default benefit period below.
SERVICE_DATE = date(2026, 3, 1)
SERVICE_CODE = "PHYSIO"


def D(value: str | int) -> Decimal:
    """Concise Decimal constructor for readable test arithmetic."""
    return Decimal(str(value))


@pytest.fixture
def plan() -> Plan:
    """Plan with no deductible by default (cost-sharing tests override this)."""
    return Plan(annual_deductible_amount=D(0))


@pytest.fixture
def policy() -> PolicyContext:
    """Active policy whose benefit period covers SERVICE_DATE."""
    return PolicyContext(
        benefit_period_start=date(2026, 1, 1),
        benefit_period_end=date(2026, 12, 31),
        status="active",
    )


@pytest.fixture
def empty_accumulator() -> AccumulatorState:
    """No usage consumed yet."""
    return AccumulatorState()


def make_rule(**overrides) -> CoverageRule:
    """A fully-covered rule with no cost sharing or limits unless overridden."""
    defaults = dict(
        service_type_code=SERVICE_CODE,
        is_covered=True,
        annual_limit_amount=None,
        annual_visit_limit=None,
        copay_amount=D(0),
        coinsurance_rate=D(0),
        review_threshold_amount=None,
    )
    defaults.update(overrides)
    return CoverageRule(**defaults)


def make_line(billed: str | int = 100, **overrides) -> LineItemInput:
    defaults = dict(
        service_type_code=SERVICE_CODE,
        service_date=SERVICE_DATE,
        billed_amount=D(billed),
        quantity=1,
    )
    defaults.update(overrides)
    return LineItemInput(**defaults)
