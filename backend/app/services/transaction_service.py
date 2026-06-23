"""
Core transaction business logic.

Handles: user auto-creation, idempotent insert via ON CONFLICT,
atomic summary update, and dedup conflict detection.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import (
    AmountExceedsMaxError,
    IdempotencyConflictError,
    NegativeAmountNotAllowedError,
    UserNotFoundError,
)
from app.models import Transaction, User

logger = logging.getLogger("transaction_ledger")


async def get_or_create_user(
    session: AsyncSession, user_id: str
) -> User:
    """
    Find existing user by client-facing user_id, or create one.
    Auto-creation on first transaction (documented in ASSUMPTIONS.md).
    """
    uid = int(user_id)
    result = await session.execute(
        select(User).where(User.id == uid)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(id=uid)
        session.add(user)
        await session.flush()  # Get the generated id

    return user


async def get_user_summary(
    session: AsyncSession, user_id: str
) -> User:
    """
    Get user by client-facing user_id.
    Raises UserNotFoundError if not found (never returns a zeroed summary
    for a nonexistent user — that hides bugs).
    """
    try:
        uid = int(user_id)
    except ValueError:
        raise UserNotFoundError(user_id)

    result = await session.execute(
        select(User).where(User.id == uid)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise UserNotFoundError(user_id)

    return user


async def create_transaction(
    session: AsyncSession,
    user_id: str,
    amount: Decimal,
    idempotency_key: str,
    client_timestamp: datetime | None = None,
) -> tuple[Transaction, User, bool]:
    """
    Create a new transaction with full idempotency and atomic summary update.

    Returns: (transaction, user, is_replay)
      - is_replay=False, status 201: new transaction created
      - is_replay=True,  status 200: idempotent replay of existing

    Raises:
      - AmountExceedsMaxError: abs(amount) > MAX_TRANSACTION_AMOUNT
      - NegativeAmountNotAllowedError: amount < 0 and config disallows
      - IdempotencyConflictError: same key used with different userId/amount

    Flow:
      1. Validate amount bounds
      2. Auto-create user if needed
      3. INSERT ... ON CONFLICT (idempotency_key) DO NOTHING
      4. If inserted (rowcount=1): atomic UPDATE users counters
      5. If conflict (rowcount=0): check if same payload → replay, else → 409
    """
    # ── Step 1: Validate amount bounds ────────────────────────────────
    abs_amount = abs(amount)

    if abs_amount > settings.MAX_TRANSACTION_AMOUNT:
        raise AmountExceedsMaxError(
            str(amount), str(settings.MAX_TRANSACTION_AMOUNT)
        )

    if amount < 0 and not settings.ALLOW_NEGATIVE_AMOUNTS:
        raise NegativeAmountNotAllowedError()

    # ── Step 2: Auto-create user ──────────────────────────────────────
    user = await get_or_create_user(session, user_id)

    # Determine if this transaction counts toward ranking
    counts = abs_amount >= settings.MIN_TRANSACTION_AMOUNT_FOR_RANKING

    # ── Step 3: INSERT ... ON CONFLICT DO NOTHING ─────────────────────
    # This is race-proof: the UNIQUE constraint on idempotency_key prevents
    # duplicates even under concurrent identical requests.
    now = datetime.now(timezone.utc)
    logger.info(f"ATTEMPTING TRANSACTION: {user_id},{amount},{idempotency_key},{client_timestamp}")
    insert_result = await session.execute(
        text("""
            INSERT INTO transactions (
                user_id, amount, idempotency_key, status,
                counts_toward_ranking, created_at, client_timestamp
            )
            VALUES (
                :user_id, :amount, :idempotency_key, 'completed',
                :counts, :created_at, :client_timestamp
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
        """),
        {
            "user_id": user.id,
            "amount": amount,
            "idempotency_key": idempotency_key,
            "counts": counts,
            "created_at": now,
            "client_timestamp": client_timestamp,
        },
    )
    logger.info(f"TRANSACTION EXECUTED: {insert_result}")

    new_row = insert_result.fetchone()

    if new_row is not None:
        # ── Step 4: New insert — atomic summary update ────────────────
        valid_incr = 1 if counts else 0

        await session.execute(
            text("""
                UPDATE users SET
                    total_amount = total_amount + :amount,
                    transaction_count = transaction_count + 1,
                    valid_transaction_count = valid_transaction_count + :valid_incr,
                    last_transaction_at = :now,
                    updated_at = :now
                WHERE id = :uid
            """),
            {
                "amount": amount,
                "valid_incr": valid_incr,
                "now": now,
                "uid": user.id,
            },
        )

        # Flush to ensure everything is in sync
        await session.flush()

        # Reload user to get updated counters
        await session.refresh(user)

        # Fetch the newly created transaction
        txn_result = await session.execute(
            select(Transaction).where(Transaction.id == new_row[0])
        )
        txn = txn_result.scalar_one()

        return txn, user, False  # is_replay=False

    else:
        # ── Step 5: Conflict — check if idempotent replay or key reuse ─
        existing_result = await session.execute(
            select(Transaction).where(
                Transaction.idempotency_key == idempotency_key
            )
        )
        existing_txn = existing_result.scalar_one()

        # Check if the existing transaction matches this request's payload
        existing_user_result = await session.execute(
            select(User).where(User.id == existing_txn.user_id)
        )
        existing_user = existing_user_result.scalar_one()

        if (
            existing_user.id != int(user_id)
            or Decimal(str(existing_txn.amount)) != amount
        ):
            # Different payload with same key → conflict, not a replay
            raise IdempotencyConflictError(idempotency_key)

        # Same payload → idempotent replay, return original
        return existing_txn, existing_user, True  # is_replay=True
