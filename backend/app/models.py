"""
SQLAlchemy 2.0 ORM models.

Two tables:
  - users:        identity + denormalized summary counters (atomic-increment only)
  - transactions: immutable ledger rows, one per successful transaction

Design notes:
  - total_amount uses NUMERIC(18,2) — never FLOAT — to avoid rounding drift.
  - Denormalized counters on `users` are updated via atomic SQL increment
    (SET x = x + delta), never read-modify-write in Python.
  - idempotency_key has a UNIQUE constraint at the DB level as the actual
    dedup mechanism that survives race conditions.
  - counts_toward_ranking is computed once at insert time based on the
    MIN_AMOUNT_THRESHOLD config, stored for efficient ranking queries.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )

    # ── Denormalized summary counters (atomic increment only) ─────────────
    total_amount: Mapped[float] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0"),
    )
    transaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    valid_transaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    last_transaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Abuse / manipulation flags ────────────────────────────────────────
    is_flagged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    flagged_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────────────────
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_users_ranking",
            "total_amount",
            "last_transaction_at",
            postgresql_using="btree",
        ),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(
        Numeric(18, 2), nullable=False,
    )
    # Client-supplied dedup key — the UNIQUE constraint is the actual
    # mechanism that prevents duplicate processing under race conditions.
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        postgresql.ENUM("completed", "flagged", "rejected", name="transaction_status", create_type=False),
        nullable=False,
        server_default=text("'completed'"),
    )
    # Computed once at insert time: abs(amount) >= MIN_AMOUNT_THRESHOLD
    counts_toward_ranking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    # Server-authoritative timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    # Optional client timestamp — for audit only, never trusted for logic
    client_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_user_created", "user_id", "created_at"),
    )
