"""Cost-sharing math: deductible, copay, coinsurance, and their ordering.

Specifies docs/domain-model.md §6 steps 4-6 and 9. The engine applies, in order:
deductible -> copay -> coinsurance on the remainder, then
payable = covered - deductible - copay - coinsurance (floored at 0).
"""
from app.domain.adjudication import adjudicate_line_item
from app.domain.enums import LineItemDecision, ReasonCode
from tests.conftest import D, make_line, make_rule
from app.domain.models import Plan


def test_full_deductible_consumes_entire_billed_amount(policy, empty_accumulator):
    # Plan deductible 500, none met; a 200 service is fully applied to deductible.
    result = adjudicate_line_item(
        line=make_line(billed=200),
        rule=make_rule(),
        plan=Plan(annual_deductible_amount=D(500)),
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED  # covered, but member owes deductible
    assert result.deductible_applied == D(200)
    assert result.payable_amount == D(0)
    assert ReasonCode.DEDUCTIBLE_APPLIED in result.reason_codes()


def test_partial_remaining_deductible_then_pays_rest(policy):
    # Deductible 500 with 400 already met -> only 100 remaining applies.
    from app.domain.models import AccumulatorState

    result = adjudicate_line_item(
        line=make_line(billed=300),
        rule=make_rule(),
        plan=Plan(annual_deductible_amount=D(500)),
        accumulator=AccumulatorState(deductible_met_amount=D(400)),
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.deductible_applied == D(100)
    assert result.payable_amount == D(200)


def test_fixed_copay_is_subtracted(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(copay_amount=D(20)),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.copay_amount == D(20)
    assert result.payable_amount == D(80)
    assert ReasonCode.COPAY_APPLIED in result.reason_codes()


def test_coinsurance_is_member_percentage(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(coinsurance_rate=D("0.20")),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.coinsurance_amount == D(20)
    assert result.payable_amount == D(80)
    assert ReasonCode.COINSURANCE_APPLIED in result.reason_codes()


def test_cost_sharing_applies_in_order_deductible_copay_then_coinsurance(policy):
    # billed 100, deductible fully met, copay 20, coinsurance 10% on remainder (80).
    # remainder after copay = 80; coinsurance = 8; payable = 100 - 0 - 20 - 8 = 72.
    from app.domain.models import AccumulatorState

    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(copay_amount=D(20), coinsurance_rate=D("0.10")),
        plan=Plan(annual_deductible_amount=D(500)),
        accumulator=AccumulatorState(deductible_met_amount=D(500)),  # deductible already met
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.deductible_applied == D(0)
    assert result.copay_amount == D(20)
    assert result.coinsurance_amount == D(8)
    assert result.payable_amount == D(72)
