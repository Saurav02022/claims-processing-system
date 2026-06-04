"""Manual-review threshold routing.

Specifies docs/domain-model.md §6 step 8: a billed amount above the rule's
review threshold routes the line item to NEEDS_REVIEW instead of auto-deciding.
"""
from app.domain.adjudication import adjudicate_line_item
from app.domain.enums import LineItemDecision, ReasonCode
from tests.conftest import D, make_line, make_rule


def test_billed_over_review_threshold_needs_review(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=5000),
        rule=make_rule(review_threshold_amount=D(1000)),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.NEEDS_REVIEW
    assert ReasonCode.OVER_REVIEW_THRESHOLD in result.reason_codes()


def test_billed_at_or_below_threshold_does_not_need_review(plan, policy, empty_accumulator):
    # Exactly at the threshold is not "over" -> normal approval.
    result = adjudicate_line_item(
        line=make_line(billed=1000),
        rule=make_rule(review_threshold_amount=D(1000)),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert ReasonCode.OVER_REVIEW_THRESHOLD not in result.reason_codes()
    assert result.payable_amount == D(1000)
