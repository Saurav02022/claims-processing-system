"""Edge cases, boundaries, and invariants for line-item adjudication.

These strengthen the happy-path suites with the cases where claims systems
actually break: monetary rounding, limit-vs-cost-sharing interaction, multiple
simultaneous explanations, exact boundaries, and rule precedence.

Documented assumptions (surface them rather than decide silently):
  * MONEY ROUNDING is HALF_UP to 2 decimals — the standard for currency/billing.
    If the engine adopts a different mode, update the two rounding tests below.
  * ANNUAL MONEY LIMIT caps the *insurer-payable* amount (consistent with the
    existing test_limits suite), so the cap is applied after cost sharing.
  * RULE PRECEDENCE follows the documented §6 step order: policy validity (1)
    before coverage (2) before cost sharing (3-6) before limits (7) before
    review threshold (8).
"""
from app.domain.adjudication import adjudicate_line_item
from app.domain.enums import LineItemDecision, ReasonCode
from app.domain.models import AccumulatorState, Plan
from tests.conftest import D, make_line, make_rule


# --------------------------------------------------------------------------
# Monetary rounding (HALF_UP to cents)
# --------------------------------------------------------------------------

def test_coinsurance_rounds_half_up_to_cents(plan, policy, empty_accumulator):
    # 0.10 * 99.99 = 9.999 -> 10.00 (round half up); payable 99.99 - 10.00 = 89.99
    result = adjudicate_line_item(
        line=make_line(billed="99.99"),
        rule=make_rule(coinsurance_rate=D("0.10")),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.coinsurance_amount == D("10.00")
    assert result.payable_amount == D("89.99")


def test_coinsurance_rounds_down_when_below_half_cent(plan, policy, empty_accumulator):
    # 0.10 * 10.02 = 1.002 -> 1.00; payable 10.02 - 1.00 = 9.02
    result = adjudicate_line_item(
        line=make_line(billed="10.02"),
        rule=make_rule(coinsurance_rate=D("0.10")),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.coinsurance_amount == D("1.00")
    assert result.payable_amount == D("9.02")


# --------------------------------------------------------------------------
# Limit cap interacting with cost sharing
# --------------------------------------------------------------------------

def test_remaining_limit_caps_payable_after_cost_sharing(plan, policy):
    # copay 20 on billed 100 -> computed payable 80; only 50 of limit remains
    # -> payable capped to 50, copay still recorded, partial-limit flagged.
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(annual_limit_amount=D(1000), copay_amount=D(20)),
        plan=plan,
        accumulator=AccumulatorState(amount_used=D(950)),  # 50 remaining
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.copay_amount == D(20)
    assert result.payable_amount == D(50)
    assert ReasonCode.LIMIT_PARTIALLY_APPLIED in result.reason_codes()


def test_remaining_limit_exactly_equals_payable_is_not_partial(plan, policy):
    # Remaining limit (100) exactly equals computed payable (100): full pay,
    # so it must NOT be flagged as a partial-limit application.
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(annual_limit_amount=D(1000)),
        plan=plan,
        accumulator=AccumulatorState(amount_used=D(900)),  # exactly 100 remaining
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.payable_amount == D(100)
    assert ReasonCode.LIMIT_PARTIALLY_APPLIED not in result.reason_codes()


# --------------------------------------------------------------------------
# Multiple simultaneous explanations
# --------------------------------------------------------------------------

def test_all_cost_sharing_reasons_are_explained_together(policy):
    # Deductible (100 remaining), copay 20, coinsurance 10% must each appear.
    # covered 300; deductible 100; remainder 200; copay 20; remainder 180;
    # coinsurance 18; payable 300 - 100 - 20 - 18 = 162.
    result = adjudicate_line_item(
        line=make_line(billed=300),
        rule=make_rule(copay_amount=D(20), coinsurance_rate=D("0.10")),
        plan=Plan(annual_deductible_amount=D(500)),
        accumulator=AccumulatorState(deductible_met_amount=D(400)),
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.deductible_applied == D(100)
    assert result.copay_amount == D(20)
    assert result.coinsurance_amount == D(18)
    assert result.payable_amount == D(162)
    codes = result.reason_codes()
    assert ReasonCode.DEDUCTIBLE_APPLIED in codes
    assert ReasonCode.COPAY_APPLIED in codes
    assert ReasonCode.COINSURANCE_APPLIED in codes


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------

def test_deductible_exactly_equals_billed_yields_zero_payable(policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=200),
        rule=make_rule(),
        plan=Plan(annual_deductible_amount=D(200)),
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.APPROVED
    assert result.deductible_applied == D(200)
    assert result.payable_amount == D(0)


def test_full_coinsurance_means_member_pays_everything(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=make_rule(coinsurance_rate=D("1.0")),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.coinsurance_amount == D(100)
    assert result.payable_amount == D(0)


def test_zero_billed_amount_is_handled(plan, policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=0),
        rule=make_rule(),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.payable_amount == D(0)
    assert result.decision is LineItemDecision.APPROVED


def test_copay_larger_than_billed_never_produces_negative_payable(plan, policy, empty_accumulator):
    # Payable is floored at 0 even when cost sharing exceeds the covered amount.
    result = adjudicate_line_item(
        line=make_line(billed=50),
        rule=make_rule(copay_amount=D(80)),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.payable_amount == D(0)
    assert result.payable_amount >= D(0)


# --------------------------------------------------------------------------
# The payable invariant must hold across configurations
# --------------------------------------------------------------------------

def test_payable_invariant_holds_across_cost_sharing(policy, empty_accumulator):
    result = adjudicate_line_item(
        line=make_line(billed=250),
        rule=make_rule(copay_amount=D(25), coinsurance_rate=D("0.20")),
        plan=Plan(annual_deductible_amount=D(50)),
        accumulator=empty_accumulator,
        policy=policy,
    )
    expected = (
        result.covered_amount
        - result.deductible_applied
        - result.copay_amount
        - result.coinsurance_amount
    )
    assert result.payable_amount == max(D(0), expected)
    assert result.payable_amount >= D(0)


# --------------------------------------------------------------------------
# Rule precedence (documented §6 step order)
# --------------------------------------------------------------------------

def test_policy_validity_precedes_coverage_check(plan, empty_accumulator):
    # Terminated policy AND no coverage rule: validity is checked first, so the
    # reason must be POLICY_INACTIVE, not NOT_COVERED.
    from app.domain.models import PolicyContext
    from datetime import date

    terminated = PolicyContext(
        benefit_period_start=date(2026, 1, 1),
        benefit_period_end=date(2026, 12, 31),
        status="terminated",
    )
    result = adjudicate_line_item(
        line=make_line(billed=100),
        rule=None,
        plan=plan,
        accumulator=empty_accumulator,
        policy=terminated,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.POLICY_INACTIVE in result.reason_codes()
    assert ReasonCode.NOT_COVERED not in result.reason_codes()


def test_exhausted_limit_denies_before_review_threshold(plan, policy):
    # Billed is over the review threshold AND the annual limit is exhausted.
    # Per documented order, the limit check (step 7) precedes review (step 8),
    # so the line is denied for limit, not routed to review.
    result = adjudicate_line_item(
        line=make_line(billed=5000),
        rule=make_rule(annual_limit_amount=D(1000), review_threshold_amount=D(1000)),
        plan=plan,
        accumulator=AccumulatorState(amount_used=D(1000)),  # exhausted
        policy=policy,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.ANNUAL_LIMIT_EXCEEDED in result.reason_codes()


def test_not_covered_ignores_cost_sharing_and_threshold(plan, policy, empty_accumulator):
    # A not-covered rule denies outright regardless of copay/threshold config.
    result = adjudicate_line_item(
        line=make_line(billed=5000),
        rule=make_rule(is_covered=False, copay_amount=D(20), review_threshold_amount=D(100)),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert result.decision is LineItemDecision.DENIED
    assert ReasonCode.NOT_COVERED in result.reason_codes()
    assert result.payable_amount == D(0)
