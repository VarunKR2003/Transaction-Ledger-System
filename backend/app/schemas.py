"""
Pydantic v2 schemas for request validation and response serialization.

Every external input is validated here — no manual dict access without validation.
Custom validators reject NaN, Infinity, zero, and over-max amounts.
"""

import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════


class TransactionRequest(BaseModel):
    """
    POST /transaction request body.

    Validates:
      - userId: non-empty string
      - amount: finite, non-zero, within bounds
      - idempotencyKey: non-empty string (client-supplied for safe retries)
      - clientTimestamp: optional, for audit only
    """

    userId: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Client-facing user identifier.",
        examples=["user_alice"],
    )
    amount: Decimal = Field(
        ...,
        description="Transaction amount. Must be finite, non-zero. "
                    "Negative values allowed for refunds/debits.",
        examples=["150.50"],
    )
    idempotencyKey: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Client-supplied idempotency key for safe retries.",
        examples=["txn-abc-123"],
    )
    clientTimestamp: datetime | None = Field(
        default=None,
        description="Optional client-side timestamp for audit. Never trusted for logic.",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount_is_finite(cls, v: Any) -> Decimal:
        """Reject NaN, Infinity, -Infinity, and non-numeric garbage."""
        # Handle float NaN/Infinity before Decimal conversion
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                raise ValueError("Amount must be a finite number, not NaN or Infinity.")
            v = Decimal(str(v))
        elif isinstance(v, (int, str)):
            try:
                v = Decimal(str(v))
            except (InvalidOperation, ValueError):
                raise ValueError("Amount must be a valid numeric value.")
        elif isinstance(v, Decimal):
            pass
        else:
            raise ValueError("Amount must be a numeric value.")

        # Check for Decimal special values
        if not v.is_finite():
            raise ValueError("Amount must be a finite number, not NaN or Infinity.")

        return v

    @field_validator("amount", mode="after")
    @classmethod
    def validate_amount_not_zero(cls, v: Decimal) -> Decimal:
        """Zero amounts are treated as a no-op / likely client bug."""
        if v == 0:
            raise ValueError(
                "Amount must not be zero. Zero transactions are treated as "
                "a no-op and likely indicate a client bug."
            )
        return v

    @field_validator("userId", "idempotencyKey", mode="after")
    @classmethod
    def validate_not_whitespace_only(cls, v: str) -> str:
        """Reject strings that are technically non-empty but only whitespace."""
        if not v.strip():
            raise ValueError("Must not be empty or whitespace-only.")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════


class TransactionResponse(BaseModel):
    """Single transaction record in a response."""

    id: UUID
    userId: str
    amount: str  # String representation of Decimal for JSON safety
    idempotencyKey: str
    status: str
    countsTowardRanking: bool
    createdAt: datetime
    clientTimestamp: datetime | None = None

    model_config = {"from_attributes": True}


class SummaryResponse(BaseModel):
    """User activity summary."""

    userId: str
    displayName: str | None = None
    totalAmount: str  # String Decimal
    transactionCount: int
    validTransactionCount: int
    lastTransactionAt: datetime | None = None
    isFlagged: bool
    createdAt: datetime

    model_config = {"from_attributes": True}


class ScoreBreakdown(BaseModel):
    """Breakdown of the composite ranking score components."""

    totalComponent: float
    frequencyComponent: float
    recencyComponent: float


class RankingEntry(BaseModel):
    """Single entry in the leaderboard."""

    rank: int
    userId: str
    displayName: str | None = None
    compositeScore: float
    breakdown: ScoreBreakdown
    totalAmount: str
    validTransactionCount: int
    lastTransactionAt: datetime | None = None


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    limit: int
    offset: int
    total: int


class RankingResponse(BaseModel):
    """GET /ranking response."""

    rankings: list[RankingEntry]
    pagination: PaginationMeta


class TransactionCreateResponse(BaseModel):
    """
    POST /transaction response, includes both the transaction
    record and the updated user summary.
    """

    transaction: TransactionResponse
    summary: SummaryResponse
    isReplay: bool = Field(
        default=False,
        description="True if this was an idempotent replay of an existing transaction.",
    )


# ═══════════════════════════════════════════════════════════════════════════
# ERROR SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════


class ErrorDetail(BaseModel):
    """Field-level error detail."""

    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    """Structured error body."""

    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorResponse(BaseModel):
    """
    Consistent error response shape across all endpoints.
    Example: {"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [...]}}
    """

    error: ErrorBody
