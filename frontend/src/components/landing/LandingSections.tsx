import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BookOpen,
  Bot,
  CircleAlert,
  CircleCheck,
  FileCheck,
  FileSearch,
  GitCompareArrows,
  GitPullRequest,
  History,
  Link2,
  ReceiptText,
  RotateCcw,
  Scale,
  ShieldCheck,
  SquareTerminal,
  TriangleAlert,
} from 'lucide-react';

function SectionHeading({
  eyebrow,
  title,
  description,
  align = 'left',
  dark = false,
}: {
  eyebrow: string;
  title: React.ReactNode;
  description?: string;
  align?: 'left' | 'center';
  dark?: boolean;
}) {
  return (
    <div className={`space-y-3 ${align === 'center' ? 'text-center mx-auto max-w-2xl' : 'max-w-2xl'}`}>
      <span
        className={`font-mono text-[11px] font-semibold uppercase tracking-[0.2em] ${
          dark ? 'text-brand-300' : 'text-brand-500'
        }`}
      >
        {eyebrow}
      </span>
      <h2
        className={`font-serif-title font-bold text-3xl sm:text-4xl leading-tight ${
          dark ? 'text-white' : 'text-brand-950'
        }`}
      >
        {title}
      </h2>
      {description && (
        <p className={`text-sm sm:text-base leading-relaxed ${dark ? 'text-brand-200' : 'text-brand-700'}`}>
          {description}
        </p>
      )}
    </div>
  );
}

const WORKFLOW = [
  {
    icon: GitPullRequest,
    title: 'Pull Request',
    body: 'Point Receipts at a repository and PR. The code is snapshotted into an isolated, hash-verified workspace.',
  },
  {
    icon: Bot,
    title: 'AI Review Agents',
    body: 'Four agents run in parallel, each collecting its own evidence against the change.',
  },
  {
    icon: ReceiptText,
    title: 'Evidence Receipts',
    body: 'Every result is recorded with the exact command, raw output, and a SHA-256 integrity hash.',
  },
  {
    icon: Scale,
    title: 'Verdict',
    body: 'BUG DETECTED, SAFE, or ESCALATE — decided from the evidence, never from speculation.',
  },
  {
    icon: ShieldCheck,
    title: 'Bug Immunity',
    body: 'Confirmed bugs are reproduced, fixed, verified, and registered as a reusable pattern.',
  },
];

