"""
In-memory sliding-window rate limiter.

Known limitation: per-process only. In multi-instance deployments,
replace with Redis-backed sliding window (ZRANGEBYSCORE pattern).
"""

import time
from collections import defaultdict, deque

from app.config import settings


class RateLimiter:
    def __init__(self, max_requests: int | None = None, window_seconds: int | None = None):
        self.max_requests = max_requests or settings.RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def check(self, user_id: str) -> tuple[bool, int]:
        now = time.monotonic()
        window_start = now - self.window_seconds
        window = self._windows[user_id]

        while window and window[0] < window_start:
            window.popleft()

        if len(window) >= self.max_requests:
            oldest = window[0]
            retry_after = int(self.window_seconds - (now - oldest)) + 1
            return False, max(retry_after, 1)

        window.append(now)
        return True, 0

    def reset(self, user_id: str | None = None) -> None:
        if user_id:
            self._windows.pop(user_id, None)
        else:
            self._windows.clear()


rate_limiter = RateLimiter()
