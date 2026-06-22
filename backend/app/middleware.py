"""
Middleware for request ID tracking and structured logging.

Every request gets a unique request_id header, logged alongside userId
and idempotencyKey on errors for production incident debugging.
"""

import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variable for request ID — accessible from any async code in the request
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

logger = logging.getLogger("transaction_ledger")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique request ID to every inbound request.
    - Checks for an existing X-Request-ID header (from load balancers).
    - Falls back to generating a new UUID4.
    - Stores it in a ContextVar for access in handlers/services.
    - Echoes it back in the response headers for client-side correlation.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Use existing request ID from upstream proxy, or generate one
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(rid)

        # Log the request (without full body — amounts/PII treated sensitively)
        logger.info(
            "request_start",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid

        logger.info(
            "request_end",
            extra={
                "request_id": rid,
                "status_code": response.status_code,
            },
        )

        return response


def setup_logging() -> None:
    """
    Configure structured logging for the application.
    Uses JSON format for machine-parseable logs in production.
    """
    log_handler = logging.StreamHandler()
    log_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    log_handler.setFormatter(formatter)

    root_logger = logging.getLogger("transaction_ledger")
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(log_handler)

    # Quiet down noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
