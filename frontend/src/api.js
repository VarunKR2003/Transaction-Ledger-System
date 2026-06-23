/**
 * API client for the Transaction Ledger backend.
 * All endpoints hit the FastAPI server at /api/*.
 */

const BASE = '/api';

/**
 * POST /api/transaction
 * @param {{ userId: string, amount: string, idempotencyKey: string }} payload
 */
export async function postTransaction({ userId, amount, idempotencyKey }) {
  const payload = { userId, amount, idempotencyKey };
  console.log('[DEBUG] Sending POST /transaction:', JSON.stringify(payload));

  let res;
  try {
    res = await fetch(`${BASE}/transaction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (fetchErr) {
    console.error('[DEBUG] fetch() itself threw:', fetchErr);
    throw fetchErr;
  }

  console.log('[DEBUG] Response status:', res.status);
  const rawText = await res.text();
  console.log('[DEBUG] Raw response body:', rawText);

  let data;
  try {
    data = JSON.parse(rawText);
  } catch (parseErr) {
    console.error('[DEBUG] Response is NOT JSON:', rawText);
    throw new Error(`HTTP ${res.status}: ${rawText}`);
  }

  if (!res.ok) {
    const msg = data?.error?.message || `HTTP ${res.status}`;
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
