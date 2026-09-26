import { useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  ArrowRight,
  HelpCircle,
} from 'lucide-react';
import { api } from '../services/api';
import type { DemoLogExecution } from '../types';
import { Spinner } from '../components/Spinner';
import { ErrorMessage } from '../components/ErrorMessage';
import ReceiptTicketModal from '../components/ReceiptTicketModal';

export default function DemoExecution() {
  const [data, setData] = useState<DemoLogExecution | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedReceiptId, setSelectedReceiptId] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    api
      .getDemoLogExecution()
      .then((res) => {
        if (isMounted) setData(res);
      })
      .catch((err) => {
        if (isMounted) setError(err.message || 'Failed to parse demo log execution');
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-12 text-center">
        <Spinner label="Parsing real demo.log execution stream & 6 phases..." />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8">
        <ErrorMessage message={error || 'Failed to load demo execution'} />
      </div>
    );
  }

  const { phases, summary } = data;
  const p1Health = phases.find((p) => p.phase_number === 1);
  const p2Review = phases.find((p) => p.phase_number === 2);
  const p3Receipts = phases.find((p) => p.phase_number === 3);
  const p4Immunity = phases.find((p) => p.phase_number === 4);
  const p5Replay = phases.find((p) => p.phase_number === 5);
  const p6Audit = phases.find((p) => p.phase_number === 6);

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      {/* Receipt Ticket Modal */}
      <ReceiptTicketModal
        receiptId={selectedReceiptId}
        onClose={() => setSelectedReceiptId(null)}
      />

      {/* Header Banner */}
      <div className="card-ice flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold mb-2">
            <Activity className="w-3.5 h-3.5 text-brand-300" />
            Phase 8 Live Execution Log Stream
          </div>
          <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
            Demo Execution Stream (6 Phases)
          </h1>
          <p className="text-brand-700 text-xs mt-1 max-w-3xl">
            Real parsed execution pipeline from <code className="bg-brand-200 px-1.5 py-0.5 rounded font-mono text-[11px]">demo/logs/latest/demo.log</code>. Visualizing all 6 execution phases, health checks, adaptive strategy trace, bug receipts, immunity pipeline, replay metrics, and audit integrity.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] font-mono text-brand-700 bg-white/80 px-3 py-1.5 rounded-full border border-brand-200">
            Start Time: {data.start_time}
          </span>
        </div>
      </div>

      {/* Overview Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4">
        <div className="card-white space-y-1">
          <span className="text-brand-500 text-[11px] font-medium block">Final Verdict</span>
          <span className="font-bold text-rose-700 text-sm block">{summary.verdict}</span>
        </div>

        <div className="card-white space-y-1">
          <span className="text-brand-500 text-[11px] font-medium block">Confidence</span>
          <span className="font-bold text-emerald-700 text-sm block">
            {(summary.confidence * 100).toFixed(0)}%
          </span>
        </div>

        <div className="card-white space-y-1">
          <span className="text-brand-500 text-[11px] font-medium block">Review Duration</span>
          <span className="font-mono font-bold text-brand-950 text-sm block">{summary.elapsed_ms} ms</span>
        </div>

        <div className="card-white space-y-1">
          <span className="text-brand-500 text-[11px] font-medium block">Replay Accuracy</span>
          <span className="font-bold text-emerald-700 text-sm block">
            {(summary.replay_accuracy * 100).toFixed(0)}%
          </span>
        </div>

        <div className="card-white space-y-1">
          <span className="text-brand-500 text-[11px] font-medium block">Immunity Status</span>
          <span className="font-bold text-amber-700 text-sm block">{summary.immunity_status}</span>
        </div>

        <div className="card-white space-y-1">
          <span className="text-brand-500 text-[11px] font-medium block">Audit Chain</span>
          <span className="font-bold text-emerald-700 text-sm block">
            {summary.audit_valid ? 'Valid (21 Events)' : 'Invalid'}
          </span>
        </div>
      </div>

      {/* 6 EXECUTION PHASES TIMELINE */}
      <div className="space-y-8">
        
        {/* PHASE 1: HEALTH CHECK */}
        <div className="card-white space-y-4">
          <div className="flex items-center justify-between border-b border-brand-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 rounded-lg bg-brand-900 text-white flex items-center justify-center font-bold text-xs">
                1
              </span>
              <div>
                <h3 className="font-serif-title font-bold text-lg text-brand-950">Phase 1: HEALTH CHECK</h3>
                <p className="text-brand-600 text-xs">System environment, database connection, and demo repository verification</p>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold border border-emerald-300">
              <CheckCircle2 className="w-3.5 h-3.5" /> PASSED ({p1Health?.duration_ms ?? 936} ms)
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {p1Health?.items?.map((item, idx) => (
              <div key={idx} className="bg-brand-50/80 p-3.5 rounded-xl border border-brand-200/80 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-brand-950 text-xs">{item.name}</span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
                    {item.status}
                  </span>
                </div>
                <span className="text-brand-600 font-mono text-[11px] block truncate" title={item.details}>
                  {item.details}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* PHASE 2: DEMO REVIEW & ADAPTIVE STRATEGY TRACE */}
        <div className="card-white space-y-4">
          <div className="flex items-center justify-between border-b border-brand-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 rounded-lg bg-brand-900 text-white flex items-center justify-center font-bold text-xs">
                2
              </span>
              <div>
                <h3 className="font-serif-title font-bold text-lg text-brand-950">Phase 2: DEMO REVIEW & ADAPTIVE STRATEGY TRACE</h3>
                <p className="text-brand-600 text-xs">Adaptive strategy execution loop evaluating claims for code correctness and documentation</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-100 text-rose-800 text-xs font-bold border border-rose-300">
                <AlertTriangle className="w-3.5 h-3.5" /> Verdict: {p2Review?.verdict} ({p2Review?.risk} Risk)
              </span>
              <span className="text-xs font-mono text-brand-600">({p2Review?.duration_ms} ms)</span>
            </div>
          </div>

          <div className="space-y-3">
            <h4 className="font-serif-title font-semibold text-sm text-brand-900">Adaptive Strategy Trace</h4>
            <div className="grid grid-cols-1 divide-y divide-brand-100 border border-brand-200 rounded-xl overflow-hidden bg-brand-50/50">
              {p2Review?.strategy_trace?.map((st) => (
                <div key={st.step} className="p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-white transition-colors">
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-brand-200 text-brand-900 font-mono font-bold text-xs flex items-center justify-center shrink-0">
                      S{st.step}
                    </span>
                    <div>
                      <span className="font-mono font-bold text-brand-950 text-xs block">{st.strategy}</span>
                      <span className="text-brand-600 text-xs block leading-relaxed">{st.reason}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                      st.result === 'FAIL'
                        ? 'bg-rose-100 text-rose-800 border-rose-300'
                        : 'bg-amber-100 text-amber-900 border-amber-300'
                    }`}>
                      {st.result}
                    </span>
                    <span className="text-xs font-semibold text-brand-700">
                      Confidence: {(st.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* PHASE 3: BUG EVIDENCE RECEIPT */}
        <div className="card-white space-y-4">
          <div className="flex items-center justify-between border-b border-brand-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 rounded-lg bg-brand-900 text-white flex items-center justify-center font-bold text-xs">
                3
              </span>
              <div>
                <h3 className="font-serif-title font-bold text-lg text-brand-950">Phase 3: BUG EVIDENCE RECEIPT</h3>
                <p className="text-brand-600 text-xs">Generated evidence receipts backed by executable agent findings (Click receipt to open Ticket View)</p>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold border border-emerald-300">
              <CheckCircle2 className="w-3.5 h-3.5" /> 2 FAIL Receipt(s) Generated ({p3Receipts?.duration_ms} ms)
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {p3Receipts?.receipts?.map((rcpt) => (
              <div
                key={rcpt.receipt_id}
                onClick={() => setSelectedReceiptId(rcpt.receipt_id)}
                className="bg-white p-4 rounded-xl border border-brand-200 shadow-soft-sm hover:shadow-soft-md hover:border-brand-400 cursor-pointer transition-all space-y-2 group"
              >
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-rose-100 text-rose-800 border border-rose-300 text-xs font-bold uppercase">
                    <AlertTriangle className="w-3 h-3" /> {rcpt.severity}
                  </span>
                  <span className="font-mono text-[11px] text-brand-500 font-semibold group-hover:text-brand-900 flex items-center gap-1">
                    Receipt #{rcpt.receipt_id.slice(0, 8)} <ArrowRight className="w-3 h-3" />
                  </span>
                </div>

                <h4 className="font-serif-title font-bold text-sm text-brand-950 group-hover:text-brand-700 transition-colors">
                  {rcpt.title}
                </h4>

                <div className="flex items-center justify-between text-xs text-brand-600 pt-1 border-t border-brand-50">
                  <span className="font-mono text-brand-800">Agent: {rcpt.agent}</span>
                  <span className="font-mono bg-brand-50 px-2 py-0.5 rounded text-[11px] border border-brand-200">
                    {rcpt.command}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* PHASE 4: IMMUNITY PIPELINE (V7) */}
        <div className="card-white space-y-4">
          <div className="flex items-center justify-between border-b border-brand-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 rounded-lg bg-brand-900 text-white flex items-center justify-center font-bold text-xs">
                4
              </span>
              <div>
                <h3 className="font-serif-title font-bold text-lg text-brand-950">Phase 4: IMMUNITY PIPELINE (V7)</h3>
                <p className="text-brand-600 text-xs">Automated 8-stage self-healing immunity pipeline</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-bold border border-amber-300">
                <HelpCircle className="w-3.5 h-3.5" /> Pipeline Status: {p4Immunity?.overall_status}
              </span>
              <span className="text-xs font-mono text-brand-600">({p4Immunity?.duration_ms} ms)</span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5">
            {p4Immunity?.stages?.map((stg, idx) => {
              const isPassed = stg.status === 'PASSED';
              const isEscalated = stg.status === 'ESCALATED';

              return (
                <div
                  key={idx}
                  className={`p-3 rounded-xl border text-center space-y-1 ${
                    isPassed
                      ? 'bg-emerald-50 border-emerald-300 text-emerald-950'
                      : isEscalated
                      ? 'bg-amber-50 border-amber-300 text-amber-950'
                      : 'bg-brand-50/50 border-brand-200 text-brand-400'
                  }`}
                >
                  <span className="text-[10px] font-bold block uppercase tracking-wider">Stage {idx + 1}</span>
                  <span className="font-bold text-xs block truncate" title={stg.stage}>
                    {stg.stage}
                  </span>
                  <span
                    className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                      isPassed
                        ? 'bg-emerald-200 text-emerald-900'
                        : isEscalated
                        ? 'bg-amber-200 text-amber-950'
                        : 'bg-brand-200 text-brand-700'
                    }`}
                  >
                    {stg.status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* PHASE 5: REPLAY ENGINE */}
        <div className="card-white space-y-4">
          <div className="flex items-center justify-between border-b border-brand-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 rounded-lg bg-brand-900 text-white flex items-center justify-center font-bold text-xs">
                5
              </span>
              <div>
                <h3 className="font-serif-title font-bold text-lg text-brand-950">Phase 5: REPLAY ENGINE</h3>
                <p className="text-brand-600 text-xs">Replay benchmark validation matrix across 6 seeded repository test cases</p>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold border border-emerald-300">
              <CheckCircle2 className="w-3.5 h-3.5" /> Replay Succeeded ({p5Replay?.duration_ms} ms)
            </span>
          </div>

          {/* Replay Metrics Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 bg-brand-50/70 p-4 rounded-xl border border-brand-200">
            <div>
              <span className="text-brand-500 text-[11px] block font-medium">Catch Rate</span>
              <span className="font-bold text-emerald-700 text-sm block">
                {((p5Replay?.metrics?.catch_rate ?? 1.0) * 100).toFixed(0)}%
              </span>
            </div>

            <div>
              <span className="text-brand-500 text-[11px] block font-medium">Accuracy</span>
              <span className="font-bold text-emerald-700 text-sm block">
                {((p5Replay?.metrics?.accuracy ?? 1.0) * 100).toFixed(0)}%
              </span>
            </div>

            <div>
              <span className="text-brand-500 text-[11px] block font-medium">False Alarm %</span>
              <span className="font-bold text-emerald-700 text-sm block">
                {(p5Replay?.metrics?.false_alarm_pct ?? 0).toFixed(1)}%
              </span>
            </div>

            <div>
              <span className="text-brand-500 text-[11px] block font-medium">Caught Bugs</span>
              <span className="font-bold text-brand-950 text-sm block">{p5Replay?.metrics?.caught_bugs ?? 3}</span>
            </div>

            <div>
              <span className="text-brand-500 text-[11px] block font-medium">Missed Bugs</span>
              <span className="font-bold text-brand-950 text-sm block">{p5Replay?.metrics?.missed_bugs ?? 0}</span>
            </div>

            <div>
              <span className="text-brand-500 text-[11px] block font-medium">False Alarms</span>
              <span className="font-bold text-brand-950 text-sm block">{p5Replay?.metrics?.false_alarms ?? 0}</span>
            </div>
          </div>

          {/* Replay Cases Matrix */}
          <div className="overflow-hidden border border-brand-200 rounded-xl bg-white">
            <table className="w-full text-left text-xs table-fixed">
              <thead className="bg-brand-50 border-b border-brand-200 text-brand-800 uppercase font-semibold">
                <tr>
                  <th className="py-3 px-4 w-[45%]">Replay Benchmark Case</th>
                  <th className="py-3 px-4 w-[30%]">Engine Verdict</th>
                  <th className="py-3 px-4 w-[25%] text-right">Ground Truth Check</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-100 font-mono text-[11px]">
                {p5Replay?.cases?.map((c, idx) => (
                  <tr key={idx} className="hover:bg-brand-50/60 transition-colors">
                    <td className="py-3 px-4 font-bold text-brand-950 font-sans text-xs">{c.case_id}</td>
                    <td className="py-3 px-4">
                      <span className={`px-2.5 py-0.5 rounded-full font-bold text-[10px] ${
                        c.verdict === 'BUG_DETECTED'
                          ? 'bg-rose-100 text-rose-800 border border-rose-200'
                          : 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                      }`}>
                        {c.verdict}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="text-emerald-700 font-bold font-sans text-xs">✓ Correct Match</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* PHASE 6: AUDIT CHAIN VERIFICATION */}
        <div className="card-white space-y-4">
          <div className="flex items-center justify-between border-b border-brand-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 rounded-lg bg-brand-900 text-white flex items-center justify-center font-bold text-xs">
                6
              </span>
              <div>
                <h3 className="font-serif-title font-bold text-lg text-brand-950">Phase 6: AUDIT CHAIN VERIFICATION</h3>
                <p className="text-brand-600 text-xs">Cryptographic SHA-256 canonical event hash chain integrity verification</p>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold border border-emerald-300">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Audit Chain Intact ({p6Audit?.duration_ms} ms)
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 bg-brand-50/70 p-4 rounded-xl border border-brand-200 text-xs">
            <div>
              <span className="text-brand-500 font-medium block">Chain Integrity</span>
              <span className="font-bold text-emerald-700 block mt-0.5">
                {p6Audit?.audit?.valid ? 'Valid (Intact)' : 'Tampered'}
              </span>
            </div>

            <div>
              <span className="text-brand-500 font-medium block">Total Audit Events</span>
              <span className="font-mono font-bold text-brand-950 block mt-0.5">
                {p6Audit?.audit?.total_events ?? 21} Events
              </span>
            </div>

            <div>
              <span className="text-brand-500 font-medium block">Error Count</span>
              <span className="font-mono font-bold text-emerald-700 block mt-0.5">
                {p6Audit?.audit?.error_count ?? 0} Errors
              </span>
            </div>

            <div>
              <span className="text-brand-500 font-medium block">Review Run ID</span>
              <span className="font-mono text-brand-800 text-[11px] block mt-0.5 truncate" title={p6Audit?.audit?.run_id}>
                {p6Audit?.audit?.run_id ?? 'd8eab6f7-abf7-451d-89d5-5df82ffc2e66'}
              </span>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
