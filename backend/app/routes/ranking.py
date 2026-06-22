"""
GET /ranking endpoint.

Fairness-adjusted leaderboard with composite score:
  score = W_total * total_amount
        + W_freq  * ln(1 + valid_transaction_count)
        + W_recency * exp(-λ * hours_since_last_transaction)

Anti-manipulation guards:
  - min-amount threshold (prevents micro-transaction frequency spam)
  - log dampening on frequency (diminishing returns on count)
  - flagged users excluded from ranking
  - only users with >0 transactions included
"""

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import (
    PaginationMeta,
    RankingEntry,
    RankingResponse,
    ScoreBreakdown,
)

router = APIRouter(tags=["ranking"])


@router.get(
    "/ranking",
    response_model=RankingResponse,
)
async def get_ranking(
    limit: int = Query(
        default=20, ge=1, le=100,
        description="Page size (max 100)",
    ),
    offset: int = Query(
        default=0, ge=0,
        description="Offset for pagination",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Return leaderboard of users ranked by fairness-adjusted composite score.

    Formula:
      score = W_total * total_amount
            + W_freq  * ln(1 + valid_transaction_count)
            + W_recency * exp(-λ * hours_since_last)

    Supports limit/offset pagination.
    """
    # Clamp limit
    limit = min(limit, settings.MAX_PAGE_LIMIT)

    w_total = settings.RANKING_WEIGHT_TOTAL
    w_freq = settings.RANKING_WEIGHT_FREQUENCY
    w_recency = settings.RANKING_WEIGHT_RECENCY
    decay = settings.RANKING_DECAY_LAMBDA

    # ── Count total eligible users ────────────────────────────────────
    count_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.is_flagged == False,  # noqa: E712
            User.transaction_count > 0,
        )
    )
    total = count_result.scalar()

    if total == 0:
        return RankingResponse(
            rankings=[],
            pagination=PaginationMeta(limit=limit, offset=offset, total=0),
        )

    # ── Fetch ranked users via composite score SQL ────────────────────
    # The ranking is computed live (not materialized) so it always reflects
    # the latest committed state.
    rows = await db.execute(
        text("""
            SELECT
                user_id,
                display_name,
                total_amount,
                valid_transaction_count,
                last_transaction_at,
                created_at,
                (
                    :w_total * total_amount
                    + :w_freq * ln(1 + valid_transaction_count)
                    + :w_recency * exp(
                        -:decay * EXTRACT(EPOCH FROM (
                            NOW() - COALESCE(last_transaction_at, created_at)
                        )) / 3600.0
                    )
                ) AS composite_score
            FROM users
            WHERE is_flagged = false
              AND transaction_count > 0
            ORDER BY composite_score DESC
            LIMIT :lim OFFSET :off
        """),
        {
            "w_total": w_total,
            "w_freq": w_freq,
            "w_recency": w_recency,
            "decay": decay,
            "lim": limit,
            "off": offset,
        },
    )

    rankings = []
    for idx, row in enumerate(rows):
        # Compute breakdown components for transparency
        total_component = float(w_total * float(row.total_amount))
        freq_component = float(
            w_freq * math.log(1 + row.valid_transaction_count)
        )

        if row.last_transaction_at:
            hours_since = (
                datetime.now(timezone.utc) - row.last_transaction_at
            ).total_seconds() / 3600.0
        else:
            hours_since = (
                datetime.now(timezone.utc) - row.created_at
            ).total_seconds() / 3600.0

        recency_component = float(
            w_recency * math.exp(-decay * hours_since)
        )

        rankings.append(
            RankingEntry(
                rank=offset + idx + 1,
                userId=row.user_id,
                displayName=row.display_name,
                compositeScore=round(float(row.composite_score), 4),
                breakdown=ScoreBreakdown(
                    totalComponent=round(total_component, 4),
                    frequencyComponent=round(freq_component, 4),
                    recencyComponent=round(recency_component, 4),
                ),
                totalAmount=str(row.total_amount),
                validTransactionCount=row.valid_transaction_count,
                lastTransactionAt=row.last_transaction_at,
            )
        )

    return RankingResponse(
        rankings=rankings,
        pagination=PaginationMeta(limit=limit, offset=offset, total=total),
    )