function WorkflowSection() {
  return (
    <section className="space-y-10">
      <SectionHeading
        eyebrow="The Receipts workflow"
        title={
          <>
            From pull request to <span className="italic font-medium text-brand-700">proven</span> verdict.
          </>
        }
        description="Each step hands the next one evidence, not opinions. If a step cannot produce evidence, the review stops and escalates."
      />

      <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 lg:gap-3">
        {WORKFLOW.map(({ icon: Icon, title, body }, i) => (
          <li key={title} className="relative">
            <div className="h-full card-white p-5 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center">
                  <Icon className="w-5 h-5" />
                </div>
                <span className="font-mono text-[11px] font-semibold text-brand-400">
                  {String(i + 1).padStart(2, '0')}
                </span>
              </div>
              <h3 className="font-serif-title font-semibold text-lg text-brand-950">{title}</h3>
              <p className="text-xs text-brand-700 leading-relaxed">{body}</p>
            </div>
            {i < WORKFLOW.length - 1 && (
              <span className="hidden lg:flex absolute top-1/2 -right-3 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-brand-900 text-white items-center justify-center shadow-sm">
                <ArrowRight className="w-3 h-3" />
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

const AGENTS = [
  {
    icon: SquareTerminal,
    name: 'Test Runner',
    id: 'test_runner',
    body: "Executes the repository's existing test suite and captures real stdout, stderr, and exit codes.",
    evidence: 'Command + raw output',
    role: 'Can flag',
  },
  {
    icon: GitCompareArrows,
    name: 'Catching Test',
    id: 'catching_test',
    body: 'Runs tests on the parent commit and the PR commit. Reports a regression only when parent passes and PR fails.',
    evidence: 'parent=PASS · PR=FAIL',
    role: 'Can flag',
  },
  {
    icon: FileSearch,
    name: 'Documentation Check',
    id: 'documentation_check',
    body: 'Inspects README, contribution guides, and docs for sections that are concretely missing or references that are broken.',
    evidence: 'Concrete gaps only',
    role: 'Advisory',
  },
  {
    icon: History,
    name: 'History Check',
    id: 'history_check',
    body: 'Reads the Git history of changed files for prior fixes, reverts, and churn to add context to the review.',
    evidence: 'Commit history context',
    role: 'Informational',
  },
];

function AgentsSection() {
  return (
    <section className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-start">
      <div className="lg:col-span-4 lg:sticky lg:top-40 space-y-6">
        <SectionHeading
          eyebrow="Review agents"
          title={
            <>
              Four agents. <span className="italic font-medium text-brand-700">One standard of proof.</span>
            </>
          }
          description="Only execution evidence can raise a bug. Documentation and history findings add context, but never flag a PR on their own."
        />
        <Link to="/activity" className="btn-pill-secondary text-xs">
          See agents in PR Activity Logs <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      <div className="lg:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-5">
        {AGENTS.map(({ icon: Icon, name, id, body, evidence, role }) => (
          <div key={id} className="card-white group flex flex-col gap-4 hover:border-brand-300">
            <div className="flex items-start justify-between gap-3">
              <div className="w-12 h-12 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center group-hover:bg-brand-900 group-hover:text-white transition-colors duration-300">
                <Icon className="w-6 h-6" />
              </div>
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${
                  role === 'Can flag'
                    ? 'bg-brand-900 text-white border-brand-900'
                    : 'bg-brand-50 text-brand-700 border-brand-200'
                }`}
              >
                {role}
              </span>
            </div>
            <div className="space-y-1.5">
              <h3 className="font-serif-title font-semibold text-xl text-brand-950">{name}</h3>
              <p className="text-xs text-brand-700 leading-relaxed">{body}</p>
            </div>
            <div className="mt-auto pt-3 border-t border-brand-100 flex items-center justify-between gap-2 font-mono text-[11px]">
              <span className="text-brand-400">{id}</span>
              <span className="text-brand-800 font-medium text-right">{evidence}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

const VERDICTS = [
  {
    label: 'BUG DETECTED',
    icon: TriangleAlert,
    accent: 'text-rose-300',
    ring: 'border-rose-400/30 bg-rose-400/[0.07]',
    body: 'Execution evidence confirms a defect: a failing test, with its exact command and output attached to the receipt.',
  },
  {
    label: 'SAFE',
    icon: CircleCheck,
    accent: 'text-emerald-300',
    ring: 'border-emerald-400/30 bg-emerald-400/[0.07]',
    body: 'Sufficient positive evidence: the tests pass and the claims are supported. Never issued when evidence is ambiguous.',
  },
  {
    label: 'ESCALATE',
    icon: CircleAlert,
    accent: 'text-amber-300',
    ring: 'border-amber-400/30 bg-amber-400/[0.07]',
    body: 'Evidence is missing or conflicting, or execution failed. Fail-closed by design, so a human makes the call.',
  },
];

function VerdictsSection() {
  return (
    <section className="relative overflow-hidden rounded-[2rem] sm:rounded-[2.5rem] bg-brand-900 border border-brand-800 shadow-soft-2xl px-6 sm:px-10 lg:px-14 py-12 sm:py-16">
      <div className="absolute inset-0 bg-evidence-grid-dark pointer-events-none" />
      <div className="absolute -bottom-32 -left-24 w-96 h-96 bg-brand-500/20 rounded-full blur-3xl pointer-events-none" />

      <div className="relative space-y-10">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <SectionHeading
            dark
            eyebrow="Evidence-backed findings"
            title={
              <>
                Three verdicts. <span className="italic font-medium text-brand-300">Zero guesswork.</span>
              </>
            }
            description="Every verdict is derived from collected evidence. When Receipts cannot prove the code is safe, it does not say it is."
          />
          <Link
            to="/activity"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-full bg-white text-brand-900 text-xs font-semibold hover:bg-brand-100 transition-colors shrink-0 self-start lg:self-auto"
          >
            Browse recent verdicts <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {VERDICTS.map(({ label, icon: Icon, accent, ring, body }) => (
            <div key={label} className={`rounded-3xl border p-6 space-y-4 ${ring}`}>
              <div className={`inline-flex items-center gap-2 font-mono text-xs font-bold tracking-[0.15em] ${accent}`}>
                <Icon className="w-4 h-4" />
                {label}
              </div>
              <p className="text-sm text-brand-100 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const IMMUNITY_STAGES = [
  'Reproduce',
  'Root Cause',
  'Fix',
  'Verify',
  'Regression Test',
  'Sibling Hunt',
  'Document',
  'Pattern',
];

const REPLAY_METRICS = [
  { metric: 'catch_rate', formula: 'caught / bugs' },
  { metric: 'false_alarm_rate', formula: 'alarms / safe' },
  { metric: 'accuracy', formula: 'correct / scored' },
];

const AUDIT_CHAIN = [
  { event: 'review_started', hash: 'a41f…' },
  { event: 'receipt_created', hash: '7b0d…' },
  { event: 'verdict_created', hash: '9f2c…' },
];

function CapabilitiesSection() {
  return (
    <section className="space-y-10">
      <SectionHeading
        eyebrow="Beyond the verdict"
        title={
          <>
            Find it once. <span className="italic font-medium text-brand-700">Prove it forever.</span>
          </>
        }
        description="Receipts turns confirmed bugs into regression protection, measures itself against known outcomes, and keeps a tamper-evident record of everything it did."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card-ice lg:col-span-3 flex flex-col lg:flex-row gap-8 lg:items-center">
          <div className="space-y-3 lg:max-w-sm shrink-0">
            <div className="w-12 h-12 rounded-2xl bg-brand-900 text-white flex items-center justify-center">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <h3 className="font-serif-title font-semibold text-2xl text-brand-950">Bug-to-Immunity Pipeline</h3>
            <p className="text-sm text-brand-700 leading-relaxed">
              A confirmed bug moves through eight evidence-gated stages. Each stage must pass its gate before the
              next begins. Failed fixes are rolled back and retried, and verified fixes land in the Pattern Library.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <Link to="/immunity" className="btn-pill-primary text-xs px-5 py-2">
                Open Bug Immunity <ArrowRight className="w-3.5 h-3.5" />
              </Link>
              <Link to="/patterns" className="btn-pill-secondary text-xs px-5 py-2">
                <BookOpen className="w-3.5 h-3.5" /> Pattern Library
              </Link>
            </div>
          </div>

          <ol className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-3">
            {IMMUNITY_STAGES.map((stage, i) => (
              <li
                key={stage}
                className="rounded-2xl bg-white border border-brand-200/80 px-4 py-3 flex items-center gap-3 shadow-sm"
              >
                <span className="font-mono text-[11px] font-semibold text-brand-400">{i + 1}</span>
                <span className="text-xs font-semibold text-brand-900">{stage}</span>
              </li>
            ))}
          </ol>
        </div>

        <Link to="/replay" className="card-white group lg:col-span-1 flex flex-col gap-4 hover:border-brand-300">
          <div className="w-12 h-12 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center group-hover:bg-brand-900 group-hover:text-white transition-colors duration-300">
            <RotateCcw className="w-6 h-6" />
          </div>
          <h3 className="font-serif-title font-semibold text-xl text-brand-950">Replay Benchmarking</h3>
          <p className="text-xs text-brand-700 leading-relaxed">
            Replay known-outcome cases through the live pipeline in isolated workspaces and score every verdict
            against ground truth.
          </p>
          <div className="rounded-2xl bg-brand-50 border border-brand-200/80 p-3 font-mono text-[11px] space-y-1.5">
            {REPLAY_METRICS.map(({ metric, formula }) => (
              <div key={metric} className="flex items-center justify-between gap-2">
                <span className="text-brand-900 font-medium">{metric}</span>
                <span className="text-brand-500 text-right">{formula}</span>
              </div>
            ))}
          </div>
          <span className="mt-auto flex items-center gap-1 text-xs font-semibold text-brand-800 group-hover:text-brand-950">
            Run the benchmark <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </span>
        </Link>

        <Link to="/audit" className="card-white group lg:col-span-2 flex flex-col gap-4 hover:border-brand-300">
          <div className="w-12 h-12 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center group-hover:bg-brand-900 group-hover:text-white transition-colors duration-300">
            <FileCheck className="w-6 h-6" />
          </div>
          <h3 className="font-serif-title font-semibold text-xl text-brand-950">Cryptographic Audit Trail</h3>
          <p className="text-xs text-brand-700 leading-relaxed max-w-xl">
            Every review event is linked to the one before it with a SHA-256 hash chain. Any change to a payload,
            hash, or ordering breaks the chain and shows up on verification.
          </p>
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-0">
            {AUDIT_CHAIN.map(({ event, hash }, i) => (
              <div key={event} className="flex flex-col sm:flex-row sm:items-center">
                <div className="rounded-2xl bg-brand-50 border border-brand-200/80 px-3.5 py-2.5 font-mono text-[11px]">
                  <div className="text-brand-900 font-medium">{event}</div>
                  <div className="text-brand-400">sha256 {hash}</div>
                </div>
                {i < AUDIT_CHAIN.length - 1 && (
                  <Link2 className="w-4 h-4 text-brand-400 mx-auto sm:mx-2 my-1 sm:my-0 rotate-90 sm:rotate-0 shrink-0" />
                )}
              </div>
            ))}
          </div>
          <span className="mt-auto flex items-center gap-1 text-xs font-semibold text-brand-800 group-hover:text-brand-950">
            Verify the audit chain <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </span>
        </Link>
      </div>
    </section>
  );
}

export function LandingSections() {
  return (
    <div className="space-y-20 lg:space-y-28 py-6 lg:py-10">
      <WorkflowSection />
      <AgentsSection />
      <VerdictsSection />
      <CapabilitiesSection />
    </div>
  );
}
