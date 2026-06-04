"""Dispute-driven re-adjudication behaviour.

Specifies docs/domain-model.md §11-12: adjudication is a deterministic, pure
function of its inputs, and re-adjudication (triggered by a dispute) produces a
*new* result rather than mutating the prior one. Persistence-level versioning
(is_current / sequence) is exercised in integration tests later; here we pin the
domain guarantee the versioning relies on.
"""
from app.domain.adjudication import adjudicate_line_item
from app.domain.enums import LineItemDecision, ReasonCode
from tests.conftest import D, make_line, make_rule


def test_adjudication_is_deterministic_for_same_inputs(plan, policy, empty_accumulator):
    kwargs = dict(
        line=make_line(billed=100),
        rule=make_rule(coinsurance_rate=D("0.20")),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    first = adjudicate_line_item(**kwargs)
    second = adjudicate_line_item(**kwargs)
    assert first == second  # frozen dataclasses compare by value


def test_dispute_overturns_denial_when_coverage_is_corrected(plan, policy, empty_accumulator):
    line = make_line(billed=100)

    # Original submission: no rule on file -> denied as NOT_COVERED.
    original = adjudicate_line_item(
        line=line,
        rule=None,
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert original.decision is LineItemDecision.DENIED
    assert ReasonCode.NOT_COVERED in original.reason_codes()

    # Dispute establishes the service IS covered -> re-adjudication approves it.
    readjudicated = adjudicate_line_item(
        line=line,
        rule=make_rule(is_covered=True),
        plan=plan,
        accumulator=empty_accumulator,
        policy=policy,
    )
    assert readjudicated.decision is LineItemDecision.APPROVED
    assert readjudicated.payable_amount == D(100)

    # The original result object is unchanged (immutability underpins versioning).
    assert original.decision is LineItemDecision.DENIED
    assert original.payable_amount == D(0)
