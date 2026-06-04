"""API request/response models (the HTTP boundary).

Kept separate from the domain dataclasses: these define what the API accepts and
returns, while `app/domain/models.py` holds the pure adjudication types.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import ClaimStatus, LineItemDecision


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
    billed_amount: Decimal
    decision: LineItemDecision
    covered_amount: Decimal
    deductible_applied: Decimal
    copay_amount: Decimal
    coinsurance_amount: Decimal
    payable_amount: Decimal
    reasons: list[ReasonOut]


class ClaimOut(BaseModel):
    claim_id: UUID
    claim_number: str
    status: ClaimStatus
    total_billed_amount: Decimal
    total_payable_amount: Decimal
    line_items: list[LineItemOut]


class DisputeIn(BaseModel):
    reason: str = Field(min_length=1)
    line_item_id: UUID | None = None


class DisputeOut(BaseModel):
    id: UUID
    claim_id: UUID
    line_item_id: UUID | None
    status: str
    reason: str
    resolution_outcome: str | None = None
