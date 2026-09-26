import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../services/api';
import type { ReviewRun, ReplayCase } from '../types';
import { MetricsAnalytics } from '../components/MetricsAnalytics';
import { Spinner } from '../components/Spinner';
import {
  ShieldCheck,
  Zap,
  RotateCcw,
  BookOpen,
  ArrowRight,
  PlusCircle,
  Play,
  FileText
} from 'lucide-react';

export default function Dashboard() {
  const navigate = useNavigate();

  // Quick form state
  const [repoName, setRepoName] = useState('demo_repo');
  const [prNumber, setPrNumber] = useState('1');
  const [prTitle, setPrTitle] = useState('Fix statistics mean function bug');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // System stats state for metrics analytics
  const [replayCases, setReplayCases] = useState<ReplayCase[]>([]);
  const [recentReviews, setRecentReviews] = useState<ReviewRun[]>([]);

  useEffect(() => {
    async function loadDashboardData() {
      try {
        const cases = await api.listReplayCases(true).catch(() => []);
        setReplayCases(cases);

        // Load saved review history from localStorage if present
        const saved = localStorage.getItem('receipts_review_history');
        if (saved) {
          try {
            setRecentReviews(JSON.parse(saved));
          } catch {
            // ignore
          }
        }
      } catch {
        // ignore
      }
    }
    loadDashboardData();
  }, []);

  const handleQuickTrigger = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setFormError(null);

    try {
      const review = await api.createReview(repoName.trim(), parseInt(prNumber, 10), {
        pr_title: prTitle,
        base_branch: 'main',
      });

      // Save to recent reviews in localStorage for activity log tracking
      const updated = [review, ...recentReviews];
      setRecentReviews(updated);
      localStorage.setItem('receipts_review_history', JSON.stringify(updated));

      navigate(`/reviews/${review.id}`);
    } catch (err: any) {
      setFormError(err.message || 'Failed to trigger review');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-10">
      
      {/* Visual Hero Section matching the layout philosophy of the reference image */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
        
        {/* Left Hero Card - Ice Blue Background & Large Serif Header */}
        <div className="lg:col-span-7 card-ice flex flex-col justify-between relative overflow-hidden">
          <div className="absolute -right-12 -top-12 w-64 h-64 bg-brand-300/30 rounded-full blur-3xl pointer-events-none" />

          <div className="space-y-4 relative z-10">
            <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold uppercase tracking-wider shadow-sm">
              <ShieldCheck className="w-3.5 h-3.5 text-brand-300" />
              Evidence-First AI Code Review
            </div>

            <h1 className="font-serif-title font-bold text-3xl sm:text-4xl text-brand-950 leading-tight">
              No evidence, no flag. <br />
              <span className="italic text-brand-700 font-normal">Cryptographically backed bug immunity.</span>
            </h1>

            <p className="text-brand-800 text-sm leading-relaxed max-w-xl">
              Receipts treats code review as an <strong>evidence collection problem</strong>. Every bug finding produces an executable receipt containing exact commands, raw outputs, and verified results. Missing evidence returns <code>ESCALATE</code>.
            </p>
          </div>

          <div className="pt-8 flex flex-wrap items-center gap-4 relative z-10">
            <button
              onClick={() => navigate('/review')}
              className="btn-pill-primary"
            >
              <Zap className="w-4 h-4 text-amber-300" />
              Trigger Live Review
            </button>
            
            <Link
              to="/activity"
              className="btn-pill-secondary"
            >
              <FileText className="w-4 h-4 text-brand-600" />
              PR Activity Logs
            </Link>
          </div>
        </div>

        {/* Right Hero Card - Quick PR Review Launcher */}
        <div className="lg:col-span-5 card-white flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-serif-title font-semibold text-lg text-brand-950 flex items-center gap-2">
                <PlusCircle className="w-5 h-5 text-brand-600" />
                Quick Review Launcher
              </h3>
              <span className="text-[11px] font-semibold text-brand-600 bg-brand-100 px-2.5 py-1 rounded-full">
                Parallel 4-Agent Execution
              </span>
            </div>

            <p className="text-xs text-brand-700 mb-5">
              Launch an immediate review on a target repository and pull request.
            </p>

            {formError && (
              <div className="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-2xl">
                {formError}
              </div>
            )}

            <form onSubmit={handleQuickTrigger} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-brand-800 uppercase tracking-wider mb-1">
                    Repository Name
                  </label>
                  <input
                    type="text"
                    required
                    value={repoName}
                    onChange={(e) => setRepoName(e.target.value)}
                    className="w-full px-3.5 py-2 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-brand-800 uppercase tracking-wider mb-1">
                    PR Number
                  </label>
                  <input
                    type="number"
                    required
                    min={1}
                    value={prNumber}
                    onChange={(e) => setPrNumber(e.target.value)}
                    className="w-full px-3.5 py-2 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-brand-800 uppercase tracking-wider mb-1">
                  PR Title / Description
                </label>
                <input
                  type="text"
                  required
                  value={prTitle}
                  onChange={(e) => setPrTitle(e.target.value)}
                  className="w-full px-3.5 py-2 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
                />
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full btn-pill-primary py-3 justify-center text-xs mt-2"
              >
                {isSubmitting ? (
                  <>
                    <Spinner size="sm" />
                    Running Parallel Agents...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    Start Review Workflow
                  </>
                )}
              </button>
            </form>
          </div>

          <div className="mt-4 pt-3 border-t border-brand-100 flex items-center justify-between text-[11px] text-brand-600">
            <span>Runs TestRunner, CatchingTest, DocCheck, History</span>
            <span className="font-semibold text-brand-900">Adaptive Planner (14 Strategies)</span>
          </div>
        </div>

      </div>

      {/* Feature 1: Metrics & Analytics Section */}
      <MetricsAnalytics
        recentReviews={recentReviews}
        replayCases={replayCases}
      />

      {/* Feature Navigation Cards - Clean 4-Grid inspired by visual reference */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        
        <Link
          to="/activity"
          className="card-white group hover:border-brand-300 transition-all duration-300 flex flex-col justify-between"
        >
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center group-hover:bg-brand-900 group-hover:text-white transition-colors duration-300">
              <FileText className="w-6 h-6" />
            </div>
            <h3 className="font-serif-title font-semibold text-lg text-brand-950 group-hover:text-brand-700 transition-colors">
              PR Activity Logs
            </h3>
            <p className="text-xs text-brand-700 leading-relaxed">
              Color-coded activity stream for GOOD, BAD, ESCALATE, and IN PROGRESS pull requests.
            </p>
          </div>
          <div className="pt-4 flex items-center gap-1 text-xs font-semibold text-brand-800 group-hover:text-brand-950">
            View Activity Stream <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </Link>

        <Link
          to="/immunity"
          className="card-white group hover:border-brand-300 transition-all duration-300 flex flex-col justify-between"
        >
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center group-hover:bg-brand-900 group-hover:text-white transition-colors duration-300">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <h3 className="font-serif-title font-semibold text-lg text-brand-950 group-hover:text-brand-700 transition-colors">
              Bug Immunity V7
            </h3>
            <p className="text-xs text-brand-700 leading-relaxed">
              8-stage evidence-gated pipeline: Reproduce, RootCause, Fix, Verify, SiblingHunt, Document & Pattern.
            </p>
          </div>
          <div className="pt-4 flex items-center gap-1 text-xs font-semibold text-brand-800 group-hover:text-brand-950">
            Explore Immunity Pipeline <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </Link>

        <Link
          to="/patterns"
          className="card-white group hover:border-brand-300 transition-all duration-300 flex flex-col justify-between"
        >
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center group-hover:bg-brand-900 group-hover:text-white transition-colors duration-300">
              <BookOpen className="w-6 h-6" />
            </div>
            <h3 className="font-serif-title font-semibold text-lg text-brand-950 group-hover:text-brand-700 transition-colors">
              Pattern Library
            </h3>
            <p className="text-xs text-brand-700 leading-relaxed">
              Searchable catalog of verified bug signatures, regression test references, and immunity patterns.
            </p>
          </div>
          <div className="pt-4 flex items-center gap-1 text-xs font-semibold text-brand-800 group-hover:text-brand-950">
            Browse Patterns <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </Link>

        <Link
          to="/replay"
          className="card-white group hover:border-brand-300 transition-all duration-300 flex flex-col justify-between"
        >
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-brand-100 text-brand-900 flex items-center justify-center group-hover:bg-brand-900 group-hover:text-white transition-colors duration-300">
              <RotateCcw className="w-6 h-6" />
            </div>
            <h3 className="font-serif-title font-semibold text-lg text-brand-950 group-hover:text-brand-700 transition-colors">
              Replay Benchmark
            </h3>
            <p className="text-xs text-brand-700 leading-relaxed">
              Run replay benchmark suites across target cases to evaluate catch rate, false alarms, and accuracy.
            </p>
          </div>
          <div className="pt-4 flex items-center gap-1 text-xs font-semibold text-brand-800 group-hover:text-brand-950">
            Run Benchmark Suite <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </Link>

      </div>

      {/* Preset Demo Scenarios */}
      <div className="card-ice">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <h3 className="font-serif-title font-bold text-xl text-brand-950">
              Quick Benchmark & Demo Scenarios
            </h3>
            <p className="text-xs text-brand-700 mt-1">
              Select any pre-configured pull request scenario to see the 4 agents and strategy planner in action.
            </p>
          </div>

          <button
            onClick={() => navigate('/review')}
            className="btn-pill-secondary text-xs shrink-0 self-start md:self-auto"
          >
            Custom Review Form
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          
          <div
            onClick={() => {
              setRepoName('demo_repo');
              setPrNumber('1');
              setPrTitle('Fix mean calculation on empty array');
            }}
            className="bg-white p-4 rounded-2xl border border-brand-200 shadow-sm cursor-pointer hover:border-brand-400 hover:shadow-md transition-all"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-rose-100 text-rose-800">
                BUG PRESENT
              </span>
              <span className="text-[11px] font-mono text-brand-500">demo_repo #1</span>
            </div>
            <h4 className="font-semibold text-xs text-brand-950 mb-1">
              Stats Mean Division by Zero
            </h4>
            <p className="text-[11px] text-brand-600 line-clamp-2">
              Triggers TestRunner failure receipt, CatchingTest verification, and Immunity root cause analysis.
            </p>
          </div>

          <div
            onClick={() => {
              setRepoName('demo_repo');
              setPrNumber('2');
              setPrTitle('Refactor math utility helper functions');
            }}
            className="bg-white p-4 rounded-2xl border border-brand-200 shadow-sm cursor-pointer hover:border-brand-400 hover:shadow-md transition-all"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                SAFE PR
              </span>
              <span className="text-[11px] font-mono text-brand-500">demo_repo #2</span>
            </div>
            <h4 className="font-semibold text-xs text-brand-950 mb-1">
              Math Helper Refactoring
            </h4>
            <p className="text-[11px] text-brand-600 line-clamp-2">
              All test suites pass cleanly. High confidence SAFE verdict returned with execution receipts.
            </p>
          </div>

          <div
            onClick={() => {
              setRepoName('demo_repo');
              setPrNumber('3');
              setPrTitle('Update documentation and add edge case tests');
            }}
            className="bg-white p-4 rounded-2xl border border-brand-200 shadow-sm cursor-pointer hover:border-brand-400 hover:shadow-md transition-all"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-800">
                DOCUMENTATION GAP
              </span>
              <span className="text-[11px] font-mono text-brand-500">demo_repo #3</span>
            </div>
            <h4 className="font-semibold text-xs text-brand-950 mb-1">
              DocCheck Discrepancy
            </h4>
            <p className="text-[11px] text-brand-600 line-clamp-2">
              Evaluates docstring claims against AST definition to detect parameter mismatch gaps.
            </p>
          </div>

        </div>
      </div>

    </div>
  );
}
