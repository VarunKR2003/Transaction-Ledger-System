/**
 * API client for the Transaction Ledger backend.
 * All endpoints hit the FastAPI server at /api/*.
 */

const BASE = 'http://localhost:8000/api';

/**
 * POST /api/transaction
 * @param {{ userId: string, amount: string, idempotencyKey: string }} payload
 */
export async function postTransaction({ userId, amount, idempotencyKey }) {
  const res = await fetch(`${BASE}/transaction`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      userId,
      amount,
      idempotencyKey,
    }),
  });

  const data = await res.json();
  if (!res.ok) {
    const msg =
      data?.error?.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.code = data?.error?.code;
    err.details = data?.error?.details;
    throw err;
  }
  return { data, status: res.status };
}

/**
 * GET /api/summary/:userId
 */
export async function getSummary(userId) {
  const res = await fetch(`${BASE}/summary/${encodeURIComponent(userId)}`);
  const data = await res.json();
  if (!res.ok) {
    const msg = data?.error?.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

/**
 * GET /api/ranking
 */
export async function getRanking(limit = 20, offset = 0) {
  const res = await fetch(
    `${BASE}/ranking?limit=${limit}&offset=${offset}`
  );
  const data = await res.json();
  if (!res.ok) {
    const msg = data?.error?.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}
