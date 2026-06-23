import { useState, useRef, useCallback } from 'react';
import { postTransaction, getSummary, getRanking } from './api';

// ── Mock users ────────────────────────────────────────────────────────────
const USERS = [
  { id: '1', label: 'User 1' },
  { id: '2', label: 'User 2' },
  { id: '3', label: 'User 3' },
  { id: '4', label: 'User 4' },
  { id: '5', label: 'User 5' },
  { id: '6', label: 'User 6' },
];

// Unique key generator
let keyCounter = 0;
function genKey(prefix = 'txn') {
  return `${prefix}-${Date.now()}-${++keyCounter}`;
}

function timestamp() {
  return new Date().toLocaleTimeString('en-US', { hour12: false });
}

export default function App() {
  // ── State ───────────────────────────────────────────────────────────────
  const [activeUser, setActiveUser] = useState(USERS[0].id);
  const [amount, setAmount] = useState('100');
  const [idempotencyKey, setIdempotencyKey] = useState(() => genKey());
  const [submitting, setSubmitting] = useState(false);

  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const [ranking, setRanking] = useState(null);
  const [rankingLoading, setRankingLoading] = useState(false);

  const [logs, setLogs] = useState([]);

  // Concurrency tester
  const [concCount, setConcCount] = useState(5);
  const [concAmount, setConcAmount] = useState('50');
  const [concRunning, setConcRunning] = useState(false);

  // Cross-user concurrency
  const [crossUsers, setCrossUsers] = useState(['1', '2']);
  const [crossAmount, setCrossAmount] = useState('100');
  const [crossRunning, setCrossRunning] = useState(false);

  const logIdRef = useRef(0);

  // ── Logging ─────────────────────────────────────────────────────────────
  const addLog = useCallback((type, message) => {
    setLogs((prev) => [
      { id: ++logIdRef.current, type, message, time: timestamp() },
      ...prev.slice(0, 99),
    ]);
  }, []);

  // ── Submit Transaction ──────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { data, status } = await postTransaction({
        userId: activeUser,
        amount,
        idempotencyKey,
      });
      if (status === 200) {
        addLog(
          'warning',
          `<strong>Idempotent replay</strong> for user ${activeUser} — key "${idempotencyKey}" already processed`
        );
      } else {
        addLog(
          'success',
          `<strong>Transaction created</strong> for user ${activeUser} — amount: ${amount}, balance: ${data.summary.totalAmount}`
        );
      }
      setIdempotencyKey(genKey());
    } catch (err) {
      addLog('error', `<strong>Failed</strong> for user ${activeUser}: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  // ── Fetch Summary ──────────────────────────────────────────────────────
  const handleFetchSummary = async () => {
    setSummaryLoading(true);
    try {
      const data = await getSummary(activeUser);
      setSummary(data);
      addLog('info', `Fetched summary for user ${activeUser}`);
    } catch (err) {
      setSummary(null);
      addLog('error', `Summary fetch failed: ${err.message}`);
    } finally {
      setSummaryLoading(false);
    }
  };

  // ── Fetch Ranking ──────────────────────────────────────────────────────
  const handleFetchRanking = async () => {
    setRankingLoading(true);
    try {
      const data = await getRanking();
      setRanking(data);
      addLog('info', `Fetched leaderboard — ${data.rankings.length} entries`);
    } catch (err) {
      setRanking(null);
      addLog('error', `Ranking fetch failed: ${err.message}`);
    } finally {
      setRankingLoading(false);
    }
  };

  // ── Concurrency Test: Same User ────────────────────────────────────────
  const handleConcurrencyTest = async () => {
    setConcRunning(true);
    addLog(
      'info',
      `<strong>Concurrency test:</strong> firing ${concCount} simultaneous transactions as user ${activeUser}, amount ${concAmount} each`
    );

    const promises = Array.from({ length: Number(concCount) }, (_, i) => {
      const key = genKey(`conc-${activeUser}`);
      return postTransaction({
        userId: activeUser,
        amount: concAmount,
        idempotencyKey: key,
      })
        .then(({ data, status }) => ({
          ok: true,
          i,
          status,
          balance: data.summary.totalAmount,
        }))
        .catch((err) => ({ ok: false, i, error: err.message }));
    });

    const results = await Promise.all(promises);
    const succeeded = results.filter((r) => r.ok).length;
    const failed = results.filter((r) => !r.ok).length;

    const lastBalance = results
      .filter((r) => r.ok)
      .sort((a, b) => b.i - a.i)[0]?.balance;

    addLog(
      succeeded > 0 ? 'success' : 'error',
      `<strong>Concurrency result:</strong> ${succeeded} succeeded, ${failed} failed. Latest balance: ${lastBalance ?? 'N/A'}`
    );

    setConcRunning(false);
  };

  // ── Concurrency Test: Cross-User ───────────────────────────────────────
  const handleCrossUserTest = async () => {
    setCrossRunning(true);
    addLog(
      'info',
      `<strong>Cross-user test:</strong> submitting simultaneously as users [${crossUsers.join(', ')}], amount ${crossAmount}`
    );

    const promises = crossUsers.map((uid) => {
      const key = genKey(`cross-${uid}`);
      return postTransaction({
        userId: uid,
        amount: crossAmount,
        idempotencyKey: key,
      })
        .then(({ data }) => ({
          ok: true,
          userId: uid,
          balance: data.summary.totalAmount,
        }))
        .catch((err) => ({ ok: false, userId: uid, error: err.message }));
    });

    const results = await Promise.all(promises);

    results.forEach((r) => {
      if (r.ok) {
        addLog(
          'success',
          `User ${r.userId} → balance: ${r.balance}`
        );
      } else {
        addLog('error', `User ${r.userId} → ${r.error}`);
      }
    });

    setCrossRunning(false);
  };

  const toggleCrossUser = (uid) => {
    setCrossUsers((prev) =>
      prev.includes(uid)
        ? prev.filter((u) => u !== uid)
        : [...prev, uid]
    );
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <h1>Transaction Ledger</h1>
        <p>Concurrency-safe ledger testing dashboard</p>
      </header>

      {/* User Selector */}
      <div className="user-selector-bar" id="user-selector">
        <span className="label">Acting as:</span>
        {USERS.map((u) => (
          <button
            key={u.id}
            className={`user-chip ${activeUser === u.id ? 'active' : ''}`}
            onClick={() => setActiveUser(u.id)}
            id={`user-chip-${u.id}`}
          >
            <span className="user-dot"></span>
            {u.label}
          </button>
        ))}
      </div>

      {/* Main Panels */}
      <div className="panels-grid">
        {/* ── Submit Transaction Panel ─────────────────────────────────── */}
        <div className="card" id="submit-panel">
          <div className="card-header">
            <h2><span className="icon">⚡</span> Submit Transaction</h2>
            <span className="badge badge-info">User {activeUser}</span>
          </div>
          <div className="card-body">
            <form onSubmit={handleSubmit}>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Amount</label>
                  <input
                    type="text"
                    className="form-input"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="e.g. 150.50 or -25"
                    id="input-amount"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Idempotency Key</label>
                  <input
                    type="text"
                    className="form-input"
                    value={idempotencyKey}
                    onChange={(e) => setIdempotencyKey(e.target.value)}
                    placeholder="Auto-generated"
                    id="input-idempotency-key"
                  />
                </div>
              </div>
              <div className="form-group" style={{ marginTop: 16 }}>
                <button
                  type="submit"
                  className="btn btn-primary btn-block"
                  disabled={submitting || !amount}
                  id="btn-submit-txn"
                >
                  {submitting ? (
                    <>
                      <span className="spinner"></span> Submitting…
                    </>
                  ) : (
                    'Submit Transaction'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* ── Summary Panel ────────────────────────────────────────────── */}
        <div className="card" id="summary-panel">
          <div className="card-header">
            <h2><span className="icon">📊</span> User Summary</h2>
            <button
              className="btn btn-outline btn-sm"
              onClick={handleFetchSummary}
              disabled={summaryLoading}
              id="btn-fetch-summary"
            >
              {summaryLoading ? <span className="spinner"></span> : 'Refresh'}
            </button>
          </div>
          <div className="card-body">
            {summary ? (
              <div className="stats-grid">
                <div className="stat-item">
                  <div className="stat-label">User ID</div>
                  <div className="stat-value">{summary.userId}</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Total Amount</div>
                  <div
                    className={`stat-value ${
                      parseFloat(summary.totalAmount) >= 0
                        ? 'positive'
                        : 'negative'
                    }`}
                  >
                    {summary.totalAmount}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Transactions</div>
                  <div className="stat-value">{summary.transactionCount}</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Valid Txns</div>
                  <div className="stat-value">
                    {summary.validTransactionCount}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Flagged</div>
                  <div className="stat-value">
                    {summary.isFlagged ? (
                      <span className="badge badge-error">Yes</span>
                    ) : (
                      <span className="badge badge-success">No</span>
                    )}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Last Txn</div>
                  <div className="stat-value" style={{ fontSize: '0.8rem' }}>
                    {summary.lastTransactionAt
                      ? new Date(summary.lastTransactionAt).toLocaleString()
                      : '—'}
                  </div>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <div className="icon">📋</div>
                <p>Click Refresh to load summary for User {activeUser}</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Concurrency Tester ───────────────────────────────────────── */}
        <div className="card full-width" id="concurrency-panel">
          <div className="card-header">
            <h2><span className="icon">🔥</span> Concurrency Tester</h2>
          </div>
          <div className="card-body">
            {/* Same-user burst */}
            <div className="concurrency-section">
              <p
                style={{
                  fontSize: '0.82rem',
                  color: 'var(--text-secondary)',
                  marginBottom: 12,
                }}
              >
                <strong>Same-user burst:</strong> Fire N simultaneous
                transactions as User {activeUser} to test atomic increments.
              </p>
              <div className="concurrency-controls">
                <div className="form-group">
                  <label className="form-label">Count</label>
                  <input
                    type="number"
                    className="form-input"
                    value={concCount}
                    onChange={(e) => setConcCount(e.target.value)}
                    min="1"
                    max="50"
                    id="input-conc-count"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Amount Each</label>
                  <input
                    type="text"
                    className="form-input"
                    value={concAmount}
                    onChange={(e) => setConcAmount(e.target.value)}
                    id="input-conc-amount"
                  />
                </div>
                <button
                  className="btn btn-success"
                  onClick={handleConcurrencyTest}
                  disabled={concRunning}
                  id="btn-conc-test"
                >
                  {concRunning ? (
                    <>
                      <span className="spinner"></span> Running…
                    </>
                  ) : (
                    `Fire ${concCount} Transactions`
                  )}
                </button>
              </div>
            </div>

            <hr
              style={{
                border: 'none',
                borderTop: '1px solid var(--border)',
                margin: '20px 0',
              }}
            />

            {/* Cross-user isolation */}
            <div className="concurrency-section">
              <p
                style={{
                  fontSize: '0.82rem',
                  color: 'var(--text-secondary)',
                  marginBottom: 12,
                }}
              >
                <strong>Cross-user isolation:</strong> Submit one transaction
                per selected user simultaneously to verify isolation.
              </p>
              <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                {USERS.map((u) => (
                  <button
                    key={u.id}
                    className={`user-chip ${
                      crossUsers.includes(u.id) ? 'active' : ''
                    }`}
                    onClick={() => toggleCrossUser(u.id)}
                    id={`cross-user-chip-${u.id}`}
                  >
                    <span className="user-dot"></span>
                    {u.label}
                  </button>
                ))}
              </div>
              <div className="concurrency-controls">
                <div className="form-group">
                  <label className="form-label">Amount Each</label>
                  <input
                    type="text"
                    className="form-input"
                    value={crossAmount}
                    onChange={(e) => setCrossAmount(e.target.value)}
                    id="input-cross-amount"
                  />
                </div>
                <button
                  className="btn btn-success"
                  onClick={handleCrossUserTest}
                  disabled={crossRunning || crossUsers.length === 0}
                  id="btn-cross-test"
                >
                  {crossRunning ? (
                    <>
                      <span className="spinner"></span> Running…
                    </>
                  ) : (
                    `Fire for ${crossUsers.length} Users`
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Leaderboard ──────────────────────────────────────────────── */}
        <div className="card" id="ranking-panel">
          <div className="card-header">
            <h2><span className="icon">🏆</span> Leaderboard</h2>
            <button
              className="btn btn-outline btn-sm"
              onClick={handleFetchRanking}
              disabled={rankingLoading}
              id="btn-fetch-ranking"
            >
              {rankingLoading ? <span className="spinner"></span> : 'Refresh'}
            </button>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {ranking && ranking.rankings.length > 0 ? (
              <table className="leaderboard-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>User</th>
                    <th>Score</th>
                    <th>Amount</th>
                    <th>Txns</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.rankings.map((entry) => (
                    <tr key={entry.userId}>
                      <td
                        className={`rank-cell ${
                          entry.rank <= 3 ? `rank-${entry.rank}` : ''
                        }`}
                      >
                        {entry.rank <= 3
                          ? ['🥇', '🥈', '🥉'][entry.rank - 1]
                          : entry.rank}
                      </td>
                      <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        {entry.displayName || `User ${entry.userId}`}
                      </td>
                      <td className="score-cell">
                        {entry.compositeScore.toFixed(2)}
                      </td>
                      <td className="amount-cell">{entry.totalAmount}</td>
                      <td>{entry.validTransactionCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">
                <div className="icon">🏆</div>
                <p>Click Refresh to load the leaderboard</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Activity Log ─────────────────────────────────────────────── */}
        <div className="card" id="log-panel">
          <div className="card-header">
            <h2><span className="icon">📜</span> Activity Log</h2>
            {logs.length > 0 && (
              <button
                className="btn btn-outline btn-sm"
                onClick={() => setLogs([])}
                id="btn-clear-log"
              >
                Clear
              </button>
            )}
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {logs.length > 0 ? (
              <div className="log-container">
                {logs.map((log) => (
                  <div key={log.id} className={`log-entry ${log.type}`}>
                    <span className="log-time">{log.time}</span>
                    <span
                      className="log-message"
                      dangerouslySetInnerHTML={{ __html: log.message }}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="icon">📜</div>
                <p>Actions will appear here</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
