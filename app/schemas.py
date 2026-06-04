"""API request/response models (the HTTP boundary).

Kept separate from the domain dataclasses: these define what the API accepts and
returns, while `app/domain/models.py` holds the pure adjudication types.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer

from app.domain.enums import ClaimStatus, LineItemDecision

_CENTS = Decimal("0.01")


def _format_money(value: Decimal) -> str:
    """Serialize a monetary amount as a fixed 2-decimal string (e.g. '80.00').

    The values are already quantized to cents by the engine, but the
    DB -> PostgREST -> Decimal round-trip can drop trailing zeros ('80.0').
    Quantizing here gives every money field in a response a consistent 2-dp
    representation without touching validation or the in-memory Decimal.
    """
    return str(value.quantize(_CENTS, rounding=ROUND_HALF_UP))


# A Decimal money field that always serializes to a 2-decimal string.
Money = Annotated[Decimal, PlainSerializer(_format_money, return_type=str)]


class LineItemIn(BaseModel):
    service_type_code: str
    service_date: date
    # Bounded to the NUMERIC(12,2) column range so oversized input is rejected
    # at validation (422) rather than overflowing on insert (500).
    billed_amount: Decimal = Field(ge=0, le=Decimal("9999999999.99"))
    quantity: int = Field(default=1, gt=0)
    diagnosis_code: str | None = None


class ClaimIn(BaseModel):
    policy_id: UUID
    provider_name: str | None = None
    provider_identifier: str | None = None
    line_items: list[LineItemIn] = Field(min_length=1)


class ReasonOut(BaseModel):
    code: str
    message: str | None = None


class LineItemOut(BaseModel):
    id: UUID
    line_number: int
    service_type_code: str
    billed_amount: Money
    decision: LineItemDecision
    covered_amount: Money
    deductible_applied: Money
    copay_amount: Money
    coinsurance_amount: Money
    payable_amount: Money
    reasons: list[ReasonOut]


class ClaimOut(BaseModel):
    claim_id: UUID
    claim_number: str
    status: ClaimStatus
    total_billed_amount: Money
    total_payable_amount: Money
    line_items: list[LineItemOut]


class DisputeIn(BaseModel):
    # Disputes are line-level: a target line is required so the dispute is always
    # resolvable (a claim-level dispute would have no re-adjudication target and
    # could leave the claim permanently `disputed`).
    reason: str = Field(min_length=1)
    line_item_id: UUID


class DisputeOut(BaseModel):
    id: UUID
    claim_id: UUID
    line_item_id: UUID | None
    status: str
    reason: str
    resolution_outcome: str | None = None


class ReviewIn(BaseModel):
    """A reviewer's decision on a line item routed to manual review.

    Only `approved` or `denied` are valid — `needs_review` is the state being
    resolved, not a target.
    """

    decision: Literal["approved", "denied"]
    note: str | None = None
