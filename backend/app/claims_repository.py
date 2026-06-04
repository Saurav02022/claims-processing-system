"""Persistence for claims and disputes, plus the data contracts the service uses.

`ClaimRepository` is the abstraction the service depends on; `SupabaseClaimRepository`
is the live implementation over the Supabase client. Keeping the abstraction here
lets the API be tested with an in-memory fake (no database).

Atomicity note: PostgREST has no multi-call transaction, so writes happen across
several calls. For a single-transaction guarantee, move a write path into a
Postgres function and call it via `client.rpc(...)`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol

from app.domain.models import CoverageRule, Plan, PolicyContext, Reason

_ZERO = Decimal("0")


# --- data contracts -------------------------------------------------------

@dataclass
class PolicyContextData:
    policy_id: str
    plan: Plan
    policy: PolicyContext
    rules: dict[str, CoverageRule]
    service_type_ids: dict[str, str]
    deductible_met: Decimal = _ZERO
    usage: dict[str, tuple[Decimal, int]] = field(default_factory=dict)


@dataclass
class SavedLine:
    line_number: int
    service_type_code: str
    service_type_id: str | None
    service_date: date
    billed_amount: Decimal
    quantity: int
    diagnosis_code: str | None
    decision: str
    covered_amount: Decimal
    deductible_applied: Decimal
    copay_amount: Decimal
    coinsurance_amount: Decimal
    payable_amount: Decimal
    reasons: list[Reason]
    line_id: str | None = None          # set when read back; needed for re-adjudication
    current_sequence: int = 0


@dataclass
class SavedClaim:
    claim_number: str
    policy_id: str
    provider_name: str | None
    provider_identifier: str | None
    status: str
    total_billed_amount: Decimal
    total_payable_amount: Decimal
    lines: list[SavedLine]


class ClaimRepository(Protocol):
    def load_policy_context(self, policy_id: str) -> PolicyContextData | None: ...
    def save_claim(self, saved: SavedClaim) -> str: ...
    def save_accumulators(self, policy_id: str, period_start, period_end,
                          deductible_met: Decimal, usage: dict, service_type_ids: dict) -> None: ...
    def get_claim(self, claim_id: str) -> SavedClaim | None: ...
    def create_dispute(self, claim_id: str, line_item_id: str | None, reason: str) -> dict | None: ...
    def get_dispute(self, dispute_id: str) -> dict | None: ...
    def apply_resolution(self, **kwargs) -> None: ...


# --- helpers --------------------------------------------------------------

def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _num(value: Decimal | None):
    return None if value is None else float(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Supabase implementation ----------------------------------------------

class SupabaseClaimRepository:
    def __init__(self, client):
        self.client = client
        self._reason_ids: dict[str, str] | None = None

    # ---- read ----
    def load_policy_context(self, policy_id: str) -> PolicyContextData | None:
        c = self.client
        rows = c.table("policy").select("*").eq("id", str(policy_id)).limit(1).execute().data
        if not rows:
            return None
        policy = rows[0]
        plan = c.table("plan").select("*").eq("id", policy["plan_id"]).single().execute().data

        service_types = c.table("service_type").select("id,code").execute().data
        code_by_id = {r["id"]: r["code"] for r in service_types}
        id_by_code = {r["code"]: r["id"] for r in service_types}

        rules: dict[str, CoverageRule] = {}
        for r in c.table("coverage_rule").select("*").eq("plan_id", policy["plan_id"]).execute().data:
            code = code_by_id.get(r["service_type_id"])
            if code is None:
                continue
            rules[code] = CoverageRule(
                service_type_code=code,
                is_covered=r["is_covered"],
                annual_limit_amount=_dec(r["annual_limit_amount"]),
                annual_visit_limit=r["annual_visit_limit"],
                copay_amount=_dec(r["copay_amount"]) or _ZERO,
                coinsurance_rate=_dec(r["coinsurance_rate"]) or _ZERO,
                review_threshold_amount=_dec(r["review_threshold_amount"]),
            )

        deductible_met = _ZERO
        usage: dict[str, tuple[Decimal, int]] = {}
        acc_rows = (
            c.table("accumulator").select("*").eq("policy_id", str(policy_id))
            .eq("period_start", policy["benefit_period_start"]).execute().data
        )
        for a in acc_rows:
            if a["service_type_id"] is None:
                deductible_met = _dec(a["deductible_met_amount"]) or _ZERO
            elif (code := code_by_id.get(a["service_type_id"])) is not None:
                usage[code] = (_dec(a["amount_used"]) or _ZERO, int(a["visits_used"]))

        return PolicyContextData(
            policy_id=str(policy_id),
            plan=Plan(annual_deductible_amount=_dec(plan["annual_deductible_amount"]) or _ZERO),
            policy=PolicyContext(
                benefit_period_start=date.fromisoformat(policy["benefit_period_start"]),
                benefit_period_end=date.fromisoformat(policy["benefit_period_end"]),
                status=policy["status"],
            ),
            rules=rules,
            service_type_ids=id_by_code,
            deductible_met=deductible_met,
            usage=usage,
        )

    def get_claim(self, claim_id: str) -> SavedClaim | None:
        c = self.client
        rows = c.table("claim").select("*").eq("id", str(claim_id)).limit(1).execute().data
        if not rows:
            return None
        claim = rows[0]
        code_by_id = {r["id"]: r["code"] for r in c.table("service_type").select("id,code").execute().data}
        reason_by_id = {r["id"]: r["code"] for r in c.table("reason_code").select("id,code").execute().data}

        lines: list[SavedLine] = []
        for lr in c.table("claim_line_item").select("*").eq("claim_id", str(claim_id)).order("line_number").execute().data:
            adj_rows = (
                c.table("adjudication").select("*").eq("line_item_id", lr["id"])
                .eq("is_current", True).limit(1).execute().data
            )
            adj = adj_rows[0] if adj_rows else None
            reasons: list[Reason] = []
            if adj:
                for x in c.table("adjudication_reason").select("*").eq("adjudication_id", adj["id"]).execute().data:
                    reasons.append(Reason(code=reason_by_id.get(x["reason_code_id"], ""), message=x["message"]))
            lines.append(SavedLine(
                line_number=lr["line_number"],
                service_type_code=code_by_id.get(lr["service_type_id"], ""),
                service_type_id=lr["service_type_id"],
                service_date=date.fromisoformat(lr["service_date"]),
                billed_amount=_dec(lr["billed_amount"]) or _ZERO,
                quantity=lr["quantity"],
                diagnosis_code=lr["diagnosis_code"],
                decision=adj["decision"] if adj else lr["status"],
                covered_amount=_dec(adj["covered_amount"]) if adj else _ZERO,
                deductible_applied=_dec(adj["deductible_applied"]) if adj else _ZERO,
                copay_amount=_dec(adj["copay_amount"]) if adj else _ZERO,
                coinsurance_amount=_dec(adj["coinsurance_amount"]) if adj else _ZERO,
                payable_amount=_dec(adj["payable_amount"]) if adj else _ZERO,
                reasons=reasons,
                line_id=lr["id"],
                current_sequence=adj["sequence"] if adj else 0,
            ))

        return SavedClaim(
            claim_number=claim["claim_number"], policy_id=claim["policy_id"],
            provider_name=claim["provider_name"], provider_identifier=claim["provider_identifier"],
            status=claim["status"],
            total_billed_amount=_dec(claim["total_billed_amount"]) or _ZERO,
            total_payable_amount=_dec(claim["total_payable_amount"]) or _ZERO,
            lines=lines,
        )

    # ---- write ----
    def save_claim(self, saved: SavedClaim) -> str:
        c = self.client
        reason_ids = self._reason_code_ids()
        claim = c.table("claim").insert({
            "claim_number": saved.claim_number, "policy_id": saved.policy_id, "status": saved.status,
            "provider_name": saved.provider_name, "provider_identifier": saved.provider_identifier,
            "total_billed_amount": _num(saved.total_billed_amount),
            "total_payable_amount": _num(saved.total_payable_amount),
        }).execute().data[0]
        c.table("claim_status_history").insert({
            "claim_id": claim["id"], "from_status": None, "to_status": saved.status,
            "reason": "submission", "changed_by": "system",
        }).execute()

        for line in saved.lines:
            li = c.table("claim_line_item").insert({
                "claim_id": claim["id"], "line_number": line.line_number,
                "service_type_id": line.service_type_id, "service_date": line.service_date.isoformat(),
                "billed_amount": _num(line.billed_amount), "quantity": line.quantity,
                "diagnosis_code": line.diagnosis_code, "status": line.decision,
            }).execute().data[0]
            self._insert_adjudication(li["id"], 1, line.decision, line, reason_ids)
            c.table("line_item_status_history").insert({
                "line_item_id": li["id"], "from_status": "pending", "to_status": line.decision,
                "reason": "submission", "changed_by": "system",
            }).execute()
        return claim["id"]

    def save_accumulators(self, policy_id, period_start, period_end, deductible_met, usage, service_type_ids):
        ps = period_start.isoformat() if hasattr(period_start, "isoformat") else period_start
        pe = period_end.isoformat() if hasattr(period_end, "isoformat") else period_end
        self._upsert_accumulator(policy_id, ps, pe, None, {"deductible_met_amount": _num(deductible_met)})
        for code, (amount, visits) in usage.items():
            stid = service_type_ids.get(code)
            if stid is not None:
                self._upsert_accumulator(policy_id, ps, pe, stid, {"amount_used": _num(amount), "visits_used": visits})

    def create_dispute(self, claim_id, line_item_id, reason):
        c = self.client
        claim = c.table("claim").select("status").eq("id", str(claim_id)).limit(1).execute().data
        if not claim:
            return None
        dispute = c.table("dispute").insert({
            "claim_id": str(claim_id), "line_item_id": line_item_id, "reason": reason, "status": "open",
        }).execute().data[0]
        c.table("claim").update({"status": "disputed"}).eq("id", str(claim_id)).execute()
        c.table("claim_status_history").insert({
            "claim_id": str(claim_id), "from_status": claim[0]["status"], "to_status": "disputed",
            "reason": "dispute opened", "changed_by": "member",
        }).execute()
        return dispute

    def get_dispute(self, dispute_id):
        rows = self.client.table("dispute").select("*").eq("id", str(dispute_id)).limit(1).execute().data
        return rows[0] if rows else None

    def apply_resolution(self, *, dispute_id, claim_id, line_id, prev_sequence, prev_line_decision,
                         new_line, new_claim_status, new_total, outcome,
                         policy_id, period_start, period_end, deductible_met, usage, service_type_ids):
        c = self.client
        reason_ids = self._reason_code_ids()
        c.table("adjudication").update({"is_current": False}).eq("line_item_id", line_id).eq("is_current", True).execute()
        self._insert_adjudication(line_id, prev_sequence + 1, new_line.decision, new_line, reason_ids, triggered_by="dispute")
        c.table("claim_line_item").update({"status": new_line.decision}).eq("id", line_id).execute()
        c.table("line_item_status_history").insert({
            "line_item_id": line_id, "from_status": prev_line_decision, "to_status": new_line.decision,
            "reason": "dispute resolution", "changed_by": "system",
        }).execute()
        c.table("claim").update({"status": new_claim_status, "total_payable_amount": _num(new_total)}).eq("id", claim_id).execute()
        c.table("claim_status_history").insert({
            "claim_id": claim_id, "from_status": "disputed", "to_status": new_claim_status,
            "reason": "dispute resolved", "changed_by": "system",
        }).execute()
        self.save_accumulators(policy_id, period_start, period_end, deductible_met, usage, service_type_ids)
        c.table("dispute").update({
            "status": "resolved", "resolution_outcome": outcome,
            "resolution_notes": f"Re-adjudicated: {outcome}.", "resolved_at": _now(),
        }).eq("id", dispute_id).execute()

    # ---- internals ----
    def _insert_adjudication(self, line_id, sequence, decision, line, reason_ids, triggered_by="submission"):
        c = self.client
        adj = c.table("adjudication").insert({
            "line_item_id": line_id, "sequence": sequence, "is_current": True, "decision": decision,
            "covered_amount": _num(line.covered_amount), "deductible_applied": _num(line.deductible_applied),
            "copay_amount": _num(line.copay_amount), "coinsurance_amount": _num(line.coinsurance_amount),
            "payable_amount": _num(line.payable_amount), "triggered_by": triggered_by,
        }).execute().data[0]
        payload = [
            {"adjudication_id": adj["id"], "reason_code_id": reason_ids[str(r.code)], "message": r.message or ""}
            for r in line.reasons if str(r.code) in reason_ids
        ]
        if payload:
            c.table("adjudication_reason").insert(payload).execute()

    def _upsert_accumulator(self, policy_id, period_start, period_end, service_type_id, fields):
        c = self.client
        q = c.table("accumulator").select("id").eq("policy_id", policy_id).eq("period_start", period_start)
        q = q.is_("service_type_id", "null") if service_type_id is None else q.eq("service_type_id", service_type_id)
        existing = q.limit(1).execute().data
        if existing:
            c.table("accumulator").update(fields).eq("id", existing[0]["id"]).execute()
        else:
            c.table("accumulator").insert({
                "policy_id": policy_id, "service_type_id": service_type_id,
                "period_start": period_start, "period_end": period_end, **fields,
            }).execute()

    def _reason_code_ids(self) -> dict[str, str]:
        if self._reason_ids is None:
            rows = self.client.table("reason_code").select("id,code").execute().data
            self._reason_ids = {r["code"]: r["id"] for r in rows}
        return self._reason_ids
