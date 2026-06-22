"""
Rate limiter unit tests.

Tests the in-memory sliding window limiter directly (not through HTTP).
"""

import time

import pytest

from app.services.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_allows_up_to_limit(self):
        """Requests up to the limit are allowed."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, _ = limiter.check("user_a")
            assert allowed is True

    def test_rejects_over_limit(self):
        """The (limit+1)th request is rejected."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            limiter.check("user_a")

        allowed, retry_after = limiter.check("user_a")
        assert allowed is False
        assert retry_after > 0

    def test_independent_per_user(self):
        """Different users have independent counters."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.check("user_a")
        limiter.check("user_a")

        # user_a is at limit, user_b should still be free
        allowed_a, _ = limiter.check("user_a")
        assert allowed_a is False

        allowed_b, _ = limiter.check("user_b")
        assert allowed_b is True

    def test_reset_clears_user(self):
        """Reset for a specific user clears their counter."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.check("user_a")
        limiter.check("user_a")

        limiter.reset("user_a")

        allowed, _ = limiter.check("user_a")
        assert allowed is True

    def test_reset_all(self):
        """Reset without user_id clears all counters."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.check("user_a")
        limiter.check("user_b")

        limiter.reset()

        allowed_a, _ = limiter.check("user_a")
        allowed_b, _ = limiter.check("user_b")
        assert allowed_a is True
        assert allowed_b is True
