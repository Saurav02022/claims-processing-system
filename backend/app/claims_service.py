"""Claim + dispute orchestration over the pure adjudication engine.

Framework-agnostic: loads context, runs the engine, persists via the repository,
and shapes API responses. Domain errors are plain exceptions; the API maps them
to HTTP status codes.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from app.claims_repository import ClaimRepository, SavedClaim, SavedLine
from app.domain.adjudication import adjudicate_line_item, claim_total_payable, roll_up_claim_status
from app.domain.enums import LineItemDecision
from app.domain.models import AccumulatorState, LineItemInput
from app.schemas import ClaimIn, ClaimOut, DisputeIn, DisputeOut, LineItemOut, ReasonOut

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


class PolicyNotFound(Exception): ...
class ClaimNotFound(Exception): ...
class DisputeNotFound(Exception): ...
class DisputeAlreadyResolved(Exception): ...


class UnknownServiceType(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class LineNotInClaim(Exception): ...


def submit_claim(repo: ClaimRepository, submission: ClaimIn) -> ClaimOut:
    ctx = repo.load_policy_context(str(submission.policy_id))
    if ctx is None:
        raise PolicyNotFound()
    for li in submission.line_items:
        if li.service_type_code not in ctx.service_type_ids:
            raise UnknownServiceType(li.service_type_code)

    running_deductible_met = ctx.deductible_met
    running_usage = dict(ctx.usage)
    results, saved_lines = [], []

    for index, li in enumerate(submission.line_items, start=1):
        used_amount, used_visits = running_usage.get(li.service_type_code, (_ZERO, 0))
        result = adjudicate_line_item(
            line=LineItemInput(li.service_type_code, li.service_date, li.billed_amount, li.quantity),
            rule=ctx.rules.get(li.service_type_code),
            plan=ctx.plan,
            accumulator=AccumulatorState(running_deductible_met, used_amount, used_visits),
            policy=ctx.policy,
        )
        results.append(result)
        running_deductible_met += result.deductible_applied
        visit_increment = 0 if result.decision is LineItemDecision.DENIED else 1
        running_usage[li.service_type_code] = (used_amount + result.payable_amount, used_visits + visit_increment)
        saved_lines.append(_line_from_result(index, li.service_type_code, ctx.service_type_ids[li.service_type_code],
                                              li.service_date, li.billed_amount, li.quantity, li.diagnosis_code, result))

    status = roll_up_claim_status([r.decision for r in results])
    saved = SavedClaim(
        claim_number=f"CLM-{uuid.uuid4().hex[:10].upper()}",
        policy_id=str(submission.policy_id),
        provider_name=submission.provider_name,
        provider_identifier=submission.provider_identifier,
        status=str(status),
        total_billed_amount=sum((li.billed_amount for li in submission.line_items), _ZERO),
        total_payable_amount=claim_total_payable(results),
        lines=saved_lines,
    )
    claim_id = repo.save_claim(saved)
    repo.save_accumulators(str(submission.policy_id), ctx.policy.benefit_period_start,
                           ctx.policy.benefit_period_end, running_deductible_met, running_usage, ctx.service_type_ids)
    logger.info("claim %s submitted: status=%s lines=%d", saved.claim_number, status, len(saved_lines))
    # Re-read so the response carries persisted line ids (needed to dispute a line).
    return get_claim(repo, claim_id)


def get_claim(repo: ClaimRepository, claim_id: str) -> ClaimOut:
    saved = repo.get_claim(claim_id)
    if saved is None:
        raise ClaimNotFound()
    return _to_response(claim_id, saved)


def open_dispute(repo: ClaimRepository, claim_id: str, payload: DisputeIn) -> DisputeOut:
    claim = repo.get_claim(claim_id)
    if claim is None:
        raise ClaimNotFound()
    line_id = str(payload.line_item_id) if payload.line_item_id else None
    if line_id is not None and not any(line.line_id == line_id for line in claim.lines):
        raise LineNotInClaim()
    dispute = repo.create_dispute(claim_id, line_id, payload.reason)
    if dispute is None:
        raise ClaimNotFound()
    logger.info("dispute opened on claim %s (line=%s)", claim_id, line_id)
    return _dispute_out(dispute)


def resolve_dispute(repo: ClaimRepository, dispute_id: str) -> ClaimOut:
    dispute = repo.get_dispute(dispute_id)
    if dispute is None:
        raise DisputeNotFound()
    if dispute["status"] == "resolved":
        raise DisputeAlreadyResolved()
    line_id = dispute["line_item_id"]
    if line_id is None:
        raise LineNotInClaim()  # this endpoint resolves line-level disputes

    claim_id = dispute["claim_id"]
    claim = repo.get_claim(claim_id)
    ctx = repo.load_policy_context(claim.policy_id)
    line = next((l for l in claim.lines if l.line_id == line_id), None)
    if line is None:
        raise LineNotInClaim()

    code = line.service_type_code
    used_amount, used_visits = ctx.usage.get(code, (_ZERO, 0))
    # Re-evaluate against current rules, excluding THIS line's prior contribution.
    base_deductible = max(_ZERO, ctx.deductible_met - line.deductible_applied)
    base_amount = max(_ZERO, used_amount - line.payable_amount)
    base_visits = max(0, used_visits - (0 if line.decision == LineItemDecision.DENIED else 1))
    result = adjudicate_line_item(
        line=LineItemInput(code, line.service_date, line.billed_amount, line.quantity),
        rule=ctx.rules.get(code),
        plan=ctx.plan,
        accumulator=AccumulatorState(base_deductible, base_amount, base_visits),
        policy=ctx.policy,
    )
    changed = str(result.decision) != line.decision or result.payable_amount != line.payable_amount
    outcome = "overturned" if changed else "upheld"

    # Reconcile claim totals/status using the other lines' current results.
    decisions, total = [], _ZERO
    for other in claim.lines:
        if other.line_id == line_id:
            decisions.append(result.decision)
            total += result.payable_amount
        else:
            decisions.append(LineItemDecision(other.decision))
            total += other.payable_amount
    new_status = roll_up_claim_status(decisions)

    new_usage = dict(ctx.usage)
    new_usage[code] = (base_amount + result.payable_amount,
                       base_visits + (0 if result.decision is LineItemDecision.DENIED else 1))

    repo.apply_resolution(
        dispute_id=dispute_id, claim_id=claim_id, line_id=line_id,
        prev_sequence=line.current_sequence, prev_line_decision=line.decision,
        new_line=_line_from_result(line.line_number, code, ctx.service_type_ids.get(code),
                                   line.service_date, line.billed_amount, line.quantity, line.diagnosis_code, result),
        new_claim_status=str(new_status), new_total=total, outcome=outcome,
        policy_id=ctx.policy_id, period_start=ctx.policy.benefit_period_start, period_end=ctx.policy.benefit_period_end,
        deductible_met=base_deductible + result.deductible_applied, usage=new_usage,
        service_type_ids=ctx.service_type_ids,
    )
    logger.info("dispute %s resolved: outcome=%s claim_status=%s", dispute_id, outcome, new_status)
    return get_claim(repo, claim_id)


# --- mapping helpers ------------------------------------------------------

def _line_from_result(line_number, code, service_type_id, service_date, billed, quantity, diagnosis, result) -> SavedLine:
    return SavedLine(
        line_number=line_number, service_type_code=code, service_type_id=service_type_id,
        service_date=service_date, billed_amount=billed, quantity=quantity, diagnosis_code=diagnosis,
        decision=str(result.decision), covered_amount=result.covered_amount,
        deductible_applied=result.deductible_applied, copay_amount=result.copay_amount,
        coinsurance_amount=result.coinsurance_amount, payable_amount=result.payable_amount,
        reasons=list(result.reasons),
    )


def _to_response(claim_id: str, saved: SavedClaim) -> ClaimOut:
    return ClaimOut(
        claim_id=claim_id, claim_number=saved.claim_number, status=saved.status,
        total_billed_amount=saved.total_billed_amount, total_payable_amount=saved.total_payable_amount,
        line_items=[
            LineItemOut(
                id=line.line_id, line_number=line.line_number, service_type_code=line.service_type_code,
                billed_amount=line.billed_amount, decision=line.decision,
                covered_amount=line.covered_amount, deductible_applied=line.deductible_applied,
                copay_amount=line.copay_amount, coinsurance_amount=line.coinsurance_amount,
                payable_amount=line.payable_amount,
                reasons=[ReasonOut(code=str(r.code), message=r.message) for r in line.reasons],
            )
            for line in saved.lines
        ],
    )


def _dispute_out(dispute: dict) -> DisputeOut:
    return DisputeOut(
        id=dispute["id"], claim_id=dispute["claim_id"], line_item_id=dispute.get("line_item_id"),
        status=dispute["status"], reason=dispute["reason"],
        resolution_outcome=dispute.get("resolution_outcome"),
    )
