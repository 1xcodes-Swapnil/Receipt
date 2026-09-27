import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Fingerprint,
  GitPullRequest,
  Play,
  ShieldCheck,
  Zap,
} from 'lucide-react';

type AgentStatus = 'FAIL' | 'PASS' | 'INSUFFICIENT' | 'INFO';

const SAMPLE_AGENTS: { name: string; status: AgentStatus }[] = [
  { name: 'Test Runner', status: 'FAIL' },
  { name: 'Catching Test', status: 'INSUFFICIENT' },
  { name: 'Documentation Check', status: 'PASS' },
  { name: 'History Check', status: 'INFO' },
];

const STATUS_STYLES: Record<AgentStatus, { dot: string; text: string }> = {
  FAIL: { dot: 'bg-rose-400', text: 'text-rose-300' },
  PASS: { dot: 'bg-emerald-400', text: 'text-emerald-300' },
  INSUFFICIENT: { dot: 'bg-amber-400', text: 'text-amber-300' },
  INFO: { dot: 'bg-brand-300', text: 'text-brand-300' },
};

function ReviewRunCard() {
  return (
    <div className="relative rounded-3xl bg-brand-900 text-white border border-brand-800 shadow-soft-2xl p-5 pb-12 sm:p-6 sm:pb-14 lg:-rotate-2 lg:w-[88%]">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <GitPullRequest className="w-4 h-4 text-brand-300 shrink-0" />
          <span className="font-mono text-xs text-brand-100 truncate">demo_repo · PR #1</span>
        </div>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-brand-300 bg-white/5 border border-white/10 px-2 py-0.5 rounded-full shrink-0">
          4 agents
        </span>
      </div>

      <ul className="space-y-2.5">
        {SAMPLE_AGENTS.map(({ name, status }) => {
          const s = STATUS_STYLES[status];
          return (
            <li
              key={name}
              className="flex items-center justify-between gap-3 rounded-xl bg-white/[0.04] border border-white/[0.06] px-3 py-2"
            >
              <span className="flex items-center gap-2.5 text-xs font-medium text-brand-50 min-w-0">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.dot}`} />
                <span className="truncate">{name}</span>
              </span>
              <span className={`font-mono text-[10px] font-semibold tracking-wider shrink-0 ${s.text}`}>
                {status}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function EvidenceReceipt() {
  return (
    <div className="relative -mt-8 sm:-mt-10 ml-auto w-[92%] sm:w-[86%] lg:rotate-[1.5deg] drop-shadow-[0_24px_40px_rgba(19,32,39,0.18)]">
      <div className="bg-white rounded-t-2xl px-5 sm:px-6 pt-5 pb-4 font-mono text-[11px] text-brand-800">
        <div className="flex items-center justify-between mb-3">
          <span className="font-sans text-[10px] font-bold uppercase tracking-[0.2em] text-brand-500">
            Evidence Receipt
          </span>
          <span className="text-[10px] text-brand-400">sample</span>
        </div>

        <div className="border-t border-dashed border-brand-200 pt-3 space-y-1.5">
          <div className="flex justify-between gap-3">
            <span className="text-brand-400">agent</span>
            <span className="text-brand-900 font-medium">test_runner</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-brand-400">command</span>
            <span className="text-brand-900 font-medium truncate">pytest test_buggy_stats.py</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-brand-400">exit_code</span>
            <span className="text-brand-900 font-medium">1</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-brand-400">result</span>
            <span className="text-rose-600 font-semibold">FAIL</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-brand-400">severity</span>
            <span className="text-brand-900 font-medium">HIGH</span>
          </div>
        </div>

        <div className="border-t border-dashed border-brand-200 mt-3 pt-3 flex items-center gap-2 text-[10px] text-brand-500">
          <Fingerprint className="w-3.5 h-3.5 text-brand-400 shrink-0" />
          <span className="truncate">sha256 · 9f2c…e41a → prev 7b0d…c3f9</span>
        </div>
      </div>
      <div className="receipt-tear" />

      <div className="absolute -top-4 -right-2 sm:-right-4 rotate-6 rounded-xl border-2 border-rose-500/80 bg-rose-50/95 px-3 py-1.5 font-sans text-[11px] font-extrabold tracking-[0.18em] text-rose-600 shadow-sm">
        BUG DETECTED
      </div>
    </div>
  );
}

export function LandingHero() {
  return (
    <section className="relative overflow-hidden rounded-[2rem] sm:rounded-[2.5rem] border border-brand-200/80 bg-gradient-to-b from-brand-100 via-brand-100/80 to-brand-50 shadow-soft-xl">
      <div className="absolute inset-0 bg-evidence-grid pointer-events-none" />
      <div className="absolute -top-24 -right-24 w-96 h-96 bg-brand-300/30 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 inset-x-0 h-32 bg-gradient-to-t from-white/70 to-transparent pointer-events-none" />

      <div className="relative grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-10 items-center px-6 sm:px-10 lg:px-14 py-12 sm:py-16 lg:py-24">
        <div className="lg:col-span-7 space-y-7">
          <div className="inline-flex items-center gap-2 pl-1 pr-3.5 py-1 rounded-full bg-white/80 border border-brand-200 text-xs font-semibold text-brand-800 shadow-sm backdrop-blur-sm">
            <span className="inline-flex items-center gap-1 bg-brand-900 text-white px-2.5 py-0.5 rounded-full">
              <ShieldCheck className="w-3 h-3 text-brand-300" />
              Receipts
            </span>
            Every finding ships with proof
          </div>

          <h1 className="font-serif-title font-bold text-5xl sm:text-6xl lg:text-7xl text-brand-950 leading-[1.02] tracking-tight">
            No evidence,
            <br />
            <span className="italic font-medium text-brand-700">no flag.</span>
          </h1>

          <p className="text-lg sm:text-xl font-semibold text-brand-900">
            Evidence-First AI Code Review &amp; Bug Immunity
          </p>

          <p className="text-brand-700 text-sm sm:text-base leading-relaxed max-w-xl">
            Receipts treats code review as an evidence collection problem. Every finding is backed by
            executable tests, verifiable results, and an audit-ready evidence receipt.
          </p>

          <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-1">
            <Link to="/review" className="btn-pill-primary px-7 py-3.5 text-sm shadow-md hover:shadow-lg">
              <Zap className="w-4 h-4 text-amber-300" />
              Start a Review
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link to="/demo" className="btn-pill-secondary px-7 py-3.5 text-sm">
              <Play className="w-4 h-4 fill-current text-brand-600" />
              Explore Demo
            </Link>
          </div>

          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-950 transition-colors"
          >
            <Activity className="w-3.5 h-3.5" />
            Go to the dashboard
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        <div className="lg:col-span-5 relative max-w-md w-full mx-auto lg:max-w-none">
          <ReviewRunCard />
          <EvidenceReceipt />
        </div>
      </div>
    </section>
  );
}
