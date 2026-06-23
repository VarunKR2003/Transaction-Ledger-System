# Transaction Ledger System

A high-concurrency, idempotent transaction ledger system built with **FastAPI** (Python) and **React**.

This system handles financial transactions with strict guarantees on data consistency, idempotency, and concurrency, satisfying all requirements of the assignment.

## 🚀 How to Run the Project

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL (running locally or via Docker)

### 1. Database Setup
Ensure PostgreSQL is running and create a database named `ledger_system`.
Execute the SQL schema provided in `ASSUMPTIONS.md` to initialize the tables.

### 2. Backend Setup
Navigate to the `backend` directory:
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

### 3. Frontend Setup
Navigate to the `frontend` directory:
```bash
cd frontend
npm install
npm run dev
```
The frontend dashboard will be available at `http://localhost:5173`.

---

## 📡 API Documentation

### 1. `POST /transaction`
Records a transaction for a user.
- **Payload**: `{"userId": "1", "amount": "100.50", "idempotencyKey": "txn-uuid"}`
- **Responses**:
  - `201 Created`: Transaction processed successfully.
  - `200 OK`: Idempotent replay (the exact payload was already processed).
  - `409 Conflict`: Idempotency key reused with a different payload.
  - `422 Unprocessable Entity`: Invalid amount (e.g., zero, negative, or exceeding max limit).
  - `429 Too Many Requests`: Rate limit exceeded.

### 2. `GET /summary/:userId`
Retrieves aggregated transaction data for a specific user.
- **Responses**:
  - `200 OK`: Returns the user's current balance, transaction count, and status.
  - `404 Not Found`: User does not exist.

### 3. `GET /ranking`
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
`Score = (W_total * total_amount) + (W_freq * ln(1 + valid_count)) + (W_recency * exp(-λ * hours))`
1. **Total Volume:** Rewards raw financial balance.
2. **Frequency (Log-Dampened):** Rewards consistent usage but uses a logarithmic curve (`ln`) so the value of each additional transaction drops sharply, preventing spam abuse. Transactions under a specific threshold do not count toward this metric.
3. **Recency (Exponential Decay):** Rewards active users. Scores slowly "rot" or decay over time if the user becomes inactive.
