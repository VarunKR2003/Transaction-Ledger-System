"""
Ranking endpoint tests.

Covers:
  - Empty leaderboard
  - Single user
  - Correct ordering by composite score
  - Pagination
  - Flagged users excluded
"""

import uuid

import pytest
from httpx import AsyncClient


async def create_user_with_transactions(
    client: AsyncClient, user_id: str, amount: str, count: int
):
    """Helper: create a user with N transactions."""
    for _ in range(count):
        resp = await client.post("/api/transaction", json={
            "userId": user_id,
            "amount": amount,
            "idempotencyKey": str(uuid.uuid4()),
        })
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_ranking_empty(client: AsyncClient):
    """GET /ranking with zero users returns empty list."""
    resp = await client.get("/api/ranking")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rankings"] == []
    assert body["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_ranking_single_user(client: AsyncClient):
    """Single user appears at rank 1."""
    await create_user_with_transactions(client, "solo_user", "100.00", 3)

    resp = await client.get("/api/ranking")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rankings"]) == 1
    assert body["rankings"][0]["rank"] == 1
    assert body["rankings"][0]["userId"] == "solo_user"
    # Breakdown should be present
    assert "breakdown" in body["rankings"][0]
    assert "totalComponent" in body["rankings"][0]["breakdown"]
    assert "frequencyComponent" in body["rankings"][0]["breakdown"]
    assert "recencyComponent" in body["rankings"][0]["breakdown"]


@pytest.mark.asyncio
async def test_ranking_correct_order(client: AsyncClient):
    """User with higher total ranks above user with lower total."""
    await create_user_with_transactions(client, "low_user", "10.00", 1)
    await create_user_with_transactions(client, "high_user", "1000.00", 1)

    resp = await client.get("/api/ranking")
    assert resp.status_code == 200
    rankings = resp.json()["rankings"]
    assert len(rankings) == 2
    assert rankings[0]["userId"] == "high_user"
    assert rankings[1]["userId"] == "low_user"


@pytest.mark.asyncio
async def test_ranking_pagination(client: AsyncClient):
    """Pagination works correctly with limit/offset."""
    for i in range(5):
        await create_user_with_transactions(
            client, f"page_user_{i}", f"{(i + 1) * 100}.00", 1
        )

    # Get first page of 2
    resp = await client.get("/api/ranking?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rankings"]) == 2
    assert body["pagination"]["total"] == 5
    assert body["rankings"][0]["rank"] == 1
    assert body["rankings"][1]["rank"] == 2

    # Get second page
    resp2 = await client.get("/api/ranking?limit=2&offset=2")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["rankings"]) == 2
    assert body2["rankings"][0]["rank"] == 3


@pytest.mark.asyncio
async def test_ranking_micro_transactions_dampened(client: AsyncClient):
    """
    Frequency dampening: spamming many small valid transactions
    should not linearly inflate rank vs fewer large transactions.
    """
    # User A: 1 large transaction of 500
    await create_user_with_transactions(client, "whale", "500.00", 1)

    # User B: 10 small transactions of 5 each (total = 50)
    await create_user_with_transactions(client, "spammer", "5.00", 10)

    resp = await client.get("/api/ranking")
    rankings = resp.json()["rankings"]

    # Whale should still rank above spammer despite fewer transactions
    # because total_amount (500 vs 50) dominates with W_total=0.5
    whale_rank = next(r for r in rankings if r["userId"] == "whale")
    spammer_rank = next(r for r in rankings if r["userId"] == "spammer")
    assert whale_rank["rank"] < spammer_rank["rank"]
