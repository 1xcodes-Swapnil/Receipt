import { Link } from 'react-router-dom';

export default function Dashboard() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">Dashboard</h1>
      <p className="text-muted text-sm mb-8">
        Evidence-First Code Review &amp; Bug Immunity
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="text-base font-semibold mb-1">PR Review</h2>
          <p className="text-sm text-muted mb-4">
            Trigger a review and inspect evidence receipts.
          </p>
          <Link to="/review" className="btn-primary text-sm">
            Open PR Review →
          </Link>
        </div>

        <div className="card opacity-60">
          <h2 className="text-base font-semibold mb-1">
            Bug Immunity
            <span className="ml-2 text-xs text-muted font-normal">Phase 2+</span>
          </h2>
          <p className="text-sm text-muted">
            Automatically generate immunity tests from confirmed bugs.
          </p>
        </div>

        <div className="card opacity-60">
          <h2 className="text-base font-semibold mb-1">
            Replay
            <span className="ml-2 text-xs text-muted font-normal">Phase 2+</span>
          </h2>
          <p className="text-sm text-muted">
            Re-run historical review cases to verify fixes.
          </p>
        </div>

        <div className="card opacity-60">
          <h2 className="text-base font-semibold mb-1">
            Audit Trail
            <span className="ml-2 text-xs text-muted font-normal">Phase 2+</span>
          </h2>
          <p className="text-sm text-muted">
            Tamper-evident audit log of all review decisions.
          </p>
        </div>
      </div>

      <div className="mt-10 p-4 border border-border rounded-md bg-surface text-xs text-muted">
        <strong className="text-gray-700">Phase 1 — Foundation</strong>
        <p className="mt-1">
          PR Review is functional. All other features are Phase 2+ placeholders.
        </p>
      </div>
    </div>
  );
}
