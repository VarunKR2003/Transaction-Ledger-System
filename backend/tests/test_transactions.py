"""
Transaction endpoint tests — the most critical test file.

Covers:
  - Validation edge cases (missing fields, zero, NaN, Infinity, over-max, negative)
  - Idempotent replay (same key+payload → 200)
  - Key reuse conflict (same key + different payload → 409)
  - ⭐ Concurrent duplicate submission (most important test)
  - ⭐ Concurrent different transactions same user (no lost updates)
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient


def make_txn(user_id="user_alice", amount="100.00", key=None):
    """Helper to build a transaction request body."""
    return {
        "userId": user_id,
        "amount": amount,
        "idempotencyKey": key or str(uuid.uuid4()),
    }


# ═══════════════════════════════════════════════════════════════════════
# VALIDATION EDGE CASES
# ═══════════════════════════════════════════════════════════════════════


class TestTransactionValidation:
    @pytest.mark.asyncio
    async def test_missing_user_id(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json={
            "amount": "100.00",
            "idempotencyKey": "key-1",
        })
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_empty_user_id(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json={
            "userId": "",
            "amount": "100.00",
            "idempotencyKey": "key-1",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_whitespace_only_user_id(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json={
            "userId": "   ",
            "amount": "100.00",
            "idempotencyKey": "key-1",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_zero_amount(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json=make_txn(amount="0"))
        assert resp.status_code == 422
        assert "zero" in resp.json()["error"]["details"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_nan_amount(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json=make_txn(amount="NaN"))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_infinity_amount(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json=make_txn(amount="Infinity"))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_infinity_amount(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json=make_txn(amount="-Infinity"))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_over_max_amount(self, client: AsyncClient):
        resp = await client.post(
            "/api/transaction",
            json=make_txn(amount="99999999.00"),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "AMOUNT_EXCEEDS_MAXIMUM"

    @pytest.mark.asyncio
    async def test_negative_amount_allowed(self, client: AsyncClient):
        """Negative amounts are allowed as refunds/debits."""
        resp = await client.post(
            "/api/transaction",
            json=make_txn(amount="-50.00"),
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_missing_idempotency_key(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json={
            "userId": "user_alice",
            "amount": "100.00",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_malformed_json(self, client: AsyncClient):
        resp = await client.post(
            "/api/transaction",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_wrong_type_amount(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json={
            "userId": "user_alice",
            "amount": "not_a_number",
            "idempotencyKey": "key-1",
        })
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# HAPPY PATH
# ═══════════════════════════════════════════════════════════════════════


class TestTransactionCreation:
    @pytest.mark.asyncio
    async def test_create_transaction_returns_201(self, client: AsyncClient):
        resp = await client.post("/api/transaction", json=make_txn())
        assert resp.status_code == 201
        body = resp.json()
        assert body["transaction"]["status"] == "completed"
        assert body["summary"]["transactionCount"] == 1
        assert body["isReplay"] is False

    @pytest.mark.asyncio
    async def test_auto_creates_user(self, client: AsyncClient):
        """User is auto-created on first transaction."""
        user_id = f"new_user_{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/transaction",
            json=make_txn(user_id=user_id),
        )
        assert resp.status_code == 201
        assert resp.json()["summary"]["userId"] == user_id

    @pytest.mark.asyncio
    async def test_summary_accumulates(self, client: AsyncClient):
        """Multiple transactions accumulate correctly."""
        user_id = "accumulator"
        for i in range(3):
            resp = await client.post(
                "/api/transaction",
                json=make_txn(user_id=user_id, amount="10.00"),
            )
            assert resp.status_code == 201

        assert resp.json()["summary"]["transactionCount"] == 3
        assert resp.json()["summary"]["totalAmount"] == "30.00"


# ═══════════════════════════════════════════════════════════════════════
# IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════════


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_idempotent_replay_returns_200(self, client: AsyncClient):
        """Same key + same payload = idempotent replay, 200."""
        key = "idem-key-1"
        body = make_txn(key=key)

        resp1 = await client.post("/api/transaction", json=body)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/transaction", json=body)
        assert resp2.status_code == 200
        assert resp2.json()["isReplay"] is True
        # Transaction IDs should be the same
        assert (
            resp2.json()["transaction"]["id"]
            == resp1.json()["transaction"]["id"]
        )

    @pytest.mark.asyncio
    async def test_key_reuse_different_amount_returns_409(
        self, client: AsyncClient
    ):
        """Same key + different amount = conflict, 409."""
        key = "conflict-key-1"

        resp1 = await client.post(
            "/api/transaction",
            json=make_txn(amount="100.00", key=key),
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/transaction",
            json=make_txn(amount="200.00", key=key),
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    @pytest.mark.asyncio
    async def test_key_reuse_different_user_returns_409(
        self, client: AsyncClient
    ):
        """Same key + different userId = conflict, 409."""
        key = "conflict-key-2"

        resp1 = await client.post(
            "/api/transaction",
            json=make_txn(user_id="user_a", key=key),
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/transaction",
            json=make_txn(user_id="user_b", key=key),
        )
        assert resp2.status_code == 409


# ═══════════════════════════════════════════════════════════════════════
# ⭐ CONCURRENCY — MOST IMPORTANT TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_duplicate_submissions(self, client: AsyncClient):
        """
        ⭐ Fire 10 identical requests (same idempotency key) concurrently.
        Assert: exactly 1 row in DB, all responses are 200 or 201, and the
        summary shows exactly 1 transaction.
        """
        key = "concurrent-dedup-key"
        body = make_txn(user_id="dedup_user", amount="50.00", key=key)

        # Fire 10 concurrent requests
        tasks = [
            client.post("/api/transaction", json=body)
            for _ in range(10)
        ]
        responses = await asyncio.gather(*tasks)

        status_codes = [r.status_code for r in responses]

        # Exactly one 201, rest should be 200
        assert status_codes.count(201) == 1, (
            f"Expected exactly one 201, got: {status_codes}"
        )
        assert all(s in (200, 201) for s in status_codes), (
            f"Unexpected status codes: {status_codes}"
        )

        # Summary should show exactly 1 transaction
        summary_resp = await client.get("/api/summary/dedup_user")
        assert summary_resp.status_code == 200
        summary = summary_resp.json()
        assert summary["transactionCount"] == 1
        assert summary["totalAmount"] == "50.00"

    @pytest.mark.asyncio
    async def test_concurrent_different_transactions_same_user(
        self, client: AsyncClient
    ):
        """
        ⭐ Fire 10 different transactions for the same user concurrently.
        Assert: total_amount equals the exact sum (no lost updates).
        """
        user_id = "concurrent_user"
        amount_per_txn = "25.00"

        # Fire 10 concurrent requests with different keys
        tasks = [
            client.post(
                "/api/transaction",
                json=make_txn(
                    user_id=user_id,
                    amount=amount_per_txn,
                ),
            )
            for _ in range(10)
        ]
        responses = await asyncio.gather(*tasks)

        # All should be 201
        for r in responses:
            assert r.status_code == 201, (
                f"Expected 201, got {r.status_code}: {r.json()}"
            )

        # Summary should reflect all 10 transactions
        summary_resp = await client.get(f"/api/summary/{user_id}")
        assert summary_resp.status_code == 200
        summary = summary_resp.json()
        assert summary["transactionCount"] == 10
        assert summary["totalAmount"] == "250.00"


# ═══════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ═══════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, client: AsyncClient):
        """Exceeding rate limit returns 429."""
        user_id = "rate_limited_user"

        # Default is 10 per minute — send 11
        for i in range(10):
            resp = await client.post(
                "/api/transaction",
                json=make_txn(user_id=user_id, amount="10.00"),
            )
            assert resp.status_code == 201

        # 11th should be rate limited
        resp = await client.post(
            "/api/transaction",
            json=make_txn(user_id=user_id, amount="10.00"),
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMITED"

    @pytest.mark.asyncio
    async def test_rate_limit_independent_per_user(self, client: AsyncClient):
        """Different users have independent rate limits."""
        # Fill up user_a's limit
        for i in range(10):
            await client.post(
                "/api/transaction",
                json=make_txn(user_id="user_a", amount="10.00"),
            )

        # user_b should still be able to transact
        resp = await client.post(
            "/api/transaction",
            json=make_txn(user_id="user_b", amount="10.00"),
        )
        assert resp.status_code == 201
