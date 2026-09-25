import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import type {
  AgentCard,
  AgentType,
  Receipt,
  ReviewEvent,
  ReviewRunDetail,
} from '../types';
import { AGENT_LABELS } from '../types';
import { ErrorMessage } from '../components/ErrorMessage';
import { Spinner } from '../components/Spinner';
import { VerdictBadge } from '../components/VerdictBadge';
import { SeverityBadge } from '../components/SeverityBadge';
import { StatusDot } from '../components/StatusDot';
import { RiskBadge } from '../components/RiskBadge';

// ---------------------------------------------------------------------------
// Agent card grid
// ---------------------------------------------------------------------------

const ALL_AGENTS: AgentType[] = [
  'test_runner',
  'catching_test',
  'documentation_check',
  'history_check',
];

function makeInitialCards(): AgentCard[] {
  return ALL_AGENTS.map((a) => ({
    agent_type: a,
    label: AGENT_LABELS[a] ?? a,
    status: 'pending',
    result: null,
    receipt_count: 0,
    duration_ms: null,
    started_at: null,
  }));
}

function AgentCardView({ card }: { card: AgentCard }) {
  const resultColor =
    card.result === 'PASS'
      ? 'text-green-700'
      : card.result === 'FAIL'
      ? 'text-red-700'
      : card.result === 'INSUFFICIENT_EVIDENCE'
      ? 'text-yellow-700'
      : card.result === 'ERROR' || card.result === 'TIMEOUT'
      ? 'text-red-700'
      : 'text-gray-500';

  return (
    <div className="card flex flex-col gap-2">
      <div className="flex justify-between items-start">
        <p className="text-sm font-medium text-gray-900">{card.label}</p>
        <StatusDot status={card.status} />
      </div>
      <div className="text-xs text-muted grid grid-cols-2 gap-x-4 gap-y-0.5">
        <div>
          <span className="text-muted">Result</span>
          <span className={`ml-1.5 font-semibold ${resultColor}`}>
            {card.result ?? '—'}
          </span>
        </div>
        <div>
          <span className="text-muted">Receipts</span>
          <span className="ml-1.5 text-gray-700">{card.receipt_count}</span>
        </div>
        <div>
          <span className="text-muted">Duration</span>
          <span className="ml-1.5 text-gray-700">
            {card.duration_ms != null
              ? `${(card.duration_ms / 1000).toFixed(1)}s`
              : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Receipt card
// ---------------------------------------------------------------------------

function ReceiptCard({ receipt }: { receipt: Receipt }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="card text-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium text-gray-900">{receipt.title}</p>
          <p className="text-muted text-xs mt-0.5">
            Agent:{' '}
            <code className="font-mono text-gray-700">
              {receipt.agent ?? receipt.agent_execution_id.slice(0, 8)}
            </code>
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <SeverityBadge severity={receipt.severity} />
          <span className="text-xs text-muted">
            {(receipt.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
        <div>
          <span className="text-muted">Result</span>
          <span
            className={`ml-2 font-semibold ${
              receipt.result_summary === 'PASS'
                ? 'text-green-700'
                : receipt.result_summary === 'FAIL'
                ? 'text-red-700'
                : 'text-yellow-700'
            }`}
          >
            {receipt.result_summary}
          </span>
        </div>
        {receipt.command && (
          <div>
            <span className="text-muted">Command</span>
            <code className="ml-2 font-mono text-gray-700">{receipt.command}</code>
          </div>
        )}
        {receipt.file_ref && (
          <div className="col-span-2">
            <span className="text-muted">File</span>
            <code className="ml-2 font-mono text-gray-700">{receipt.file_ref}</code>
          </div>
        )}
      </div>

      {receipt.raw_output && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-accent hover:underline"
          >
            {expanded ? 'Hide evidence ↑' : 'Show evidence ↓'}
          </button>
          {expanded && (
            <pre className="mt-2 bg-gray-950 text-green-400 text-xs font-mono p-3 rounded overflow-x-auto max-h-64 whitespace-pre-wrap">
              {receipt.raw_output}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event log strip
// ---------------------------------------------------------------------------

function EventLog({ events }: { events: ReviewEvent[] }) {
  if (events.length === 0) return null;
  return (
    <div className="mt-2 text-xs text-muted space-y-0.5 max-h-32 overflow-y-auto font-mono border border-border rounded p-2 bg-surface">
      {events.map((e, i) => (
        <div key={i} className="flex gap-2">
          <span className="text-gray-400 shrink-0">
            {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : ''}
          </span>
          <span className={e.event_type.includes('fail') ? 'text-red-600' : 'text-gray-600'}>
            {e.event_type}
          </span>
          {e.agent_type && <span className="text-accent">{e.agent_type as string}</span>}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PR Review page
// ---------------------------------------------------------------------------

export default function PRReview() {
  const [repo, setRepo] = useState('demo');
  const [prNumber, setPrNumber] = useState('1');
  const [prTitle, setPrTitle] = useState('Demo PR — calculator fixes');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReviewRunDetail | null>(null);
  const [cards, setCards] = useState<AgentCard[]>(makeInitialCards());
  const [liveEvents, setLiveEvents] = useState<ReviewEvent[]>([]);

  const esRef = useRef<EventSource | null>(null);

  // Close SSE on unmount
  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  function applyEvent(event: ReviewEvent, prevCards: AgentCard[]): AgentCard[] {
    const { event_type, agent_type } = event;
    if (!agent_type) return prevCards;

    return prevCards.map((c) => {
      if (c.agent_type !== agent_type) return c;
      switch (event_type) {
        case 'agent.started':
          return { ...c, status: 'running', started_at: Date.now() };
        case 'agent.completed':
          return {
            ...c,
            status: 'completed',
            result: (event.result as string) ?? c.result,
            duration_ms:
              c.started_at != null ? Date.now() - c.started_at : c.duration_ms,
          };
        case 'agent.failed':
          return {
            ...c,
            status: 'error',
            result: (event.result as string) ?? 'ERROR',
            duration_ms:
              c.started_at != null ? Date.now() - c.started_at : c.duration_ms,
          };
        case 'receipt.created':
          return { ...c, receipt_count: c.receipt_count + 1 };
        default:
          return c;
      }
    });
  }

  async function handleRunReview() {
    const prNum = parseInt(prNumber, 10);
    if (!repo.trim() || isNaN(prNum)) {
      setError('Repository name and a valid PR number are required.');
      return;
    }

    // Reset state
    setLoading(true);
    setError(null);
    setResult(null);
    setCards(makeInitialCards());
    setLiveEvents([]);
    esRef.current?.close();

    let runId: string;
    try {
      const run = await api.createReview(repo, prNum, { pr_title: prTitle || 'PR Review' });
      runId = run.id;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
      return;
    }

    // Open SSE stream BEFORE fetching the final result — the review runs
    // synchronously on the server in Phase 2, so by the time createReview
    // returns the run is already complete. We subscribe to replay the events.
    const es = api.streamReview(runId);
    esRef.current = es;

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as ReviewEvent;
        if (data.event_type === 'stream.end') {
          es.close();
          return;
        }
        setLiveEvents((prev) => [...prev, data]);
        setCards((prev) => applyEvent(data, prev));
      } catch {
        // malformed event — ignore
      }
    };

    es.onerror = () => {
      es.close();
    };

    // Fetch full detail (review is already completed synchronously)
    try {
      const detail = await api.getReview(runId);
      setResult(detail);
      // Reconcile card states from definitive agent_executions data
      setCards((prev) =>
        prev.map((card) => {
          const ae = detail.agent_executions.find(
            (a) => a.agent_type === card.agent_type
          );
          if (!ae) return card;
          const receipts = detail.receipts.filter(
            (r) => r.agent_execution_id === ae.id
          );
          return {
            ...card,
            status: ae.status,
            result: receipts[0]?.result_summary ?? card.result,
            receipt_count: receipts.length,
            duration_ms:
              ae.started_at && ae.completed_at
                ? new Date(ae.completed_at).getTime() -
                  new Date(ae.started_at).getTime()
                : card.duration_ms,
          };
        })
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">PR Review</h1>
        <p className="text-muted text-sm mt-1">
          Four parallel agents produce evidence receipts. Every finding is backed by real
          command output.
        </p>
      </div>

      {/* Input form */}
      <div className="card mb-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4 uppercase tracking-wide">
          Review Target
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-xs text-muted mb-1">Repository</label>
            <input
              type="text"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="demo"
              className="w-full text-sm border border-border rounded-md px-3 py-1.5 bg-white
                         focus:outline-none focus:ring-1 focus:ring-accent font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">PR Number</label>
            <input
              type="number"
              value={prNumber}
              onChange={(e) => setPrNumber(e.target.value)}
              min={1}
              className="w-full text-sm border border-border rounded-md px-3 py-1.5 bg-white
                         focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">PR Title</label>
            <input
              type="text"
              value={prTitle}
              onChange={(e) => setPrTitle(e.target.value)}
              placeholder="PR title"
              className="w-full text-sm border border-border rounded-md px-3 py-1.5 bg-white
                         focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRunReview}
            disabled={loading}
            className="btn-primary"
          >
            {loading ? (
              <>
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Running…
              </>
            ) : (
              'Run Review'
            )}
          </button>
          <span className="text-xs text-muted">
            Use <code className="font-mono">demo</code> repo for the local demo
          </span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6">
          <ErrorMessage message={error} onRetry={handleRunReview} />
        </div>
      )}

      {/* Loading */}
      {loading && !result && (
        <div className="mb-6">
          <Spinner label="Running four-agent review…" />
        </div>
      )}

      {/* Agent cards — always visible once a run is triggered */}
      {(loading || result) && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
              Agent Squad
            </h2>
            {result && (
              <RiskBadge risk={result.risk_level} />
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {cards.map((c) => (
              <AgentCardView key={c.agent_type} card={c} />
            ))}
          </div>
          {liveEvents.length > 0 && <EventLog events={liveEvents} />}
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-6">
          {/* Review summary */}
          <div className="card">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div>
                <h2 className="text-base font-semibold text-gray-900">Review Result</h2>
                <p className="text-xs text-muted mt-0.5">
                  Run ID: <code className="font-mono">{result.id}</code>
                </p>
              </div>
              <VerdictBadge verdict={result.verdict} />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted">Repository</p>
                <p className="font-mono text-gray-900 mt-0.5">{repo}</p>
              </div>
              <div>
                <p className="text-xs text-muted">PR Number</p>
                <p className="text-gray-900 mt-0.5">#{prNumber}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Risk Level</p>
                <div className="mt-0.5">
                  <RiskBadge risk={result.risk_level} />
                </div>
              </div>
              <div>
                <p className="text-xs text-muted">Confidence</p>
                <p className="text-gray-900 mt-0.5">
                  {result.confidence != null
                    ? `${(result.confidence * 100).toFixed(0)}%`
                    : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted">Status</p>
                <p className="text-gray-900 mt-0.5 capitalize">{result.status}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Duration</p>
                <p className="text-gray-900 mt-0.5">
                  {result.elapsed_ms != null ? `${result.elapsed_ms} ms` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted">Agents</p>
                <p className="text-gray-900 mt-0.5">
                  {result.agent_executions.length}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted">Receipts</p>
                <p className="text-gray-900 mt-0.5">{result.receipts.length}</p>
              </div>
            </div>
          </div>

          {/* Evidence receipts */}
          {result.receipts.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
                Evidence Receipts
                <span className="ml-2 text-xs font-normal text-muted">
                  {result.receipts.length} total
                </span>
              </h2>
              <div className="space-y-3">
                {result.receipts.map((r) => (
                  <ReceiptCard key={r.id} receipt={r} />
                ))}
              </div>
              <p className="mt-3 text-xs text-muted">
                ✓ Each receipt contains the exact command and output used to reach the verdict.
              </p>
            </div>
          )}

          <div className="text-xs text-muted">
            <Link to={`/reviews/${result.id}`} className="text-accent hover:underline">
              View full review details →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
