"""
Middleware for request ID tracking and structured logging.

Every request gets a unique request_id header, logged alongside userId
and idempotencyKey on errors for production incident debugging.
"""

import logging
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

# Context variable for request ID — accessible from any async code in the request
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

logger = logging.getLogger("transaction_ledger")


class RequestIdMiddleware:
    """
    Pure ASGI middleware that assigns a unique request ID to every inbound request.

    Uses raw ASGI instead of BaseHTTPMiddleware to avoid the known Starlette
    bug where BaseHTTPMiddleware can consume/lose the request body on
    cross-origin browser POST requests.

    - Checks for an existing X-Request-ID header (from load balancers).
    - Falls back to generating a new UUID4.
    - Stores it in a ContextVar for access in handlers/services.
    - Echoes it back in the response headers for client-side correlation.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract existing request ID from headers, or generate one
        headers = dict(scope.get("headers", []))
        rid = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        request_id_ctx.set(rid)

        # Extract path and client info for logging
        path = scope.get("path", "unknown")
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        logger.info(
            "request_start",
            extra={
                "request_id": rid,
                "method": scope.get("method", ""),
                "path": path,
                "client_ip": client_ip,
            },
        )

        # Intercept response to inject X-Request-ID header and log status
        status_code = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Inject X-Request-ID into response headers
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                # Log on final body chunk
                if not message.get("more_body", False):
                    logger.info(
                        "request_end",
                        extra={
                            "request_id": rid,
                            "status_code": status_code,
                        },
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)


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
