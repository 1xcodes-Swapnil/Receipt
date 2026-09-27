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
  FileText,
  X,
  ExternalLink,
} from 'lucide-react';

function GithubIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
    </svg>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();

  // Quick form state
  const [repoName, setRepoName] = useState('demo_repo');
  const [prNumber, setPrNumber] = useState('1');
  const [prTitle, setPrTitle] = useState('Fix statistics mean function bug');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // GitHub Repo Selector Modal state
  const [isGithubModalOpen, setIsGithubModalOpen] = useState(false);
  const [githubUrlInput, setGithubUrlInput] = useState('');
  const [githubInputError, setGithubInputError] = useState<string | null>(null);

  const handleSelectGithubRepo = (repoPath: string) => {
    let cleaned = repoPath.trim();
    if (cleaned.startsWith('http://') || cleaned.startsWith('https://')) {
      try {
        const url = new URL(cleaned);
        cleaned = url.pathname.replace(/^\//, '').replace(/\.git$/, '');
      } catch {
        // keep raw string
      }
    }

    if (!cleaned) {
      setGithubInputError('Please enter a valid GitHub repository name or URL');
      return;
    }

    setRepoName(cleaned);
    setIsGithubModalOpen(false);
    setGithubUrlInput('');
    setGithubInputError(null);
  };

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

            <form onSubmit={handleQuickTrigger} className="space-y-4">
              {/* Repository Name Field & Add from GitHub Button */}
              <div>
                <div className="flex items-center justify-between mb-1.5 gap-2 flex-wrap">
                  <label className="block text-[11px] font-semibold text-brand-800 uppercase tracking-wider">
                    Repository Name
                  </label>
                  {repoName !== 'demo_repo' && (
                    <button
                      type="button"
                      onClick={() => setRepoName('demo_repo')}
                      className="text-xs text-brand-600 hover:text-brand-950 underline font-medium cursor-pointer"
                      title="Reset back to default demo_repo"
                    >
                      Reset to demo_repo
                    </button>
                  )}
                </div>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
                  <input
                    type="text"
                    required
                    value={repoName}
                    onChange={(e) => setRepoName(e.target.value)}
                    className="flex-1 px-3.5 py-2.5 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white font-mono min-w-0"
                  />
                  <button
                    type="button"
                    onClick={() => setIsGithubModalOpen(true)}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold text-brand-950 bg-white hover:bg-brand-100 border border-brand-300 hover:border-brand-400 rounded-xl shadow-2xs transition-all cursor-pointer whitespace-nowrap shrink-0"
                  >
                    <span className="text-brand-700 font-bold text-sm leading-none">+</span>
                    <GithubIcon className="w-4 h-4 text-brand-900 shrink-0" />
                    <span>Add from GitHub</span>
                  </button>
                </div>
              </div>

              {/* PR Number Field */}
              <div>
                <label className="block text-[11px] font-semibold text-brand-800 uppercase tracking-wider mb-1.5">
                  PR Number
                </label>
                <input
                  type="number"
                  required
                  min={1}
                  value={prNumber}
                  onChange={(e) => setPrNumber(e.target.value)}
                  className="w-full sm:w-1/3 px-3.5 py-2.5 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white font-mono"
                />
              </div>

              {/* PR Title / Description Field */}
              <div>
                <label className="block text-[11px] font-semibold text-brand-800 uppercase tracking-wider mb-1.5">
                  PR Title / Description
                </label>
                <input
                  type="text"
                  required
                  value={prTitle}
                  onChange={(e) => setPrTitle(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
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

      {/* GitHub Repository Selector Modal */}
      {isGithubModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-brand-950/60 backdrop-blur-sm animate-fade-in"
          onClick={() => setIsGithubModalOpen(false)}
        >
          <div
            className="card-white w-full max-w-lg space-y-5 shadow-2xl rounded-2xl border border-brand-200 p-6 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-brand-100 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-brand-900 text-white flex items-center justify-center font-bold text-sm shadow-sm">
                  <GithubIcon className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h3 className="font-serif-title font-bold text-lg text-brand-950">Select GitHub Repository</h3>
                  <p className="text-brand-600 text-xs">Enter a GitHub repository URL or owner/repository path</p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setIsGithubModalOpen(false)}
                className="p-1.5 rounded-full hover:bg-brand-100 text-brand-500 hover:text-brand-950 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3.5">
              <div>
                <label className="block text-[11px] font-semibold text-brand-800 uppercase tracking-wider mb-1">
                  GitHub Repository URL or Path
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="e.g. https://github.com/facebook/react or owner/repo"
                    value={githubUrlInput}
                    onChange={(e) => {
                      setGithubUrlInput(e.target.value);
                      setGithubInputError(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handleSelectGithubRepo(githubUrlInput);
                      }
                    }}
                    className="flex-1 px-3.5 py-2 text-xs bg-brand-50 border border-brand-200 rounded-xl text-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => handleSelectGithubRepo(githubUrlInput)}
                    className="btn-pill-primary text-xs shrink-0 px-4"
                  >
                    Select
                  </button>
                </div>
                {githubInputError && (
                  <p className="text-rose-600 text-xs mt-1 font-medium">{githubInputError}</p>
                )}
              </div>

              {/* Quick Popular GitHub Repositories */}
              <div className="space-y-1.5 pt-1">
                <span className="text-[11px] font-medium text-brand-600 block">Popular GitHub Repositories:</span>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    'facebook/react',
                    'pallets/flask',
                    'python/cpython',
                    'vercel/next.js',
                    'torvalds/linux',
                  ].map((repo) => (
                    <button
                      key={repo}
                      type="button"
                      onClick={() => handleSelectGithubRepo(repo)}
                      className="px-2.5 py-1 rounded-full bg-brand-50 hover:bg-brand-100 text-brand-900 border border-brand-200 text-xs font-mono font-medium transition-colors"
                    >
                      {repo}
                    </button>
                  ))}
                </div>
              </div>

              {/* Informational Notice regarding GitHub Backend Status */}
              <div className="bg-brand-50 p-3 rounded-xl border border-brand-200 text-[11px] text-brand-700 leading-relaxed flex items-start gap-2">
                <ExternalLink className="w-4 h-4 text-brand-500 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-brand-900">Backend Integration Status:</strong> Selecting a remote GitHub repository populates the field. Note: the current backend Review Orchestrator runs parallel agents locally against <code className="bg-brand-200 px-1 rounded font-mono text-[10px]">demo_repo</code>. Remote repository cloning & API integration require backend token setup.
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-brand-100">
              <button
                type="button"
                onClick={() => setIsGithubModalOpen(false)}
                className="btn-pill-secondary text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleSelectGithubRepo('demo_repo')}
                className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-brand-200 hover:bg-brand-300 text-brand-950 transition-colors"
              >
                Reset to demo_repo
              </button>
            </div>
          </div>
        </div>
      )}

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
