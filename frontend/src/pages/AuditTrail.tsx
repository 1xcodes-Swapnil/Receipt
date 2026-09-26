import { useState } from 'react';
import { api } from '../services/api';
import type { AuditEvent, AuditVerification } from '../types';
import { Spinner } from '../components/Spinner';
import { ErrorMessage } from '../components/ErrorMessage';
import {
  FileCheck,
  Lock,
  CheckCircle2,
  AlertTriangle
} from 'lucide-react';

export default function AuditTrail() {
  const [runIdInput, setRunIdInput] = useState('');
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [verification, setVerification] = useState<AuditVerification | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleVerify = async (runId: string) => {
    if (!runId.trim()) {
      setError('Please enter a valid Review Run ID');
      return;
    }

    setLoading(true);
    setError(null);
    setVerification(null);
    setEvents([]);

    try {
      const evs = await api.getAuditEvents(runId.trim());
      setEvents(evs);
      const verif = await api.verifyAuditChain(runId.trim());
      setVerification(verif);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch audit events for run ID');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      
      {/* Header Banner */}
      <div className="card-ice flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold mb-2">
            <Lock className="w-3.5 h-3.5 text-brand-300" />
            Cryptographic SHA-256 Audit Chain
          </div>
          <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
            Audit Trail & Verification
          </h1>
          <p className="text-brand-700 text-xs mt-1 max-w-2xl">
            Verifies the hash chain integrity for review runs. Every event includes canonical JSON payload hashing and previous event pointer.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-brand-900 bg-white px-3.5 py-1.5 rounded-full border border-brand-200">
            SHA-256 Chain Verification Active
          </span>
        </div>
      </div>

      {/* Input Form */}
      <div className="card-white space-y-4">
        <h3 className="font-serif-title font-semibold text-lg text-brand-950 flex items-center gap-2 border-b border-brand-100 pb-3">
          <FileCheck className="w-5 h-5 text-brand-600" />
          Verify Review Run Audit Chain
        </h3>

        <div className="flex flex-col sm:flex-row items-end gap-3">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-brand-800 uppercase tracking-wider mb-1">
              Review Run ID
            </label>
            <input
              type="text"
              required
              value={runIdInput}
              onChange={(e) => setRunIdInput(e.target.value)}
              placeholder="e.g. review run ID string"
              className="w-full px-3.5 py-2.5 text-xs font-mono bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </div>

          <button
            onClick={() => handleVerify(runIdInput)}
            disabled={loading}
            className="btn-pill-primary text-xs px-8 py-3 shrink-0"
          >
            {loading ? (
              <>
                <Spinner size="sm" />
                Verifying Hashes...
              </>
            ) : (
              <>
                <Lock className="w-4 h-4" />
                Verify SHA-256 Chain
              </>
            )}
          </button>
        </div>
      </div>

      {error && <ErrorMessage message={error} />}

      {/* Verification Status Alert */}
      {verification && (
        <div className={`p-5 rounded-3xl border shadow-soft-xl flex items-start gap-4 ${
          verification.valid
            ? 'bg-emerald-50 border-emerald-300 text-emerald-950'
            : 'bg-rose-50 border-rose-300 text-rose-950'
        }`}>
          <div className={`p-2.5 rounded-2xl ${verification.valid ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'}`}>
            {verification.valid ? <CheckCircle2 className="w-6 h-6" /> : <AlertTriangle className="w-6 h-6" />}
          </div>

          <div className="space-y-1">
            <h3 className="font-serif-title font-bold text-lg">
              Audit Chain Status: {verification.valid ? 'VERIFIED & INTACT' : 'TAMPERED / INVALID'}
            </h3>
            <p className="text-xs leading-relaxed">
              Checked <strong>{verification.total_events}</strong> total audit event nodes. Error count: <strong>{verification.error_count}</strong>.
            </p>
          </div>
        </div>
      )}

      {/* Events Table */}
      {events.length > 0 && (
        <div className="card-white space-y-4">
          <h3 className="font-serif-title font-semibold text-xl text-brand-950 border-b border-brand-100 pb-3">
            Audit Event Sequence ({events.length} Events)
          </h3>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-brand-50 border-b border-brand-200 text-brand-800 uppercase font-semibold">
                <tr>
                  <th className="py-3 px-4">Seq</th>
                  <th className="py-3 px-4">Event Type</th>
                  <th className="py-3 px-4">Integrity Hash (SHA-256)</th>
                  <th className="py-3 px-4">Previous Hash</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-100 font-mono text-[11px]">
                {events.map((ev, idx) => (
                  <tr key={ev.id || idx} className="hover:bg-brand-50/60">
                    <td className="py-3 px-4 text-brand-500 font-bold">{ev.sequence ?? idx + 1}</td>
                    <td className="py-3 px-4 font-bold text-brand-950 font-sans text-xs">{ev.event_type}</td>
                    <td className="py-3 px-4 text-emerald-700 font-semibold truncate max-w-[200px]" title={ev.integrity_hash || ''}>
                      {ev.integrity_hash || '—'}
                    </td>
                    <td className="py-3 px-4 text-brand-400 truncate max-w-[200px]" title={ev.prev_hash || ''}>
                      {ev.prev_hash || '—'}
                    </td>
                    <td className="py-3 px-4 text-brand-600 font-sans text-[11px]">
                      {ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}
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
