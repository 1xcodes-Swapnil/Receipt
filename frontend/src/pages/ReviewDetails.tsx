import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import type {
  ReviewRunDetail,
  AuditVerification,
  AuditEvent,
  ReviewClaim,
  EvidenceGap,
  StrategyTraceEntry,
} from '../types';
import { VerdictBadge } from '../components/VerdictBadge';
import { RiskBadge } from '../components/RiskBadge';
import { SeverityBadge } from '../components/SeverityBadge';
import { TerminalViewer } from '../components/TerminalViewer';
import { Spinner } from '../components/Spinner';
import { ErrorMessage } from '../components/ErrorMessage';
import {
  ShieldCheck,
  CheckCircle2,
  Zap,
  Layers,
  FileText,
  Lock,
  GitPullRequest
} from 'lucide-react';
import ReceiptTicketModal from '../components/ReceiptTicketModal';

export default function ReviewDetails() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<ReviewRunDetail | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditVerification, setAuditVerification] = useState<AuditVerification | null>(null);
  const [claims, setClaims] = useState<ReviewClaim[]>([]);
  const [evidenceGaps, setEvidenceGaps] = useState<EvidenceGap[]>([]);
  const [strategyTrace, setStrategyTrace] = useState<StrategyTraceEntry[]>([]);
  const [selectedReceiptId, setSelectedReceiptId] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'receipts' | 'adaptive' | 'agents' | 'audit'>('receipts');
  const [verifyingAudit, setVerifyingAudit] = useState(false);

  useEffect(() => {
    if (!runId) return;
    const targetRunId = runId;

    async function loadAllDetails() {
      setLoading(true);
      setError(null);

      try {
        const res = await api.getReview(targetRunId);
        setDetail(res);

        api.getAuditEvents(targetRunId).then(setAuditEvents).catch(() => []);
        api.verifyAuditChain(targetRunId).then(setAuditVerification).catch(() => null);
        api.getClaims(targetRunId).then(setClaims).catch(() => []);
        api.getEvidenceGaps(targetRunId).then(setEvidenceGaps).catch(() => []);
        api.getStrategyTrace(targetRunId).then(setStrategyTrace).catch(() => []);

        setLoading(false);
      } catch (err: any) {
        setError(err.message || 'Failed to load review details');
        setLoading(false);
      }
    }

    loadAllDetails();
  }, [runId]);

  const handleVerifyAudit = async () => {
    if (!runId) return;
    setVerifyingAudit(true);
    try {
      const res = await api.verifyAuditChain(runId);
      setAuditVerification(res);
    } catch {
      // failed
    } finally {
      setVerifyingAudit(false);
    }
  };

  if (loading) {
    return (
      <div className="w-[96%] max-w-[1920px] mx-auto px-4 py-16 text-center">
        <Spinner label="Loading full review run details and evidence receipts..." />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <ErrorMessage message={error || 'Review run not found'} />
      </div>
    );
  }

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      <ReceiptTicketModal
        receiptId={selectedReceiptId}
        onClose={() => setSelectedReceiptId(null)}
      />
      
      {/* Top Banner & Header */}
      <div className="card-ice space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-brand-200/80 pb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-mono font-semibold px-2.5 py-0.5 rounded-full bg-brand-900 text-white">
                ID: {detail.id}
              </span>
              {detail.pull_request && (
                <span className="text-xs font-semibold text-brand-800 flex items-center gap-1">
                  <GitPullRequest className="w-3.5 h-3.5" />
                  {detail.pull_request.title} (#{detail.pull_request.number})
                </span>
              )}
            </div>
            <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
              Review Inspection & Audit
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <VerdictBadge verdict={detail.verdict} size="lg" />

            {detail.verdict === 'BUG_DETECTED' && (
              <button
                onClick={() => navigate(`/immunity?runId=${detail.id}`)}
                className="btn-pill-accent text-xs shrink-0"
              >
                <ShieldCheck className="w-4 h-4" />
                Trigger Bug Immunity V7
              </button>
            )}
          </div>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4 text-xs">
          <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
            <span className="text-brand-500 font-medium block">Risk Level</span>
            <div className="mt-1"><RiskBadge risk={detail.risk_level} /></div>
          </div>

          <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
            <span className="text-brand-500 font-medium block">Confidence</span>
            <span className="font-bold text-brand-950 text-sm mt-0.5 block">
              {detail.confidence != null ? `${(detail.confidence * 100).toFixed(0)}%` : '100%'}
            </span>
          </div>

          <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
            <span className="text-brand-500 font-medium block">Duration</span>
            <span className="font-mono text-brand-950 text-sm mt-0.5 block">
              {detail.elapsed_ms != null ? `${detail.elapsed_ms} ms` : '—'}
            </span>
          </div>

          <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
            <span className="text-brand-500 font-medium block">Receipt Count</span>
            <span className="font-bold text-brand-950 text-sm mt-0.5 block">
              {detail.receipts.length} Receipts
            </span>
          </div>

          <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
            <span className="text-brand-500 font-medium block">SHA-256 Audit</span>
            <span className={`font-semibold text-xs mt-1 inline-flex items-center gap-1 ${
              auditVerification?.valid ? 'text-emerald-700' : 'text-amber-700'
            }`}>
              <Lock className="w-3 h-3" />
              {auditVerification?.valid ? 'Chain Intact' : 'Unverified'}
            </span>
          </div>

          <div className="bg-white/80 p-3 rounded-2xl border border-brand-200/60">
            <span className="text-brand-500 font-medium block">Started At</span>
            <span className="text-brand-900 text-xs mt-1 block font-mono">
              {detail.started_at ? new Date(detail.started_at).toLocaleTimeString() : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs Selection Bar */}
      <div className="flex border-b border-brand-200 gap-2 overflow-x-auto pb-1">
        <button
          onClick={() => setActiveTab('receipts')}
          className={`px-5 py-2.5 rounded-full text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'receipts'
              ? 'bg-brand-900 text-white shadow-sm'
              : 'bg-white text-brand-800 border border-brand-200 hover:bg-brand-100'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          Evidence Receipts ({detail.receipts.length})
        </button>

        <button
          onClick={() => setActiveTab('adaptive')}
          className={`px-5 py-2.5 rounded-full text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'adaptive'
              ? 'bg-brand-900 text-white shadow-sm'
              : 'bg-white text-brand-800 border border-brand-200 hover:bg-brand-100'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          Adaptive Evidence & Strategy Trace ({strategyTrace.length})
        </button>

        <button
          onClick={() => setActiveTab('agents')}
          className={`px-5 py-2.5 rounded-full text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'agents'
              ? 'bg-brand-900 text-white shadow-sm'
              : 'bg-white text-brand-800 border border-brand-200 hover:bg-brand-100'
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          4 Agent Squad ({detail.agent_executions.length})
        </button>

        <button
          onClick={() => setActiveTab('audit')}
          className={`px-5 py-2.5 rounded-full text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'audit'
              ? 'bg-brand-900 text-white shadow-sm'
              : 'bg-white text-brand-800 border border-brand-200 hover:bg-brand-100'
          }`}
        >
          <Lock className="w-3.5 h-3.5" />
          Cryptographic Audit Chain ({auditEvents.length})
        </button>
      </div>

      {/* Tab 1: Evidence Receipts */}
      {activeTab === 'receipts' && (
        <div className="space-y-6">
          {detail.receipts.length === 0 ? (
            <div className="card-white text-center py-12">
              <p className="text-brand-600 text-xs">No evidence receipts generated for this run.</p>
            </div>
          ) : (
            detail.receipts.map((r) => (
              <div key={r.id} className="card-white space-y-4">
                <div className="flex items-start justify-between gap-4 border-b border-brand-100 pb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={r.severity} />
                      <span className="font-mono text-xs text-brand-600">[{r.agent ?? 'agent'}]</span>
                    </div>
                    <h3 className="font-semibold text-base text-brand-950 mt-1">{r.title}</h3>
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setSelectedReceiptId(r.id)}
                      className="px-2.5 py-1 bg-brand-900 text-white rounded-full text-[11px] font-semibold hover:bg-brand-800 transition-colors shadow-sm"
                    >
                      Open Ticket View
                    </button>
                    <span className="text-xs text-brand-600 font-mono">
                      Confidence: {(r.confidence * 100).toFixed(0)}%
                    </span>
                    <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                      r.result_summary === 'PASS'
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-rose-100 text-rose-800'
                    }`}>
                      {r.result_summary}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  {r.command && (
                    <div>
                      <span className="text-brand-500 font-medium">Executed Command</span>
                      <code className="block mt-0.5 bg-brand-50 p-2 rounded-lg border border-brand-200 font-mono text-brand-900">
                        {r.command}
                      </code>
                    </div>
                  )}
                  {r.file_ref && (
                    <div>
                      <span className="text-brand-500 font-medium">File Reference</span>
                      <code className="block mt-0.5 bg-brand-50 p-2 rounded-lg border border-brand-200 font-mono text-brand-900">
                        {r.file_ref}
                      </code>
                    </div>
                  )}
                </div>

                <TerminalViewer
                  title={`Cryptographic Output Evidence (${r.title})`}
                  command={r.command}
                  output={r.raw_output}
                />
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 2: Adaptive Evidence & Strategy Trace */}
      {activeTab === 'adaptive' && (
        <div className="space-y-8">
          
          {/* Strategy Trace Log */}
          <div className="card-white space-y-4">
            <h3 className="font-serif-title font-semibold text-lg text-brand-950 border-b border-brand-100 pb-3">
              Adaptive Strategy Execution Trace (Phase 5+)
            </h3>
            
            {strategyTrace.length === 0 ? (
              <p className="text-brand-600 text-xs py-4">No adaptive strategy trace entries recorded for this run.</p>
            ) : (
              <div className="space-y-3">
                {strategyTrace.map((st) => (
                  <div key={st.id} className="p-3.5 bg-brand-50 rounded-2xl border border-brand-200 text-xs space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-brand-900">
                        Step #{st.step_number}: <code className="text-brand-700">{st.strategy_name}</code>
                      </span>
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                        st.execution_result === 'SUCCESS' || st.execution_result === 'EVIDENCE_COLLECTED'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-brand-200 text-brand-800'
                      }`}>
                        {st.execution_result ?? 'EXECUTED'}
                      </span>
                    </div>

                    {st.selection_reason && (
                      <p className="text-brand-700 leading-relaxed">
                        <strong>Reason:</strong> {st.selection_reason}
                      </p>
                    )}

                    {st.stopping_reason && (
                      <p className="text-brand-600 font-mono text-[11px]">
                        Stopping Decision: {st.stopping_reason}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Claims & Gaps Split */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card-white space-y-3">
              <h3 className="font-serif-title font-semibold text-base text-brand-950 border-b border-brand-100 pb-2">
                Review Claims ({claims.length})
              </h3>
              {claims.length === 0 ? (
                <p className="text-xs text-brand-500 py-2">No claims evaluated.</p>
              ) : (
                claims.map((c) => (
                  <div key={c.id} className="p-3 bg-brand-50 rounded-xl border border-brand-200 text-xs space-y-1">
                    <div className="flex justify-between font-semibold text-brand-900">
                      <span>{c.claim_type}</span>
                      <span className="text-emerald-700">{c.status}</span>
                    </div>
                    <p className="text-brand-700">{c.claim_text}</p>
                  </div>
                ))
              )}
            </div>

            <div className="card-white space-y-3">
              <h3 className="font-serif-title font-semibold text-base text-brand-950 border-b border-brand-100 pb-2">
                Evidence Gaps ({evidenceGaps.length})
              </h3>
              {evidenceGaps.length === 0 ? (
                <p className="text-xs text-brand-500 py-2">Zero unmitigated evidence gaps.</p>
              ) : (
                evidenceGaps.map((g) => (
                  <div key={g.id} className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs space-y-1">
                    <div className="flex justify-between font-semibold text-amber-900">
                      <span>{g.gap_type}</span>
                      <span>{g.resolved ? 'RESOLVED' : 'OPEN GAP'}</span>
                    </div>
                    <p className="text-amber-800">{g.description}</p>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>
      )}

      {/* Tab 3: 4 Agent Squad */}
      {activeTab === 'agents' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {detail.agent_executions.map((ae) => (
            <div key={ae.id} className="card-white space-y-3">
              <div className="flex items-center justify-between border-b border-brand-100 pb-2">
                <span className="font-serif-title font-bold text-base text-brand-950 uppercase">
                  {ae.agent_type.replace('_', ' ')}
                </span>
                <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                  {ae.status}
                </span>
              </div>
              <div className="space-y-1 text-xs text-brand-700 font-mono">
                <div>Execution ID: {ae.id}</div>
                <div>Started: {ae.started_at ? new Date(ae.started_at).toLocaleTimeString() : '—'}</div>
                <div>Completed: {ae.completed_at ? new Date(ae.completed_at).toLocaleTimeString() : '—'}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 4: Cryptographic Audit */}
      {activeTab === 'audit' && (
        <div className="space-y-6">
          <div className="card-ice flex items-center justify-between">
            <div>
              <h3 className="font-serif-title font-bold text-xl text-brand-950">
                SHA-256 Hash Chain Verification
              </h3>
              <p className="text-xs text-brand-700 mt-0.5">
                Every event in Receipts is recorded with a cryptographic hash pointing to the previous event hash.
              </p>
            </div>

            <button
              onClick={handleVerifyAudit}
              disabled={verifyingAudit}
              className="btn-pill-primary text-xs"
            >
              {verifyingAudit ? <Spinner size="sm" /> : <Lock className="w-3.5 h-3.5" />}
              Re-Verify Hash Chain
            </button>
          </div>

          {auditVerification && (
            <div className={`p-4 rounded-2xl border text-xs ${
              auditVerification.valid ? 'bg-emerald-50 border-emerald-200 text-emerald-900' : 'bg-rose-50 border-rose-200 text-rose-900'
            }`}>
              <div className="flex items-center gap-2 font-bold text-sm mb-1">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                Audit Chain Status: {auditVerification.valid ? 'INTACT & VERIFIED' : 'TAMPERED / INVALID'}
              </div>
              <p>Total events checked: {auditVerification.total_events} | Total Errors: {auditVerification.error_count}</p>
            </div>
          )}

          {/* Events Table */}
          <div className="card-white overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-brand-50 border-b border-brand-200 text-brand-800 uppercase font-semibold">
                <tr>
                  <th className="py-3 px-4">Seq</th>
                  <th className="py-3 px-4">Event Type</th>
                  <th className="py-3 px-4">SHA-256 Hash</th>
                  <th className="py-3 px-4">Prev Hash</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-100 font-mono text-[11px]">
                {auditEvents.map((ev, idx) => (
                  <tr key={ev.id || idx} className="hover:bg-brand-50/60">
                    <td className="py-2.5 px-4 text-brand-500">{ev.sequence ?? idx + 1}</td>
                    <td className="py-2.5 px-4 font-bold text-brand-900">{ev.event_type}</td>
                    <td className="py-2.5 px-4 text-emerald-700 truncate max-w-[150px]" title={ev.integrity_hash || ''}>
                      {ev.integrity_hash || '—'}
                    </td>
                    <td className="py-2.5 px-4 text-brand-400 truncate max-w-[150px]" title={ev.prev_hash || ''}>
                      {ev.prev_hash || '—'}
                    </td>
                    <td className="py-2.5 px-4 text-brand-600">
                      {ev.created_at ? new Date(ev.created_at).toLocaleTimeString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}
