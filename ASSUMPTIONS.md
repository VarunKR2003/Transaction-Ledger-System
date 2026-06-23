# Assumptions & Design Decisions

This document outlines the core technical assumptions, design choices, and the database schema used in the Transaction Ledger System.

## 1. Database Schema & Data Flow
Instead of using in-memory mock data, we utilized a robust PostgreSQL schema to leverage row-level locking, ACID transactions, and atomic constraints. 

Below is the exact schema driving the application data flow:

```sql
CREATE TABLE users (
    id int PRIMARY KEY,
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

CREATE TYPE transaction_status AS ENUM ('completed', 'flagged', 'rejected');

CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id int NOT NULL REFERENCES users(id),
    amount NUMERIC(18,2) NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status transaction_status NOT NULL,
    counts_toward_ranking BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    client_timestamp TIMESTAMPTZ NULL
);

-- Indexes for performance
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_users_composite_score_data ON users(is_flagged, transaction_count, total_amount, valid_transaction_count, last_transaction_at);
```

*(Note: Providing this schema definition explicitly defines the data flow and constraints, allowing evaluators to see the exact structure without needing a raw mock data dump).*

## 2. Design Assumptions

### User Provisioning & Identity
**Assumption:** In a real-world scenario, user accounts are created via an external Authentication/Identity service before transactions occur. 
**Implementation:** The system relies on a pre-provisioned set of users. The database initialization script (`init.sql`) seeds the database with 6 test users via Docker. The backend explicitly raises a `404 User Not Found` error if a transaction is submitted for a user ID that does not exist in the database, strictly enforcing referential integrity.

### Denormalized Counters
**Assumption:** Calculating a user's total balance dynamically by summing up all historical rows in the `transactions` table (`SUM(amount)`) becomes heavily bottlenecked at scale.
**Implementation:** We denormalize the `total_amount` and `transaction_count` directly onto the `users` table. This allows `GET /summary` and `GET /ranking` to respond in $O(1)$ time per user. Data consistency is mathematically guaranteed because the backend updates these counters in the exact same atomic transaction block as the `INSERT` to the transactions table.

### Zero-Amount and Negative Transactions
**Assumption:** Transactions of `0` amount are considered "no-ops" that clutter the database without providing financial value.
**Implementation:** A `$0` amount is rejected via a `422 Unprocessable Entity` exception. Negative amounts (refunds/debits) are allowed by the database schema but are guarded by an environment configuration variable (`ALLOW_NEGATIVE_AMOUNTS`), allowing the business logic to easily toggle this behavior.

### Handling Concurrency
**Assumption:** Python-level `asyncio` locks are insufficient because production environments typically run multiple worker processes (e.g., Gunicorn/Uvicorn with 4+ workers) or span across multiple physical servers.
**Implementation:** Concurrency management is pushed entirely to the database engine. We rely on PostgreSQL `Row-Level Locking` and atomic increments (`total_amount = total_amount + :amount`). The database guarantees serialization of concurrent requests to the same user row, completely preventing "lost update" race conditions.

### Idempotency Key Scope & Generation
**Assumption:** An idempotency key represents a single, unique user intent (e.g., clicking "Pay" once).
**Implementation:** The frontend generates cryptographically secure `UUID v4` keys (`self.crypto.randomUUID()`) for every transaction to guarantee global uniqueness. If a key is reused with the **exact same payload** (`userId` and `amount`), the backend treats it as a safe network retry (`200 OK`). If the payload is modified (e.g. someone tries to change the amount of an already submitted transaction), it is treated as a malicious request and raises a `409 Conflict`.

### Infrastructure & Deployment
**Assumption:** Evaluators need a frictionless, zero-configuration way to run the entire stack without manually installing Python packages, Node modules, or configuring local databases.
**Implementation:** The entire application is containerized using Docker Compose. Running `docker compose up -d` is the only step required — it orchestrates the PostgreSQL database (auto-seeded with schema and demo users via `init.sql`), the FastAPI backend, and an Nginx server serving the React frontend. Once the containers are up, the evaluator simply opens `http://localhost:3000` in a browser to access the full application. Manual setup instructions (Python venv, npm, local Postgres) are also documented as an alternative for local development.
