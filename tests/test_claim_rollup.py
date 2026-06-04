"""Claim-level status roll-up and total payable across line items.

Specifies docs/domain-model.md §10 (partial approvals): the claim status is
derived from its line-item decisions, and total payable sums the line payables.
"""
from app.domain.adjudication import claim_total_payable, roll_up_claim_status
from app.domain.enums import ClaimStatus, LineItemDecision
from app.domain.models import LineItemAdjudication, Reason
from tests.conftest import D


def _result(decision: LineItemDecision, payable) -> LineItemAdjudication:
    return LineItemAdjudication(
        decision=decision,
        covered_amount=D(payable),
        deductible_applied=D(0),
        copay_amount=D(0),
        coinsurance_amount=D(0),
        payable_amount=D(payable),
        reasons=(Reason(code="COVERED_IN_FULL"),),
    )


def test_no_lines_rolls_up_to_submitted():
    assert roll_up_claim_status([]) is ClaimStatus.SUBMITTED


def test_all_approved_rolls_up_to_approved():
    decisions = [LineItemDecision.APPROVED, LineItemDecision.APPROVED]
    assert roll_up_claim_status(decisions) is ClaimStatus.APPROVED


def test_all_denied_rolls_up_to_denied():
    decisions = [LineItemDecision.DENIED, LineItemDecision.DENIED]
    assert roll_up_claim_status(decisions) is ClaimStatus.DENIED


def test_mix_of_approved_and_denied_is_partially_approved():
    decisions = [LineItemDecision.APPROVED, LineItemDecision.DENIED]
    assert roll_up_claim_status(decisions) is ClaimStatus.PARTIALLY_APPROVED


def test_any_needs_review_forces_under_review():
    # Even with approvals and denials present, a review line holds the claim.
    decisions = [
        LineItemDecision.APPROVED,
        LineItemDecision.DENIED,
        LineItemDecision.NEEDS_REVIEW,
    ]
    assert roll_up_claim_status(decisions) is ClaimStatus.UNDER_REVIEW


def test_five_line_partial_approval_total_payable():
    # 3 approved (80 + 50 + 20), 1 denied (0), 1 needs_review (0) -> total 150.
    results = [
        _result(LineItemDecision.APPROVED, 80),
        _result(LineItemDecision.APPROVED, 50),
        _result(LineItemDecision.APPROVED, 20),
        _result(LineItemDecision.DENIED, 0),
        _result(LineItemDecision.NEEDS_REVIEW, 0),
    ]
    assert claim_total_payable(results) == D(150)
    assert roll_up_claim_status([r.decision for r in results]) is ClaimStatus.UNDER_REVIEW
