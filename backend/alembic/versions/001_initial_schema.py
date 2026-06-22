"""Initial schema: users and transactions tables

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Users table ───────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.String(255), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "total_amount",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "transaction_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "valid_transaction_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_transaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_flagged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("flagged_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index("ix_users_user_id", "users", ["user_id"], unique=True)
    op.create_index(
        "ix_users_ranking",
        "users",
        ["total_amount", "last_transaction_at"],
    )

    # ── Transactions table ────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'completed'"),
        ),
        sa.Column(
            "counts_toward_ranking",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index(
        "ix_transactions_user_created",
        "transactions",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_transactions_idempotency_key",
        "transactions",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("users")
