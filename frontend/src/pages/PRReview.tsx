import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import type {
  AgentCard,
  AgentType,
  ReviewEvent,
  ReviewRunDetail,
} from '../types';
import { AGENT_LABELS } from '../types';
import { VerdictBadge } from '../components/VerdictBadge';
import { SeverityBadge } from '../components/SeverityBadge';
import { RiskBadge } from '../components/RiskBadge';
import { TerminalViewer } from '../components/TerminalViewer';
import { Spinner } from '../components/Spinner';
import {
  Zap,
  Play,
  ShieldCheck,
  AlertTriangle,
  Terminal,
  ArrowRight,
  Cpu,
  Layers
} from 'lucide-react';

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
  const isRunning = card.status === 'running';
  const isCompleted = card.status === 'completed';
  const isError = card.status === 'error' || card.status === 'timeout';

  return (
    <div className={`p-4 rounded-2xl border transition-all duration-300 ${
      isRunning
        ? 'bg-brand-100 border-brand-400 shadow-soft-xl animate-pulse-glow'
        : isCompleted
        ? 'bg-white border-brand-200/80 shadow-sm'
        : isError
        ? 'bg-rose-50 border-rose-200'
        : 'bg-white/60 border-brand-100 text-brand-400'
    }`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-semibold text-xs text-brand-950 flex items-center gap-1.5">
          <Cpu className={`w-3.5 h-3.5 ${isRunning ? 'text-brand-600 animate-spin' : 'text-brand-400'}`} />
          {card.label}
        </span>
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
          isRunning
            ? 'bg-brand-900 text-white'
            : isCompleted
            ? 'bg-emerald-100 text-emerald-800'
            : isError
            ? 'bg-rose-100 text-rose-800'
            : 'bg-brand-100 text-brand-500'
        }`}>
          {card.status}
        </span>
      </div>

      <div className="space-y-1 text-xs text-brand-700 font-mono">
        <div className="flex justify-between">
          <span className="font-sans text-brand-500">Verdict</span>
          <span className="font-semibold text-brand-900">{card.result ?? '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="font-sans text-brand-500">Receipts</span>
          <span className="text-brand-900">{card.receipt_count}</span>
        </div>
        <div className="flex justify-between">
          <span className="font-sans text-brand-500">Execution</span>
          <span className="text-brand-900">
            {card.duration_ms != null ? `${(card.duration_ms / 1000).toFixed(2)}s` : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function PRReview() {
  const navigate = useNavigate();
  const [repo, setRepo] = useState('demo_repo');
  const [prNumber, setPrNumber] = useState('1');
  const [prTitle, setPrTitle] = useState('Fix statistics mean function bug');
  const [author, setAuthor] = useState('developer');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReviewRunDetail | null>(null);
  const [cards, setCards] = useState<AgentCard[]>(makeInitialCards());
  const [liveEvents, setLiveEvents] = useState<ReviewEvent[]>([]);

  const esRef = useRef<EventSource | null>(null);

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
            duration_ms: c.started_at != null ? Date.now() - c.started_at : c.duration_ms,
          };
        case 'agent.failed':
          return {
            ...c,
            status: 'error',
            result: (event.result as string) ?? 'ERROR',
            duration_ms: c.started_at != null ? Date.now() - c.started_at : c.duration_ms,
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

    setLoading(true);
    setError(null);
    setResult(null);
    setCards(makeInitialCards());
    setLiveEvents([]);
    esRef.current?.close();

    let runId: string;
    try {
      const run = await api.createReview(repo.trim(), prNum, {
        pr_title: prTitle || 'PR Review',
        author: author || 'developer',
        base_branch: 'main',
      });
      runId = run.id;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
      return;
    }

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
        // ignore
      }
    };

    es.onerror = () => {
      es.close();
    };

    try {
      const detail = await api.getReview(runId);
      setResult(detail);
      setCards((prev) =>
        prev.map((card) => {
          const ae = detail.agent_executions.find((a) => a.agent_type === card.agent_type);
          if (!ae) return card;
          const receipts = detail.receipts.filter((r) => r.agent_execution_id === ae.id);
          return {
            ...card,
            status: ae.status,
            result: receipts[0]?.result_summary ?? card.result,
            receipt_count: receipts.length,
            duration_ms:
              ae.started_at && ae.completed_at
                ? new Date(ae.completed_at).getTime() - new Date(ae.started_at).getTime()
                : card.duration_ms,
          };
        })
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } fontally: {
      setLoading(false);
    }
  }

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      
      {/* Header Banner */}
      <div className="card-ice flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold mb-2">
            <Zap className="w-3.5 h-3.5 text-amber-300" />
            Parallel Review Orchestrator
          </div>
          <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
            Trigger Pull Request Review
          </h1>
          <p className="text-brand-700 text-xs mt-1 max-w-2xl">
            Executes 4 parallel analysis agents (TestRunner, CatchingTest, DocCheck, HistoryCheck) followed by the Adaptive Strategy Planner.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setRepo('demo_repo');
              setPrNumber('1');
              setPrTitle('Fix statistics mean function bug');
            }}
            className="btn-pill-secondary text-xs"
          >
            Load Demo PR #1
          </button>
        </div>
      </div>

      {/* Review Setup Card */}
      <div className="card-white space-y-6">
        <h3 className="font-serif-title font-semibold text-lg text-brand-950 flex items-center gap-2 border-b border-brand-100 pb-3">
          <Layers className="w-5 h-5 text-brand-600" />
          Repository & PR Parameters
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-semibold text-brand-800 uppercase tracking-wider mb-1">
              Repository Name *
            </label>
            <input
              type="text"
              required
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="demo_repo"
              className="w-full px-3.5 py-2 text-xs font-mono bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-brand-800 uppercase tracking-wider mb-1">
              PR Number *
            </label>
            <input
              type="number"
              required
              min={1}
              value={prNumber}
              onChange={(e) => setPrNumber(e.target.value)}
              placeholder="1"
              className="w-full px-3.5 py-2 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-brand-800 uppercase tracking-wider mb-1">
              Author
            </label>
            <input
              type="text"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="developer"
              className="w-full px-3.5 py-2 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-brand-800 uppercase tracking-wider mb-1">
              PR Title
            </label>
            <input
              type="text"
              value={prTitle}
              onChange={(e) => setPrTitle(e.target.value)}
              placeholder="PR Title"
              className="w-full px-3.5 py-2 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
          <button
            onClick={handleRunReview}
            disabled={loading}
            className="btn-pill-primary text-sm px-8"
          >
            {loading ? (
              <>
                <Spinner size="sm" />
                Orchestrating Agents...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                Run Evidence-First Review
              </>
            )}
          </button>

          <span className="text-xs text-brand-600 font-mono">
            Endpoint: <code className="text-brand-900">POST /repos/{'{repo}'}/prs/{'{number}'}/review</code>
          </span>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-600" />
          <span>{error}</span>
        </div>
      )}

      {/* Agents execution squad status */}
      {(loading || result) && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-serif-title font-semibold text-lg text-brand-950 flex items-center gap-2">
              <Cpu className="w-5 h-5 text-brand-600" />
              Parallel Agent Execution Squad
            </h3>
            {result && <RiskBadge risk={result.risk_level} />}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {cards.map((c) => (
              <AgentCardView key={c.agent_type} card={c} />
            ))}
          </div>

          {/* SSE Live event log */}
          {liveEvents.length > 0 && (
            <div className="card-dark space-y-2">
              <div className="flex items-center justify-between text-xs text-brand-300 font-mono border-b border-brand-800 pb-2">
                <span className="flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-emerald-400" />
                  Live Review Event Stream (SSE)
                </span>
                <span className="text-[11px] text-gray-400">{liveEvents.length} events logged</span>
              </div>
              <div className="max-h-40 overflow-y-auto font-mono text-[11px] space-y-1 scrollbar-thin pr-2">
                {liveEvents.map((ev, idx) => (
                  <div key={idx} className="flex items-center gap-3 text-gray-300">
                    <span className="text-brand-400">{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}</span>
                    <span className="text-emerald-400 font-semibold">{ev.event_type}</span>
                    {ev.agent_type && <span className="text-amber-300">[{ev.agent_type}]</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Review Final Summary & Receipts */}
      {result && !loading && (
        <div className="space-y-6">
          <div className="card-ice space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-brand-200/80 pb-4">
              <div>
                <span className="text-[11px] font-semibold text-brand-600 uppercase tracking-wider">
                  Review Run #{result.id.slice(0, 8)}
                </span>
                <h2 className="font-serif-title font-bold text-2xl text-brand-950 mt-0.5">
                  Review Completed
                </h2>
              </div>
              <div className="flex items-center gap-3">
                <VerdictBadge verdict={result.verdict} size="lg" />
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
              <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
                <span className="text-brand-500 font-medium block">Risk Level</span>
                <div className="mt-1"><RiskBadge risk={result.risk_level} /></div>
              </div>

              <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
                <span className="text-brand-500 font-medium block">Verdict Confidence</span>
                <span className="font-bold text-brand-950 text-sm mt-0.5 block">
                  {result.confidence != null ? `${(result.confidence * 100).toFixed(0)}%` : '100%'}
                </span>
              </div>

              <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
                <span className="text-brand-500 font-medium block">Execution Time</span>
                <span className="font-mono text-brand-950 text-sm mt-0.5 block">
                  {result.elapsed_ms != null ? `${result.elapsed_ms} ms` : '—'}
                </span>
              </div>

              <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
                <span className="text-brand-500 font-medium block">Total Receipts</span>
                <span className="font-bold text-brand-950 text-sm mt-0.5 block">
                  {result.receipts.length} Evidence Receipts
                </span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-4 pt-2">
              <button
                onClick={() => navigate(`/reviews/${result.id}`)}
                className="btn-pill-primary text-xs"
              >
                Inspect Full Review Details <ArrowRight className="w-3.5 h-3.5" />
              </button>

              {result.verdict === 'BUG_DETECTED' && (
                <button
                  onClick={() => navigate(`/immunity?runId=${result.id}`)}
                  className="btn-pill-accent text-xs"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  Launch Bug Immunity Pipeline V7
                </button>
              )}
            </div>
          </div>

          {/* Evidence Receipts list */}
          {result.receipts.length > 0 && (
            <div className="space-y-4">
              <h3 className="font-serif-title font-semibold text-xl text-brand-950 flex items-center justify-between">
                <span>Executable Evidence Receipts</span>
                <span className="text-xs font-sans text-brand-600">
                  {result.receipts.length} verified evidence items
                </span>
              </h3>

              <div className="space-y-4">
                {result.receipts.map((r) => (
                  <div key={r.id} className="card-white space-y-3">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <SeverityBadge severity={r.severity} />
                          <span className="font-mono text-xs text-brand-500">[{r.agent ?? 'agent'}]</span>
                        </div>
                        <h4 className="font-semibold text-sm text-brand-950 mt-1">{r.title}</h4>
                      </div>
                      <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                        {r.result_summary}
                      </span>
                    </div>

                    <TerminalViewer
                      title={`Command Receipt: ${r.title}`}
                      command={r.command}
                      output={r.raw_output}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
