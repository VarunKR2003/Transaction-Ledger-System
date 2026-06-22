"""
Application configuration via environment variables.

All configurable constants are surfaced here — no magic numbers buried in logic.
"""

from decimal import Decimal
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Central configuration, loaded from environment variables or .env file.
    Every tunable parameter lives here with a documented default.
    """

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/transaction_ledger",
        description="Async SQLAlchemy database URL",
    )

    # ── Transaction Constraints ───────────────────────────────────────────
    MAX_TRANSACTION_AMOUNT: Decimal = Field(
        default=Decimal("1000000.00"),
        description="Maximum allowed transaction amount (absolute value). "
                    "Acts as a fat-finger / abuse guard.",
    )
    MIN_TRANSACTION_AMOUNT_FOR_RANKING: Decimal = Field(
        default=Decimal("1.00"),
        description="Minimum |amount| for a transaction to count toward the "
                    "frequency term in ranking. Prevents gaming via micro-transactions.",
    )
    ALLOW_NEGATIVE_AMOUNTS: bool = Field(
        default=True,
        description="Whether negative amounts (refunds/debits) are accepted.",
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_MAX_REQUESTS: int = Field(
        default=10,
        description="Maximum transactions per user within the sliding window.",
    )
    RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        description="Sliding window size in seconds for per-user rate limiting.",
    )

    # ── Ranking Weights ───────────────────────────────────────────────────
    RANKING_WEIGHT_TOTAL: float = Field(
        default=0.5,
        description="Weight for the raw total_amount component in composite score.",
    )
    RANKING_WEIGHT_FREQUENCY: float = Field(
        default=0.3,
        description="Weight for the dampened frequency component: log(1 + valid_count).",
    )
    RANKING_WEIGHT_RECENCY: float = Field(
        default=0.2,
        description="Weight for the recency component: exp(-λ * hours_since_last).",
    )
    RANKING_DECAY_LAMBDA: float = Field(
        default=0.01,
        description="Exponential decay rate (per hour) for recency weighting.",
    )

    # ── Pagination Defaults ───────────────────────────────────────────────
    DEFAULT_PAGE_LIMIT: int = Field(default=20, description="Default page size.")
    MAX_PAGE_LIMIT: int = Field(default=100, description="Maximum page size.")

    # ── CORS ──────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins for the frontend dev server.",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton instance — import this everywhere
settings = Settings()
