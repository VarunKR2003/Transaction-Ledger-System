"""
POST /transaction endpoint.

Handles: validation, rate limiting, idempotent creation, and response
with appropriate status codes (201 new, 200 replay, 409 conflict,
422 validation, 429 rate limit).
"""

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import RateLimitExceededError, InvalidAmountException
from app.middleware import request_id_ctx
from app.schemas import (
    TransactionCreateResponse,
    TransactionRequest,
    TransactionResponse,
    SummaryResponse,
)
from app.services.rate_limiter import rate_limiter
from app.services.transaction_service import create_transaction

logger = logging.getLogger("transaction_ledger")

router = APIRouter(tags=["transactions"])


@router.post(
    "/transaction",
    response_model=TransactionCreateResponse,
    status_code=201,
    responses={
        200: {"model": TransactionCreateResponse, "description": "Idempotent replay"},
        409: {"description": "Idempotency key conflict"},
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def post_transaction(
    body: TransactionRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a transaction for a user.

    - Creates user on first transaction (auto-creation).
    - Deduplicates via DB-level UNIQUE constraint on idempotency_key.
    - Updates user summary counters atomically in SQL.
    - Returns 201 for new, 200 for idempotent replay, 409 for key reuse conflict.
    """
    rid = request_id_ctx.get()

    # ── Rate limit check ──────────────────────────────────────────────
    allowed, retry_after = rate_limiter.check(body.userId)
    if not allowed:
        logger.warning(
            "rate_limit_exceeded",
            extra={"request_id": rid, "user_id": body.userId},
        )
        raise RateLimitExceededError(body.userId, retry_after)
    if body.amount == 0:
        logger.warning(
            "transaction_zero_amount",
            extra={"request_id": rid, "user_id": body.userId},
        )
        raise InvalidAmountException()

    # ── Create transaction ────────────────────────────────────────────
    logger.info(
        "transaction_attempt",
        extra={
            "request_id": rid,
            "user_id": body.userId,
            "idempotency_key": body.idempotencyKey,
        },
    )

    txn, user, is_replay = await create_transaction(
        session=db,
        user_id=body.userId,
        amount=body.amount,
        idempotency_key=body.idempotencyKey,
        client_timestamp=body.clientTimestamp,
    )

    # Set correct status code
    if is_replay:
        response.status_code = 200
    else:
        response.status_code = 201

    return TransactionCreateResponse(
        transaction=TransactionResponse(
            id=txn.id,
            userId=user.user_id,
            amount=str(txn.amount),
            idempotencyKey=txn.idempotency_key,
            status=txn.status,
            countsTowardRanking=txn.counts_toward_ranking,
            createdAt=txn.created_at,
            clientTimestamp=txn.client_timestamp,
        ),
        summary=SummaryResponse(
            userId=user.user_id,
            displayName=user.display_name,
            totalAmount=str(user.total_amount),
            transactionCount=user.transaction_count,
            validTransactionCount=user.valid_transaction_count,
            lastTransactionAt=user.last_transaction_at,
            isFlagged=user.is_flagged,
            createdAt=user.created_at,
        ),
        isReplay=is_replay,
    )
