-- ============================================================================
-- Transaction Ledger System — Database Initialization Script
-- ============================================================================
-- This script is executed automatically by the PostgreSQL Docker container
-- on first startup. It creates all tables, indexes, types, and seeds the
-- initial user data for demonstration purposes.
-- ============================================================================

-- ── Custom ENUM type for transaction status ──────────────────────────────────
CREATE TYPE transaction_status AS ENUM ('completed', 'flagged', 'rejected');

-- ── Users table ──────────────────────────────────────────────────────────────
-- Stores user identity and denormalized summary counters.
-- Counters are updated atomically via SQL (total_amount = total_amount + delta)
-- to prevent race conditions during concurrent transactions.
CREATE TABLE users (
    id INT PRIMARY KEY,
    display_name TEXT NULL,
    total_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    valid_transaction_count INTEGER NOT NULL DEFAULT 0,
    last_transaction_at TIMESTAMPTZ NULL,
    is_flagged BOOLEAN NOT NULL DEFAULT FALSE,
    flagged_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Transactions table ───────────────────────────────────────────────────────
-- Immutable ledger of all transactions. The UNIQUE constraint on
-- idempotency_key is the database-level mechanism that prevents duplicate
-- processing, even under concurrent race conditions.
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount NUMERIC(18,2) NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status transaction_status NOT NULL DEFAULT 'completed',
    counts_toward_ranking BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    client_timestamp TIMESTAMPTZ NULL
);

-- ── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX ix_transactions_user_created ON transactions(user_id, created_at);
CREATE INDEX ix_users_ranking ON users(total_amount, last_transaction_at);

-- ============================================================================
-- Seed Data: Pre-provisioned users for demonstration
-- ============================================================================
INSERT INTO users (
    id,
    display_name,
    total_amount,
    transaction_count,
    valid_transaction_count,
    last_transaction_at,
    is_flagged,
    flagged_reason
) VALUES
(
    1,
    'Varun',
    18450.75,
    42,
    39,
    '2026-06-21 18:42:11+05:30',
    FALSE,
    NULL
),
(
    2,
    'Nila Varma',
    9720.00,
    18,
    17,
    '2026-06-20 14:10:35+05:30',
    FALSE,
    NULL
),
(
    3,
    'Dev Shah',
    50210.90,
    87,
    81,
    '2026-06-22 08:55:19+05:30',
    FALSE,
    NULL
),
(
    4,
    'Meera Nair',
    1250.00,
    9,
    7,
    '2026-06-18 21:24:02+05:30',
    FALSE,
    NULL
),
(
    5,
    'Rohan Iyer',
    0.00,
    3,
    0,
    '2026-06-12 13:07:44+05:30',
    TRUE,
    'Repeated low-value test activity and no valid ranking transactions'
),
(
    6,
    'Tara Joseph',
    66180.25,
    103,
    97,
    '2026-06-22 20:16:58+05:30',
    FALSE,
    NULL
);
