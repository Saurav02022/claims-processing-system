"""Annual money limits and visit limits, including partial application.

Specifies docs/domain-model.md §6 step 7 and the "limit exhaustion" /
"partial approval" edge cases called out in the assignment.
"""
from app.domain.adjudication import adjudicate_line_item
from app.domain.enums import LineItemDecision, ReasonCode
from app.domain.models import AccumulatorState
from tests.conftest import D, make_line, make_rule


def test_annual_money_limit_already_exhausted_is_denied(plan, policy):
    result = adjudicate_line_item(
        line=make_line(billed=200),
        rule=make_rule(annual_limit_amount=D(1000)),
        plan=plan,
        accumulator=AccumulatorState(amount_used=D(1000)),  # nothing left
        policy=policy,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.ANNUAL_LIMIT_EXCEEDED in result.reason_codes()
    assert result.payable_amount == D(0)


def test_annual_money_limit_partially_remaining_caps_payable(plan, policy):
    # Limit 1000, used 900 -> only 100 remains; a 200 service pays 100.
    result = adjudicate_line_item(
        line=make_line(billed=200),
        rule=make_rule(annual_limit_amount=D(1000)),
        plan=plan,
        accumulator=AccumulatorState(amount_used=D(900)),
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.payable_amount == D(100)
    assert ReasonCode.LIMIT_PARTIALLY_APPLIED in result.reason_codes()


def test_visit_limit_already_exhausted_is_denied(plan, policy):
    result = adjudicate_line_item(
        line=make_line(billed=50),
        rule=make_rule(annual_visit_limit=10),
        plan=plan,
        accumulator=AccumulatorState(visits_used=10),  # all visits used
        policy=policy,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.VISIT_LIMIT_EXCEEDED in result.reason_codes()
    assert result.payable_amount == D(0)


def test_visit_limit_with_remaining_visits_is_approved(plan, policy):
    result = adjudicate_line_item(
        line=make_line(billed=50),
        rule=make_rule(annual_visit_limit=10),
        plan=plan,
        accumulator=AccumulatorState(visits_used=5),  # visits remain
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.payable_amount == D(50)
