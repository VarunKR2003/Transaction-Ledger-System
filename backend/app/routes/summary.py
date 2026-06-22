"""
GET /summary/{userId} endpoint.

Returns user activity summary. 404 for nonexistent users —
never silently returns zeroed summary for a mistyped userId.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import SummaryResponse
from app.services.transaction_service import get_user_summary

router = APIRouter(tags=["summary"])


@router.get(
    "/summary/{user_id}",
    response_model=SummaryResponse,
    responses={
        404: {"description": "User not found"},
    },
)
async def get_summary(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return aggregated activity summary for a user.

    - 404 if user does not exist (distinguishable from zero-transaction user).
    - Returns latest committed state — no caching layer.
    """
    user = await get_user_summary(db, user_id)

    return SummaryResponse(
        userId=user.user_id,
        displayName=user.display_name,
        totalAmount=str(user.total_amount),
        transactionCount=user.transaction_count,
        validTransactionCount=user.valid_transaction_count,
        lastTransactionAt=user.last_transaction_at,
        isFlagged=user.is_flagged,
        createdAt=user.created_at,
    )
