import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../services/api';
import type { ReviewRunDetail } from '../types';
import { ErrorMessage } from '../components/ErrorMessage';
import { Spinner } from '../components/Spinner';
import { VerdictBadge } from '../components/VerdictBadge';
import { SeverityBadge } from '../components/SeverityBadge';
import { StatusDot } from '../components/StatusDot';

export default function ReviewDetails() {
  const { runId } = useParams<{ runId: string }>();
  const [detail, setDetail] = useState<ReviewRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    api.getReview(runId)
      .then(setDetail)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <div className="p-8"><Spinner /></div>;
  if (error) return <div className="p-8"><ErrorMessage message={error} /></div>;
  if (!detail) return null;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-6">
        <Link to="/review" className="text-xs text-accent hover:underline">← Back to PR Review</Link>
        <h1 className="text-2xl font-semibold text-gray-900 mt-2">Review Details</h1>
        <p className="text-xs text-muted font-mono mt-1">{detail.id}</p>
      </div>

      <div className="card mb-6">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-base font-semibold">Summary</h2>
          <VerdictBadge verdict={detail.verdict} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
          <div><p className="text-xs text-muted">Risk Level</p><p className="capitalize">{detail.risk_level}</p></div>
          <div><p className="text-xs text-muted">Status</p><p className="capitalize">{detail.status}</p></div>
          <div><p className="text-xs text-muted">Confidence</p><p>{detail.confidence != null ? `${(detail.confidence * 100).toFixed(0)}%` : '—'}</p></div>
          <div><p className="text-xs text-muted">Duration</p><p>{detail.elapsed_ms != null ? `${detail.elapsed_ms} ms` : '—'}</p></div>
        </div>
      </div>

      {detail.agent_executions.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-700 mb-3">Agents</h2>
          <div className="divide-y divide-border">
            {detail.agent_executions.map((ae) => (
              <div key={ae.id} className="py-2 flex justify-between text-sm">
                <span className="font-mono text-gray-700">{ae.agent_type}</span>
                <StatusDot status={ae.status} />
              </div>
            ))}
          </div>
        </div>
      )}

      {detail.receipts.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-700 mb-3">
            Evidence Receipts
          </h2>
          <div className="space-y-3">
            {detail.receipts.map((r) => (
              <div key={r.id} className="card text-sm">
                <div className="flex justify-between items-start">
                  <p className="font-medium">{r.title}</p>
                  <SeverityBadge severity={r.severity} />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  {r.agent && <div><span className="text-muted">Agent: </span><code className="font-mono">{r.agent}</code></div>}
                  <div><span className="text-muted">Result: </span><strong>{r.result_summary}</strong></div>
                  {r.command && <div><span className="text-muted">Command: </span><code className="font-mono">{r.command}</code></div>}
                  <div><span className="text-muted">Confidence: </span>{(r.confidence * 100).toFixed(0)}%</div>
                </div>
                {r.raw_output && (
                  <pre className="mt-3 bg-gray-950 text-green-400 text-xs font-mono p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                    {r.raw_output}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
