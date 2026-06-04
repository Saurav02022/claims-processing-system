"""Adjudication engine — pure domain business logic.

Implements docs/domain-model.md §6 (line-item adjudication) and §10 (claim-level
roll-up). No database, network, or framework dependencies, so the rules can be
reasoned about and tested in isolation.

Conventions the rules rely on:
  * Money is rounded HALF_UP to 2 decimals (currency/billing standard).
  * The annual money limit caps the insurer-payable amount, applied AFTER cost
    sharing.
  * Precedence follows the documented step order: policy validity -> coverage ->
    deductible -> copay -> coinsurance -> limits -> review threshold.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import ClaimStatus, LineItemDecision, ReasonCode
from app.domain.models import (
    AccumulatorState,
    CoverageRule,
    LineItemAdjudication,
    LineItemInput,
    Plan,
    PolicyContext,
    Reason,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    """Round a monetary amount HALF_UP to cents."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _reason(code: ReasonCode, message: str) -> Reason:
    return Reason(code=code, message=message)


def _denied(code: ReasonCode, message: str) -> LineItemAdjudication:
    """A denial pays nothing; the money breakdown is zeroed."""
    zero = _money(_ZERO)
    return LineItemAdjudication(
        decision=LineItemDecision.DENIED,
        covered_amount=zero,
        deductible_applied=zero,
        copay_amount=zero,
        coinsurance_amount=zero,
        payable_amount=zero,
        reasons=(_reason(code, message),),
    )


def adjudicate_line_item(
    *,
    line: LineItemInput,
    rule: CoverageRule | None,
    plan: Plan,
    accumulator: AccumulatorState,
    policy: PolicyContext,
) -> LineItemAdjudication:
    """Adjudicate a single line item (see module docstring / domain-model §6)."""
    result = _adjudicate(line=line, rule=rule, plan=plan, accumulator=accumulator, policy=policy)
    # Dev-only trace: decision + reason codes only — never amounts or PHI.
    logger.debug("line adjudicated: %s %s", result.decision, [r.code for r in result.reasons])
    return result


def _adjudicate(
    *,
    line: LineItemInput,
    rule: CoverageRule | None,
    plan: Plan,
    accumulator: AccumulatorState,
    policy: PolicyContext,
) -> LineItemAdjudication:
    billed = line.billed_amount

    # 1. policy validity (checked before coverage)
    if policy.status != "active":
        return _denied(ReasonCode.POLICY_INACTIVE, "The policy was not active on the service date.")
    if not (policy.benefit_period_start <= line.service_date <= policy.benefit_period_end):
        return _denied(ReasonCode.SERVICE_DATE_OUT_OF_COVERAGE, "The service date is outside the coverage period.")

    # 2. coverage
    if rule is None or not rule.is_covered:
        return _denied(ReasonCode.NOT_COVERED, "This service is not covered under the policy.")

    # 3. covered amount
    covered = _money(billed)
    reasons: list[Reason] = []

    # 4. plan deductible — only what remains in the benefit period applies
    remaining_deductible = max(_ZERO, plan.annual_deductible_amount - accumulator.deductible_met_amount)
    deductible_applied = _money(min(remaining_deductible, covered))
    if deductible_applied > _ZERO:
        reasons.append(_reason(ReasonCode.DEDUCTIBLE_APPLIED, "Part of the amount was applied to the annual deductible."))
    after_deductible = covered - deductible_applied

    # 5. copay — capped at the remainder so payable can never go negative
    copay = _money(min(rule.copay_amount, after_deductible))
    if copay > _ZERO:
        reasons.append(_reason(ReasonCode.COPAY_APPLIED, "A fixed copay was applied."))
    after_copay = after_deductible - copay

    # 6. coinsurance — member's percentage of the remaining covered amount
    coinsurance = _money(rule.coinsurance_rate * after_copay)
    if coinsurance > _ZERO:
        reasons.append(_reason(ReasonCode.COINSURANCE_APPLIED, "Coinsurance was applied to the covered amount."))

    # 9. payable before limit capping
    payable = _money(max(_ZERO, covered - deductible_applied - copay - coinsurance))

    # 7. limits — deny when already exhausted, otherwise cap the payable
    if rule.annual_visit_limit is not None and accumulator.visits_used >= rule.annual_visit_limit:
        return _denied(ReasonCode.VISIT_LIMIT_EXCEEDED, "The annual visit limit for this service has been reached.")
    if rule.annual_limit_amount is not None:
        remaining_limit = max(_ZERO, rule.annual_limit_amount - accumulator.amount_used)
        if remaining_limit <= _ZERO:
            return _denied(ReasonCode.ANNUAL_LIMIT_EXCEEDED, "The annual coverage limit for this service has been reached.")
        if payable > remaining_limit:
            payable = _money(remaining_limit)
            reasons.append(_reason(ReasonCode.LIMIT_PARTIALLY_APPLIED, "Payable was reduced by the remaining annual limit."))

    # 8. manual-review threshold (after limits, per documented order)
    decision = LineItemDecision.APPROVED
    if rule.review_threshold_amount is not None and billed > rule.review_threshold_amount:
        decision = LineItemDecision.NEEDS_REVIEW
        reasons.append(_reason(ReasonCode.OVER_REVIEW_THRESHOLD, "The billed amount exceeds the manual-review threshold."))

    # an approval with no reductions is covered in full
    if decision is LineItemDecision.APPROVED and not reasons:
        reasons.append(_reason(ReasonCode.COVERED_IN_FULL, "The service was covered in full."))

    return LineItemAdjudication(
        decision=decision,
        covered_amount=covered,
        deductible_applied=deductible_applied,
        copay_amount=copay,
        coinsurance_amount=coinsurance,
        payable_amount=payable,
        reasons=tuple(reasons),
    )


def roll_up_claim_status(decisions: Sequence[LineItemDecision]) -> ClaimStatus:
    """Derive the claim-level status from its line-item decisions (domain-model §10)."""
    if not decisions:
        return ClaimStatus.SUBMITTED
    unique = set(decisions)
    if LineItemDecision.NEEDS_REVIEW in unique:
        return ClaimStatus.UNDER_REVIEW
    if unique == {LineItemDecision.APPROVED}:
        return ClaimStatus.APPROVED
    if unique == {LineItemDecision.DENIED}:
        return ClaimStatus.DENIED
    return ClaimStatus.PARTIALLY_APPROVED


def claim_total_payable(results: Sequence[LineItemAdjudication]) -> Decimal:
    """Sum of payable_amount across the current line-item adjudications."""
    return _money(sum((r.payable_amount for r in results), _ZERO))
