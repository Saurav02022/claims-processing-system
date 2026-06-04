"""Domain enumerations.

Values mirror the CHECK constraints and seeded reason codes in the database
migrations (see supabase/migrations/), so the domain layer and the
schema stay in lock-step.
"""
from enum import StrEnum


class LineItemDecision(StrEnum):
    """Outcome the adjudication engine assigns to a single line item."""

    APPROVED = "approved"
    DENIED = "denied"
    NEEDS_REVIEW = "needs_review"


class ClaimStatus(StrEnum):
    """Lifecycle state of a claim (claim.status); a roll-up of its line items."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    PAID = "paid"
    DISPUTED = "disputed"


class ReasonCode(StrEnum):
    """Explanation taxonomy (reason_code.code)."""

    # denials
    NOT_COVERED = "NOT_COVERED"
    POLICY_INACTIVE = "POLICY_INACTIVE"
    SERVICE_DATE_OUT_OF_COVERAGE = "SERVICE_DATE_OUT_OF_COVERAGE"
    ANNUAL_LIMIT_EXCEEDED = "ANNUAL_LIMIT_EXCEEDED"
    VISIT_LIMIT_EXCEEDED = "VISIT_LIMIT_EXCEEDED"
    MANUAL_REVIEW_DENIED = "MANUAL_REVIEW_DENIED"
    # review
    OVER_REVIEW_THRESHOLD = "OVER_REVIEW_THRESHOLD"
    # adjustments
    DEDUCTIBLE_APPLIED = "DEDUCTIBLE_APPLIED"
    COPAY_APPLIED = "COPAY_APPLIED"
    COINSURANCE_APPLIED = "COINSURANCE_APPLIED"
    LIMIT_PARTIALLY_APPLIED = "LIMIT_PARTIALLY_APPLIED"
    COVERED_IN_FULL = "COVERED_IN_FULL"
    MANUAL_REVIEW_APPROVED = "MANUAL_REVIEW_APPROVED"
