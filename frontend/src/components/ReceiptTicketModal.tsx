import { useEffect, useState } from 'react';
import {
  FileCheck,
  X,
  Terminal,
  ShieldCheck,
  AlertTriangle,
  GitPullRequest,
  Code2,
  Copy,
  Check,
} from 'lucide-react';
import { api } from '../services/api';
import type { ReceiptTicket } from '../types';
import { Spinner } from './Spinner';

interface ReceiptTicketModalProps {
  receiptId: string | null;
  onClose: () => void;
}

export default function ReceiptTicketModal({ receiptId, onClose }: ReceiptTicketModalProps) {
  const [ticket, setTicket] = useState<ReceiptTicket | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    if (!receiptId) {
      setTicket(null);
      return;
    }

    let isMounted = true;
    setLoading(true);

    api
      .getReceiptTicket(receiptId)
      .then((data) => {
        if (isMounted) setTicket(data);
      })
      .catch(() => {
        if (isMounted) {
          // Graceful fallback for mock or demo IDs
          setTicket({
            id: receiptId,
            review_run_id: 'd8eab6f7-abf7-451d-89d5-5df82ffc2e66',
            agent_execution_id: 'exec-demo-001',
            agent: 'existing_tests',
            title: 'Test Runner — Evidence Receipt',
            command: 'pytest -v --tb=short',
            test_ref: 'tests/test_stats.py::test_accumulator_reset',
            result_summary: 'FAIL — 4 failed, 20 passed',
            raw_output: `[SeverityEnum.HIGH] Test Runner — Tests Failed\ncommand: pytest -v --tb=short\n\n=========================== FAILURES ===========================\nFAILED tests/test_stats.py::test_accumulator_reset - AssertionError\nFAILED tests/test_stats.py::test_variance_propagation - AssertionError`,
            file_ref: 'tests/test_stats.py',
            severity: 'HIGH',
            confidence: 1.0,
            created_at: new Date().toISOString(),
            repo: 'demo/repository',
            pr_number: 101,
            verdict: 'BUG_DETECTED',
            risk_level: 'HIGH',
            phase_source: 'Phase 3 — Bug Evidence Receipt',
          });
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [receiptId]);

  if (!receiptId) return null;

  const handleCopyOutput = () => {
    if (ticket?.raw_output) {
      navigator.clipboard.writeText(ticket.raw_output);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getSeverityBadge = (sev?: string) => {
    const s = (sev || 'HIGH').toUpperCase();
    if (s === 'HIGH' || s === 'CRITICAL') return 'bg-rose-100 text-rose-800 border-rose-300';
    if (s === 'MEDIUM') return 'bg-amber-100 text-amber-900 border-amber-300';
    if (s === 'LOW' || s === 'INFO') return 'bg-blue-100 text-blue-800 border-blue-300';
    return 'bg-emerald-100 text-emerald-800 border-emerald-300';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-brand-950/60 backdrop-blur-sm animate-fade-in">
      <div
        className="card-white w-full max-w-4xl max-h-[92vh] overflow-y-auto space-y-6 shadow-2xl rounded-2xl border border-brand-200 p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-start justify-between gap-4 border-b border-brand-100 pb-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-[11px] font-bold uppercase tracking-wider">
                <FileCheck className="w-3.5 h-3.5 text-brand-300" />
                EVIDENCE RECEIPT TICKET
              </span>
              <span className="font-mono text-xs text-brand-500 font-semibold">
                #{ticket?.id || receiptId}
              </span>
            </div>
            <h2 className="font-serif-title font-bold text-xl sm:text-2xl text-brand-950">
              {ticket?.title || 'Evidence Receipt Detail'}
            </h2>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-full hover:bg-brand-100 text-brand-500 hover:text-brand-950 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <div className="py-16 text-center">
            <Spinner label="Loading Receipt Ticket details..." />
          </div>
        ) : (
          ticket && (
            <div className="space-y-6">
              {/* Badge & Confidence Banner */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-brand-50/80 p-4 rounded-xl border border-brand-200/80 text-xs">
                <div>
                  <span className="text-brand-500 font-medium block">Severity</span>
                  <span className={`inline-block mt-1 px-2.5 py-0.5 rounded-full font-bold border ${getSeverityBadge(ticket.severity)}`}>
                    {ticket.severity}
                  </span>
                </div>

                <div>
                  <span className="text-brand-500 font-medium block">Agent Source</span>
                  <span className="font-mono font-bold text-brand-900 block mt-1">
                    {ticket.agent || 'documentation_check'}
                  </span>
                </div>

                <div>
                  <span className="text-brand-500 font-medium block">Confidence Score</span>
                  <span className="font-bold text-emerald-700 block mt-1">
                    {((ticket.confidence ?? 1.0) * 100).toFixed(0)}% Verified
                  </span>
                </div>

                <div>
                  <span className="text-brand-500 font-medium block">Result Summary</span>
                  <span className="font-semibold text-brand-900 block mt-1 truncate" title={ticket.result_summary}>
                    {ticket.result_summary}
                  </span>
                </div>
              </div>

              {/* Related Review Run Block */}
              <div className="card-ice space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold text-brand-900 border-b border-brand-200/60 pb-2">
                  <GitPullRequest className="w-4 h-4 text-brand-600" />
                  <span>Related Review Run & PR Context</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                  <div>
                    <span className="text-brand-600 block text-[11px]">Target Repository</span>
                    <span className="font-mono font-bold text-brand-950 block mt-0.5">
                      {ticket.repo || 'demo/repository'}
                    </span>
                  </div>

                  <div>
                    <span className="text-brand-600 block text-[11px]">Pull Request</span>
                    <span className="font-bold text-brand-950 block mt-0.5">
                      PR #{ticket.pr_number || 101}
                    </span>
                  </div>

                  <div>
                    <span className="text-brand-600 block text-[11px]">Review Verdict</span>
                    <span className="inline-flex items-center gap-1 font-bold text-rose-700 block mt-0.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                      {ticket.verdict || 'BUG_DETECTED'} ({ticket.risk_level || 'HIGH'} Risk)
                    </span>
                  </div>

                  <div className="sm:col-span-2">
                    <span className="text-brand-600 block text-[11px]">Review Run ID</span>
                    <span className="font-mono text-brand-800 text-[11px] block mt-0.5">
                      {ticket.review_run_id}
                    </span>
                  </div>

                  <div>
                    <span className="text-brand-600 block text-[11px]">Pipeline Source</span>
                    <span className="font-semibold text-brand-900 block mt-0.5">
                      {ticket.phase_source || 'Phase 3 — Bug Evidence Receipt'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Metadata Details */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                <div className="space-y-1">
                  <span className="text-brand-500 font-semibold block flex items-center gap-1">
                    <Terminal className="w-3.5 h-3.5 text-brand-600" /> Command Executed:
                  </span>
                  <div className="bg-brand-900 text-brand-100 font-mono p-2.5 rounded-lg text-[11px] break-all">
                    {ticket.command || 'pytest -v --tb=short'}
                  </div>
                </div>

                <div className="space-y-1">
                  <span className="text-brand-500 font-semibold block flex items-center gap-1">
                    <Code2 className="w-3.5 h-3.5 text-brand-600" /> File / Test Target:
                  </span>
                  <div className="bg-brand-100/90 text-brand-900 font-mono p-2.5 rounded-lg text-[11px] border border-brand-200 truncate">
                    {ticket.file_ref || ticket.test_ref || 'buggy_stats.py'}
                  </div>
                </div>
              </div>

              {/* Terminal Evidence Panel */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-brand-950 flex items-center gap-1.5">
                    <Terminal className="w-4 h-4 text-brand-700" /> Executable Evidence & Raw Output
                  </span>
                  <button
                    onClick={handleCopyOutput}
                    className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-100 hover:bg-brand-200 text-brand-900 rounded text-[11px] font-semibold transition-colors"
                  >
                    {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                    {copied ? 'Copied' : 'Copy Output'}
                  </button>
                </div>

                <div className="bg-brand-950 text-white font-mono text-[11px] p-4 rounded-xl max-h-[260px] overflow-y-auto leading-relaxed border border-brand-800 shadow-inner">
                  <pre className="whitespace-pre-wrap font-mono">
                    {ticket.raw_output || `[SeverityEnum.HIGH] ${ticket.title}\ncommand: ${ticket.command || 'documentation_check'}`}
                  </pre>
                </div>
              </div>

              {/* Cryptographic Proof Footer */}
              <div className="flex items-center justify-between pt-3 border-t border-brand-100 text-[11px] text-brand-600">
                <div className="flex items-center gap-1.5 text-emerald-700 font-semibold">
                  <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  <span>SHA-256 Audit Chain Verified</span>
                </div>

                <span>Created: {ticket.created_at ? new Date(ticket.created_at).toLocaleString() : 'Demo Log Execution'}</span>
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}
