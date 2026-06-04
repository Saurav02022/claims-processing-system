"""Adjudication engine — INTERFACE ONLY (not yet implemented).

This module declares the contract the domain-rule tests bind to. The bodies
raise NotImplementedError on purpose: the tests are written first (red), and the
engine logic is implemented in a later step. The intended algorithm is specified
in docs/domain-model.md (section 6, "Coverage rule modeling") and is summarised
in each function's docstring below.
"""
from __future__ import annotations

from collections.abc import Sequence

from app.domain.enums import ClaimStatus, LineItemDecision
from app.domain.models import (
    AccumulatorState,
    CoverageRule,
    LineItemAdjudication,
    LineItemInput,
    Plan,
    PolicyContext,
)


def adjudicate_line_item(
    *,
    line: LineItemInput,
    rule: CoverageRule | None,
    plan: Plan,
    accumulator: AccumulatorState,
    policy: PolicyContext,
) -> LineItemAdjudication:
    """Adjudicate a single line item.

    Algorithm (see docs/domain-model.md §6):
      1. Validate policy/service date; deny POLICY_INACTIVE /
         SERVICE_DATE_OUT_OF_COVERAGE when invalid.
      2. If no rule or rule.is_covered is False -> deny NOT_COVERED.
      3. covered_amount = billed_amount.
      4. Apply remaining plan deductible -> deductible_applied.
      5. Apply copay -> copay_amount.
      6. Apply coinsurance on the remainder -> coinsurance_amount.
      7. Cap against remaining annual money/visit limits; deny when already
         exhausted (ANNUAL_LIMIT_EXCEEDED / VISIT_LIMIT_EXCEEDED) or reduce and
         flag LIMIT_PARTIALLY_APPLIED.
      8. If billed_amount exceeds review_threshold_amount -> NEEDS_REVIEW.
      9. payable_amount = covered - deductible - copay - coinsurance (>= 0).
    """
    raise NotImplementedError


def roll_up_claim_status(
    decisions: Sequence[LineItemDecision],
) -> ClaimStatus:
    """Derive the claim-level status from its line-item decisions.

    - no decisions                              -> SUBMITTED
    - any NEEDS_REVIEW                          -> UNDER_REVIEW
    - all APPROVED                              -> APPROVED
    - all DENIED                                -> DENIED
    - otherwise (mix of approved and denied)    -> PARTIALLY_APPROVED
    """
    raise NotImplementedError


def claim_total_payable(
    results: Sequence[LineItemAdjudication],
) -> "Decimal":  # noqa: F821 - Decimal imported lazily by implementation
    """Sum of payable_amount across the current line-item adjudications."""
    raise NotImplementedError
