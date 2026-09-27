import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import type { ImmunityPipelineDetail } from '../types';
import { Spinner } from '../components/Spinner';
import { ErrorMessage } from '../components/ErrorMessage';
import { TerminalViewer } from '../components/TerminalViewer';
import {
  ShieldCheck,
  Zap
} from 'lucide-react';

const STAGE_STEPS = [
  { key: 'reproduce', label: '1. Reproduce' },
  { key: 'root_cause', label: '2. Root Cause' },
  { key: 'fix', label: '3. Fix' },
  { key: 'verify', label: '4. Verify' },
  { key: 'regression_test', label: '5. Regression Test' },
  { key: 'sibling_hunt', label: '6. Sibling Hunt' },
  { key: 'document', label: '7. Document' },
  { key: 'pattern', label: '8. Pattern' },
];

export default function BugImmunity() {
  const [searchParams] = useSearchParams();
  const initialRunId = searchParams.get('runId') || '';
  const navigate = useNavigate();

  const [runIdInput, setRunIdInput] = useState(initialRunId);
  const [pipelineDetail, setPipelineDetail] = useState<ImmunityPipelineDetail | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStartImmunity = async (targetRunId: string) => {
    if (!targetRunId.trim()) {
      setError('Please provide a valid Review Run ID');
      return;
    }

    setStarting(true);
    setError(null);
    setPipelineDetail(null);

    try {
      const created = await api.startImmunity(targetRunId.trim());
      const detail = await api.getImmunityPipeline(created.id);
      setPipelineDetail(detail);
    } catch (err: any) {
      setError(err.message || 'Failed to start Bug Immunity pipeline');
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    if (initialRunId) {
      handleStartImmunity(initialRunId);
    }
  }, [initialRunId]);

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      
      {/* Header Banner */}
      <div className="card-ice flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold mb-2">
            <ShieldCheck className="w-3.5 h-3.5 text-brand-300" />
            Bug Immunity V7 Orchestrator
          </div>
          <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
            8-Stage Evidence-Gated Pipeline
          </h1>
          <p className="text-brand-700 text-xs mt-1 max-w-2xl">
            When a review yields <code>BUG_DETECTED</code>, Immunity V7 executes: Reproduce → RootCause → Fix → Verify → RegressionTest → SiblingHunt → Document → Pattern.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/review')}
            className="btn-pill-secondary text-xs"
          >
            Trigger Review First
          </button>
        </div>
      </div>

      {/* Trigger Form */}
      <div className="card-white space-y-4">
        <h3 className="font-serif-title font-semibold text-lg text-brand-950 flex items-center gap-2 border-b border-brand-100 pb-3">
          <Zap className="w-5 h-5 text-brand-600" />
          Launch Pipeline for Review Run
        </h3>

        <div className="flex flex-col sm:flex-row items-end gap-3">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-brand-800 uppercase tracking-wider mb-1">
              Review Run ID (BUG_DETECTED)
            </label>
            <input
              type="text"
              required
              value={runIdInput}
              onChange={(e) => setRunIdInput(e.target.value)}
              placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
              className="w-full px-3.5 py-2.5 text-xs font-mono bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </div>

          <button
            onClick={() => handleStartImmunity(runIdInput)}
            disabled={starting}
            className="btn-pill-primary text-xs px-8 py-3 shrink-0"
          >
            {starting ? (
              <>
                <Spinner size="sm" />
                Executing Pipeline Stages...
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4" />
                Start Immunity V7 Pipeline
              </>
            )}
          </button>
        </div>
      </div>

      {error && <ErrorMessage message={error} />}

      {/* Active Pipeline Visualizer */}
      {pipelineDetail && (
        <div className="space-y-8">
          
          {/* Status Header */}
          <div className="card-ice space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-brand-200/80 pb-4">
              <div>
                <span className="text-[11px] font-mono font-semibold text-brand-600">
                  Pipeline ID: {pipelineDetail.id}
                </span>
                <h2 className="font-serif-title font-bold text-2xl text-brand-950 mt-0.5">
                  Immunity Pipeline Progress
                </h2>
              </div>

              <div className="flex items-center gap-3">
                <span className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                  pipelineDetail.status === 'passed'
                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                    : pipelineDetail.status === 'escalated'
                    ? 'bg-amber-100 text-amber-900 border border-amber-300'
                    : pipelineDetail.status === 'failed'
                    ? 'bg-rose-100 text-rose-800 border border-rose-300'
                    : 'bg-brand-900 text-white'
                }`}>
                  Status: {pipelineDetail.status}
                </span>
              </div>
            </div>

            {/* 8-Stage Progress Step Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 pt-2">
              {STAGE_STEPS.map((step) => {
                const stageData = pipelineDetail.stages.find((s) => s.stage_type === step.key);
                const isPassed = stageData?.status === 'passed';
                const isEscalated = stageData?.status === 'escalated';
                const isFailed = stageData?.status === 'failed';
                const isRunning = stageData?.status === 'running';

                return (
                  <div
                    key={step.key}
                    className={`p-3 rounded-2xl border text-center transition-all ${
                      isPassed
                        ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
                        : isEscalated
                        ? 'bg-amber-50 border-amber-300 text-amber-900'
                        : isFailed
                        ? 'bg-rose-50 border-rose-300 text-rose-900'
                        : isRunning
                        ? 'bg-brand-900 text-white animate-pulse'
                        : 'bg-white/70 border-brand-200 text-brand-400'
                    }`}
                  >
                    <span className="block font-bold text-xs truncate" title={step.label}>
                      {step.label}
                    </span>
                    <span className="block text-[10px] uppercase font-semibold mt-1">
                      {stageData?.status ?? 'pending'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Stage Details Grid */}
          <div className="space-y-4">
            <h3 className="font-serif-title font-semibold text-xl text-brand-950">
              Stage Evidence & Results ({pipelineDetail.stages.length} Stages)
            </h3>

            <div className="grid grid-cols-1 gap-4">
              {pipelineDetail.stages.map((st) => (
                <div key={st.id} className="card-white space-y-3">
                  <div className="flex items-center justify-between border-b border-brand-100 pb-2">
                    <span className="font-serif-title font-bold text-base text-brand-950 uppercase">
                      Stage: {st.stage_type.replace('_', ' ')}
                    </span>
                    <span className={`px-3 py-0.5 rounded-full text-xs font-bold ${
                      st.status === 'passed'
                        ? 'bg-emerald-100 text-emerald-800'
                        : st.status === 'escalated'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-rose-100 text-rose-800'
                    }`}>
                      {st.status}
                    </span>
                  </div>

                  {st.error && (
                    <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 font-mono">
                      <div>
                        <strong>Stage Status Notice:</strong> {st.error}
                      </div>
                      {(st.status === 'escalated' || st.status === 'blocked') && (
                        <button
                          onClick={() => handleStartImmunity(runIdInput)}
                          className="btn-pill-primary text-xs shrink-0 self-start sm:self-auto py-1.5 px-4"
                        >
                          Resolve & Continue Pipeline
                        </button>
                      )}
                    </div>
                  )}

                  {st.evidence && (
                    <TerminalViewer
                      title={`Stage Output (${st.stage_type})`}
                      output={st.evidence}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Sibling Code Findings */}
          {pipelineDetail.sibling_findings.length > 0 && (
            <div className="card-white space-y-4">
              <h3 className="font-serif-title font-semibold text-xl text-brand-950 border-b border-brand-100 pb-2">
                Sibling Code Findings ({pipelineDetail.sibling_findings.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {pipelineDetail.sibling_findings.map((sf) => (
                  <div key={sf.id} className="p-4 bg-brand-50 rounded-2xl border border-brand-200 text-xs space-y-2">
                    <div className="flex justify-between font-bold text-brand-950">
                      <span>Candidate Location</span>
                      <span className="text-emerald-700">Confidence: {(sf.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <code className="block font-mono bg-white p-2 rounded border text-brand-900">
                      {sf.candidate_location}
                    </code>
                    {sf.similarity_reason && (
                      <p className="text-brand-700">{sf.similarity_reason}</p>
                    )}
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
