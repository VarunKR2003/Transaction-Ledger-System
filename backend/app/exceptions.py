"""
Custom exception classes and centralized exception-to-HTTP-response mapping.

All exceptions are caught by handlers registered in main.py and converted
to the consistent ErrorResponse shape — no bare 500s with stack traces.
"""


class AppError(Exception):
    """Base class for application errors with HTTP status code."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: list | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        super().__init__(message)


class UserNotFoundError(AppError):
    """Raised when a user_id lookup finds no matching user."""

    def __init__(self, user_id: str):
        super().__init__(
            code="USER_NOT_FOUND",
            message=f"User '{user_id}' does not exist.",
            status_code=404,
        )


class RateLimitExceededError(AppError):
    """Raised when per-user rate limit is exceeded."""

    def __init__(self, user_id: str, retry_after: int):
        self.retry_after = retry_after
        super().__init__(
            code="RATE_LIMITED",
            message=f"Rate limit exceeded for user '{user_id}'. "
                    f"Try again in {retry_after} seconds.",
            status_code=429,
        )


class IdempotencyConflictError(AppError):
    """
    Raised when the same idempotency_key is reused with a different
    userId or amount — this is a key-reuse bug, not an idempotent replay.
    """

    def __init__(self, idempotency_key: str):
        super().__init__(
            code="IDEMPOTENCY_KEY_CONFLICT",
            message=f"Idempotency key '{idempotency_key}' was already used with "
                    f"a different userId or amount. Each unique transaction must "
                    f"have a unique idempotency key.",
            status_code=409,
        )


class AmountExceedsMaxError(AppError):
    """Raised when transaction amount exceeds configured maximum."""

    def __init__(self, amount: str, max_amount: str):
        super().__init__(
            code="AMOUNT_EXCEEDS_MAXIMUM",
            message=f"Transaction amount {amount} exceeds the maximum "
                    f"allowed amount of {max_amount}.",
            status_code=422,
            details=[{"field": "amount", "message": f"Must not exceed {max_amount}"}],
        )


class NegativeAmountNotAllowedError(AppError):
    """Raised when negative amounts are submitted but config disallows them."""

    def __init__(self):
        super().__init__(
            code="NEGATIVE_AMOUNT_NOT_ALLOWED",
            message="Negative transaction amounts are not allowed.",
            status_code=422,
            details=[{"field": "amount", "message": "Must be a positive number"}],
        )
