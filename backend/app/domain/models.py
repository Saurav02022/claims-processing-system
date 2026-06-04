"""Domain data structures for adjudication.

Frozen dataclasses with Decimal money. These are the *inputs* and *outputs* of
the adjudication engine — deliberately decoupled from the database rows so the
business rules can be specified and tested without persistence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.enums import LineItemDecision

ZERO = Decimal("0")


@dataclass(frozen=True)
class Plan:
    """Benefit design. The annual deductible is plan-level (across services)."""

    annual_deductible_amount: Decimal = ZERO


@dataclass(frozen=True)
class CoverageRule:
    """Coverage rule for one service type under a plan."""

    service_type_code: str
    is_covered: bool = True
    annual_limit_amount: Decimal | None = None          # None = unlimited
    annual_visit_limit: int | None = None               # None = unlimited
    copay_amount: Decimal = ZERO                         # fixed, per line
    coinsurance_rate: Decimal = ZERO                     # 0..1, member share
    review_threshold_amount: Decimal | None = None       # billed above -> review
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class PolicyContext:
    """Policy facts needed to decide coverage validity for a service date."""

    benefit_period_start: date
    benefit_period_end: date
    status: str = "active"                              # active | terminated


@dataclass(frozen=True)
class AccumulatorState:
    """Usage already consumed in the benefit period, before this line item.

    `amount_used` / `visits_used` are scoped to the line item's service type;
    `deductible_met_amount` is the policy-wide deductible consumed so far.
    """

    deductible_met_amount: Decimal = ZERO
    amount_used: Decimal = ZERO
    visits_used: int = 0


@dataclass(frozen=True)
class LineItemInput:
    """A single billed service submitted on a claim."""

    service_type_code: str
    service_date: date
    billed_amount: Decimal
    quantity: int = 1


@dataclass(frozen=True)
class Reason:
    """A single explanation attached to an adjudication."""

    code: str
    message: str | None = None
    detail: dict | None = None


@dataclass(frozen=True)
class LineItemAdjudication:
    """Result of adjudicating one line item: the money breakdown + outcome.

    Invariant the engine must uphold:
        payable_amount == covered_amount - deductible_applied
                          - copay_amount - coinsurance_amount   (floored at 0)
    """

    decision: LineItemDecision
    covered_amount: Decimal
    deductible_applied: Decimal
    copay_amount: Decimal
    coinsurance_amount: Decimal
    payable_amount: Decimal
    reasons: tuple[Reason, ...] = field(default_factory=tuple)

    def reason_codes(self) -> set[str]:
        return {r.code for r in self.reasons}
