# Transaction Ledger System

A high-concurrency, idempotent transaction ledger system built with **FastAPI** (Python), **PostgreSQL**, and **React**.

This system handles financial transactions with strict guarantees on data consistency, idempotency, and concurrency, satisfying all requirements of the assignment.

## 🚀 How to Run the Project

### Option 1: Docker (Recommended — One Command)

> **Prerequisites:** [Docker](https://www.docker.com/products/docker-desktop/) installed and running.

```bash
git clone <repo-url>
cd Transaction-Ledger-System
docker compose up --build
```

That's it. This will automatically:
1. Start a **PostgreSQL 16** database container
2. Execute `db/init.sql` to create all tables, indexes, and seed 6 demo users
3. Start the **FastAPI** backend on port `8000`
4. Build and serve the **React** frontend via Nginx on port `3000`

Open **http://localhost:3000** in your browser to use the application.

To stop and clean up:
```bash
docker compose down           # Stop containers
docker compose down -v        # Stop containers AND delete database volume
```

---

## 🎯 Evaluation Guide (For Recruiters)

Once the application is running via Docker, open **http://localhost:3000** to access the interactive testing dashboard. Here is how you can evaluate the core requirements:

### 1. Test Data Consistency
- Select **User 1**.
- Submit a transaction for `150.50`.
- Click **Refresh** on the User Summary panel to see the `Total Amount` and `Transactions` count update instantly.

### 2. Test Idempotency (Duplicate Prevention)
- Check the **"🔒 Lock key"** box to freeze the Idempotency Key.
- Click **Submit Transaction** multiple times.
- Notice the Activity Log: The first request returns a success, but all subsequent clicks return a `warning` indicating an Idempotent Replay. The user's balance is only charged once.

### 3. Test Concurrency (Race Conditions)
- Scroll down to the **Concurrency Tester**.
- Under *Same-user burst*, set Count to `20` and Amount to `50`.
- Click **Fire 20 Transactions**.
- The frontend will fire all 20 requests simultaneously. Because the backend uses **PostgreSQL Row-Level Locking**, you will see exactly 20 successes and the balance will mathematically perfectly increase by exactly `1000`, with zero lost updates.

### 4. Test Fairness Ranking
- Scroll down to the **Leaderboard** and click **Refresh**.
- You will see users ranked by a composite score that mathematically blends Volume, Frequency (with logarithmic dampening to prevent spam), and Recency (exponential decay).

---

### Option 2: Manual Setup (Local Development)

#### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL (running locally)

#### 1. Database Setup
Ensure PostgreSQL is running and create a database named `ledger_system`.
Execute the SQL schema:
```bash
psql -U postgres -d ledger_system -f db/init.sql
```

#### 2. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```
Create a `.env` file in the `backend` directory:
```env
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/ledger_system
```
Run the server:
```bash
uvicorn app.main:app --reload
```
The API will be available at `http://127.0.0.1:8000/api`.

#### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
The frontend dashboard will be available at `http://localhost:5173`.

---

## 📡 API Documentation

### 1. `POST /api/transaction`
Records a transaction for a user.
- **Payload**: `{"userId": "1", "amount": "100.50", "idempotencyKey": "txn-uuid"}`
- **Responses**:
  - `201 Created`: Transaction processed successfully.
  - `200 OK`: Idempotent replay (the exact payload was already processed).
  - `409 Conflict`: Idempotency key reused with a different payload.
  - `422 Unprocessable Entity`: Invalid amount (e.g., zero, negative, or exceeding max limit).
  - `429 Too Many Requests`: Rate limit exceeded.

### 2. `GET /api/summary/:userId`
Retrieves aggregated transaction data for a specific user.
- **Responses**:
  - `200 OK`: Returns the user's current balance, transaction count, and status.
  - `404 Not Found`: User does not exist.

### 3. `GET /api/ranking`
Retrieves a paginated leaderboard of users.
- **Query Params**: `?limit=20&offset=0`
- **Response**: `200 OK` with a list of ranked users and their composite scores.

---

## 🛡️ Core Mechanics & Logic

### How Duplicate Requests Are Prevented (Idempotency)
To protect against network failures where a client might retry a request, every transaction requires a unique `idempotencyKey`.
1. **Database Constraint:** The `transactions` table has a `UNIQUE` constraint on `idempotency_key`.
2. **ON CONFLICT:** The backend uses a PostgreSQL `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` statement.
3. **Collision Handling:** If a collision occurs, the system checks the payload. If the `userId` and `amount` match the original request, it safely returns a `200 OK` (Replay). If the payload differs, it rejects the request with a `409 Conflict` to prevent tampering.

### How Concurrency is Handled Safely
We do **not** use application-level Read-Modify-Write (which causes race conditions). Instead, user balances are updated via an **Atomic SQL Statement**:
```sql
UPDATE users SET total_amount = total_amount + :amount WHERE id = :uid
```
This forces the database engine to acquire a **Row-Level Lock**. If 10 concurrent requests arrive for the same user in the same millisecond, PostgreSQL processes them sequentially at the database tier, ensuring zero lost updates. Requests for *different* users do not block each other and execute in parallel.

### How Ranking is Calculated (Fairness Logic)
The leaderboard is designed to prevent manipulation (e.g., spamming 10,000 $0.01 transactions to get to rank #1). 
The composite score is calculated dynamically in SQL using this formula:

```
Score = (W_total × total_amount) + (W_freq × ln(1 + valid_count)) + (W_recency × exp(-λ × hours))
```

1. **Total Volume:** Rewards raw financial balance.
2. **Frequency (Log-Dampened):** Rewards consistent usage but uses a logarithmic curve (`ln`) so the value of each additional transaction drops sharply, preventing spam abuse. Transactions under a configurable minimum threshold do not count toward this metric.
3. **Recency (Exponential Decay):** Rewards active users. Scores slowly "rot" or decay over time if the user becomes inactive, allowing active participants to rise in the rankings.

---

## 📁 Project Structure

```
Transaction-Ledger-System/
├── docker-compose.yml          # One-command orchestration
├── db/
│   └── init.sql                # Schema + seed data (auto-executed by Docker)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI entry point, middleware, error handlers
│       ├── config.py           # All tunable parameters (weights, limits, thresholds)
│       ├── database.py         # Async SQLAlchemy engine & session factory
│       ├── models.py           # ORM models (User, Transaction)
│       ├── schemas.py          # Pydantic request/response schemas
│       ├── exceptions.py       # Centralized error hierarchy
│       ├── middleware.py       # Request ID middleware (pure ASGI)
│       ├── routes/
│       │   ├── transactions.py # POST /transaction
│       │   ├── summary.py      # GET /summary/:userId
│       │   └── ranking.py      # GET /ranking
│       └── services/
│           ├── transaction_service.py  # Core business logic
│           └── rate_limiter.py         # Sliding-window rate limiter
└── frontend/
    ├── Dockerfile
    ├── nginx.conf              # Reverse proxy config for /api
    └── src/
        ├── App.jsx             # Main dashboard with concurrency testing UI
        └── api.js              # API client module
```
