"""
FastAPI application entry point.

Wires together: routers, middleware, CORS, and centralized exception handlers.
No bare 500s with stack traces — every exception maps to the consistent
ErrorResponse shape.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import AppError
from app.middleware import RequestIdMiddleware, request_id_ctx, setup_logging
from app.routes import transactions, summary, ranking

# ── Logging ───────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger("transaction_ledger")

# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Transaction Ledger API",
    description="Points/activity-ledger system with idempotent transactions, "
                "fairness-adjusted ranking, and concurrency-safe updates.",
    version="1.0.0",
)

# ── Middleware ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(transactions.router, prefix="/api")
app.include_router(summary.router, prefix="/api")
app.include_router(ranking.router, prefix="/api")


# ── Exception Handlers ────────────────────────────────────────────────────

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """Handle all custom AppError subclasses."""
    rid = request_id_ctx.get()
    logger.warning(
        f"app_error: {exc.code}",
        extra={"request_id": rid, "error_code": exc.code},
    )

    body = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    }

    headers = {}
    if hasattr(exc, "retry_after"):
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """
    Convert Pydantic/FastAPI validation errors to our consistent error shape.
    Returns 422 with field-level details.
    """
    details = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        details.append({
            "field": field,
            "message": error.get("msg", "Invalid value"),
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": details,
            }
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """
    Catch-all: no bare 500s with stack traces leaking to the client.
    Logs full context for debugging, returns generic message to client.
    """
    rid = request_id_ctx.get()
    logger.exception(
        "unhandled_exception",
        extra={"request_id": rid},
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "details": [],
            }
        },
    )


# ── Health Check ──────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok"}
