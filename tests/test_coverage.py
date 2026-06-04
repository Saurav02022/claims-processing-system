"""Coverage validity rules: when is a line item denied outright?

Specifies docs/domain-model.md §6 steps 1-2 (policy/date validity + coverage).
"""
from datetime import date

from app.domain.adjudication import adjudicate_line_item
from app.domain.enums import LineItemDecision, ReasonCode
from tests.conftest import D, make_line, make_rule


def test_no_matching_rule_is_denied_as_not_covered(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=None,  # no coverage rule for this service type
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.NOT_COVERED in result.reason_codes()
    assert result.payable_amount == D(0)


def test_rule_marked_not_covered_is_denied(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(is_covered=False),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.NOT_COVERED in result.reason_codes()
    assert result.payable_amount == D(0)


def test_terminated_policy_is_denied(plan, policy, empty_accumulator):
    terminated = type(policy)(
        benefit_period_start=policy.benefit_period_start,
        benefit_period_end=policy.benefit_period_end,
        status="terminated",
    )
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(),
        plan=plan,
        accumulator=empty_accumulator,
        policy=terminated,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.POLICY_INACTIVE in result.reason_codes()
    assert result.payable_amount == D(0)


def test_service_date_outside_benefit_period_is_denied(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=100, service_date=date(2025, 12, 31)),  # before period
        rule=make_rule(),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.SERVICE_DATE_OUT_OF_COVERAGE in result.reason_codes()
    assert result.payable_amount == D(0)


def test_fully_covered_service_is_approved_in_full(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(),  # covered, no cost sharing, no limits
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.covered_amount == D(100)
    assert result.payable_amount == D(100)
    assert result.deductible_applied == D(0)
    assert ReasonCode.COVERED_IN_FULL in result.reason_codes()
