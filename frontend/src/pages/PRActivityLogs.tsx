import { useState, useEffect, useMemo } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../services/api';
import type { ReviewRun, ReplayCase } from '../types';
import { RiskBadge } from '../components/RiskBadge';
import { Spinner } from '../components/Spinner';
import { ErrorMessage } from '../components/ErrorMessage';
import {
  FileText,
  Search,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ArrowRight,
  GitPullRequest,
  HelpCircle,
  Tag,
  FileCheck
} from 'lucide-react';

export interface ActivityEntry {
  id: string;
  prNumber: number | string;
  prTitle: string;
  repo: string;
  author: string;
  timestamp: string;
  status: 'completed' | 'running' | 'pending' | 'failed';
  resultLabel: 'GOOD' | 'BAD' | 'ESCALATE' | 'IN PROGRESS';
  verdict: 'SAFE' | 'BUG_DETECTED' | 'ESCALATE' | null;
  riskLevel: 'low' | 'medium' | 'high' | null;
  elapsedMs: number | null;
  receiptsCount: number;
}

export default function PRActivityLogs() {
  const navigate = useNavigate();

  const [recentReviews, setRecentReviews] = useState<ReviewRun[]>([]);
  const [replayCases, setReplayCases] = useState<ReplayCase[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterResult, setFilterResult] = useState<string>('ALL');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch registered cases
      const cases = await api.listReplayCases(true).catch(() => []);
      setReplayCases(cases);

      // Load saved activity history from localStorage if available
      const savedLocal = localStorage.getItem('receipts_review_history');
      if (savedLocal) {
        try {
          const parsed = JSON.parse(savedLocal);
          setRecentReviews(parsed);
        } catch {
          // ignore
        }
      }

      setLoading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to load PR activity logs');
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Map backend entities and stored review runs into structured Activity Entries
  const activityList = useMemo<ActivityEntry[]>(() => {
    const list: ActivityEntry[] = [];

    // 1. Map stored review runs
    recentReviews.forEach((r) => {
      let resultLabel: 'GOOD' | 'BAD' | 'ESCALATE' | 'IN PROGRESS' = 'GOOD';
      if (r.status === 'running' || r.status === 'pending') {
        resultLabel = 'IN PROGRESS';
      } else if (r.verdict === 'BUG_DETECTED') {
        resultLabel = 'BAD';
      } else if (r.verdict === 'ESCALATE') {
        resultLabel = 'ESCALATE';
      } else {
        resultLabel = 'GOOD';
      }

      list.push({
        id: r.id,
        prNumber: r.pr_id ? `#${r.pr_id.slice(0, 4)}` : '#1',
        prTitle: 'Pull Request Review Run',
        repo: 'demo_repo',
        author: 'developer',
        timestamp: r.started_at || new Date().toISOString(),
        status: r.status,
        resultLabel,
        verdict: r.verdict,
        riskLevel: r.risk_level,
        elapsedMs: r.elapsed_ms,
        receiptsCount: 4,
      });
    });

    // 2. Map replay test cases if list is short
    replayCases.forEach((c, idx) => {
      const isBad = c.ground_truth === 'BUG_DETECTED';
      list.push({
        id: c.id,
        prNumber: `#${idx + 1}`,
        prTitle: c.label,
        repo: c.repository_path || 'demo_repo',
        author: c.ground_truth_source || 'benchmark',
        timestamp: c.created_at || new Date().toISOString(),
        status: 'completed',
        resultLabel: isBad ? 'BAD' : 'GOOD',
        verdict: isBad ? 'BUG_DETECTED' : 'SAFE',
        riskLevel: isBad ? 'high' : 'low',
        elapsedMs: 3220,
        receiptsCount: 4,
      });
    });

    // Default demo entries if empty
    if (list.length === 0) {
      list.push(
        {
          id: 'demo-run-1',
          prNumber: '#1',
          prTitle: 'Fix statistics mean division by zero bug',
          repo: 'demo_repo',
          author: 'dev1',
          timestamp: new Date().toISOString(),
          status: 'completed',
          resultLabel: 'BAD',
          verdict: 'BUG_DETECTED',
          riskLevel: 'high',
          elapsedMs: 3223,
          receiptsCount: 4,
        },
        {
          id: 'demo-run-2',
          prNumber: '#2',
          prTitle: 'Refactor math utility helper functions',
          repo: 'demo_repo',
          author: 'dev2',
          timestamp: new Date(Date.now() - 3600000).toISOString(),
          status: 'completed',
          resultLabel: 'GOOD',
          verdict: 'SAFE',
          riskLevel: 'low',
          elapsedMs: 1450,
          receiptsCount: 4,
        },
        {
          id: 'demo-run-3',
          prNumber: '#3',
          prTitle: 'Update documentation and add edge case tests',
          repo: 'demo_repo',
          author: 'dev3',
          timestamp: new Date(Date.now() - 7200000).toISOString(),
          status: 'completed',
          resultLabel: 'ESCALATE',
          verdict: 'ESCALATE',
          riskLevel: 'medium',
          elapsedMs: 2100,
          receiptsCount: 2,
        }
      );
    }

    return list;
  }, [recentReviews, replayCases]);

  // Filtered List
  const filteredList = useMemo(() => {
    return activityList.filter((item) => {
      const matchesSearch =
        searchQuery.trim() === '' ||
        item.prTitle.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.repo.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.prNumber.toString().includes(searchQuery) ||
        item.author.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesFilter =
        filterResult === 'ALL' ||
        (filterResult === 'GOOD' && item.resultLabel === 'GOOD') ||
        (filterResult === 'BAD' && item.resultLabel === 'BAD') ||
        (filterResult === 'ESCALATE' && item.resultLabel === 'ESCALATE') ||
        (filterResult === 'IN_PROGRESS' && item.resultLabel === 'IN PROGRESS');

      return matchesSearch && matchesFilter;
    });
  }, [activityList, searchQuery, filterResult]);

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      {/* Header Banner */}
      <div className="card-ice flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold mb-2">
            <FileText className="w-3.5 h-3.5 text-brand-300" />
            PR Review Activity & Log Stream
          </div>
          <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
            PR Activity Logs
          </h1>
          <p className="text-brand-700 text-xs mt-1 max-w-2xl">
            Audit activity stream displaying PR number, repository, date/time, risk level, verdict, receipt counts, and color-coded outcomes.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/review')}
            className="btn-pill-primary text-xs"
          >
            Trigger New Review
          </button>
        </div>
      </div>

      {/* Controls & Filter Bar */}
      <div className="card-white space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-brand-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search PR title, repository, or author..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 bg-brand-50 border border-brand-200 rounded-full text-xs font-medium text-brand-900 placeholder:text-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </div>

          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
            <Filter className="w-3.5 h-3.5 text-brand-500 shrink-0" />
            
            {[
              { id: 'ALL', label: 'All Activity' },
              { id: 'GOOD', label: 'GOOD (SAFE)', color: 'emerald' },
              { id: 'BAD', label: 'BAD (BUG)', color: 'rose' },
              { id: 'ESCALATE', label: 'ESCALATE', color: 'amber' },
              { id: 'IN_PROGRESS', label: 'IN PROGRESS', color: 'blue' },
            ].map((f) => {
              const isSelected = filterResult === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => setFilterResult(f.id)}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all ${
                    isSelected
                      ? 'bg-brand-900 text-white shadow-sm'
                      : 'bg-brand-50 text-brand-800 border border-brand-200 hover:bg-brand-100'
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {error && <ErrorMessage message={error} />}

      {loading ? (
        <div className="py-12 text-center">
          <Spinner label="Loading PR activity history log..." />
        </div>
      ) : filteredList.length === 0 ? (
        <div className="card-white text-center py-16 space-y-3">
          <FileText className="w-12 h-12 text-brand-300 mx-auto" />
          <h3 className="font-serif-title font-bold text-lg text-brand-950">No PR Activity Found</h3>
          <p className="text-xs text-brand-600">No review log entries match your selected filter criteria.</p>
          <button
            onClick={() => {
              setSearchQuery('');
              setFilterResult('ALL');
            }}
            className="btn-pill-secondary text-xs"
          >
            Clear Filters
          </button>
        </div>
      ) : (
        /* PR Activity Table View - Responsive & Zero Horizontal Scroll */
        <div className="card-white p-0 overflow-hidden">
          {/* Desktop / Laptop Table View */}
          <div className="hidden md:block w-full">
            <table className="w-full text-left text-xs table-fixed border-collapse">
              <colgroup>
                <col className="w-[14%]" />
                <col className="w-[28%]" />
                <col className="w-[11%]" />
                <col className="w-[9%]" />
                <col className="w-[9%]" />
                <col className="w-[7%]" />
                <col className="w-[15%]" />
                <col className="w-[7%]" />
              </colgroup>
              <thead className="bg-brand-50 border-b border-brand-200 text-brand-800 uppercase font-semibold">
                <tr>
                  <th className="py-3 px-3">Verdict / Result</th>
                  <th className="py-3 px-3">PR Number & Title</th>
                  <th className="py-3 px-3">Repository</th>
                  <th className="py-3 px-3">Risk Level</th>
                  <th className="py-3 px-3">Receipts</th>
                  <th className="py-3 px-3">Duration</th>
                  <th className="py-3 px-3">Date & Time</th>
                  <th className="py-3 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-100">
                {filteredList.map((item) => {
                  const badgeConfig = {
                    GOOD: 'bg-emerald-100 text-emerald-800 border-emerald-300',
                    BAD: 'bg-rose-100 text-rose-800 border-rose-300',
                    ESCALATE: 'bg-amber-100 text-amber-900 border-amber-300',
                    'IN PROGRESS': 'bg-blue-100 text-blue-800 border-blue-300',
                  }[item.resultLabel];

                  const Icon =
                    item.resultLabel === 'GOOD'
                      ? CheckCircle2
                      : item.resultLabel === 'BAD'
                      ? AlertTriangle
                      : item.resultLabel === 'ESCALATE'
                      ? HelpCircle
                      : Clock;

                  return (
                    <tr key={item.id} className="hover:bg-brand-50/60 transition-colors">
                      {/* Verdict / Result */}
                      <td className="py-3 px-3 align-middle">
                        <div className="flex flex-col gap-1 items-start">
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border shadow-sm ${badgeConfig}`}
                          >
                            <Icon className="w-3 h-3 shrink-0" />
                            {item.resultLabel}
                          </span>
                          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-brand-100 text-brand-900 border border-brand-200 font-mono font-bold">
                            <Tag className="w-2.5 h-2.5 text-brand-500 shrink-0" />
                            {item.verdict || 'SAFE'}
                          </span>
                        </div>
                      </td>

                      {/* PR Number & Title */}
                      <td className="py-3 px-3 align-middle">
                        <div className="flex items-start gap-2 min-w-0">
                          <GitPullRequest className="w-3.5 h-3.5 text-brand-500 shrink-0 mt-0.5" />
                          <div className="min-w-0 flex-1 break-words">
                            <span className="font-bold text-brand-950 block text-xs">{item.prNumber}</span>
                            <span className="text-brand-700 font-medium block text-[11px] leading-tight break-words">{item.prTitle}</span>
                          </div>
                        </div>
                      </td>

                      {/* Repository */}
                      <td className="py-3 px-3 align-middle font-mono text-brand-900 font-semibold text-[11px] break-all">
                        {item.repo}
                      </td>

                      {/* Risk Level */}
                      <td className="py-3 px-3 align-middle">
                        <RiskBadge risk={item.riskLevel} size="sm" />
                      </td>

                      {/* Receipts Count */}
                      <td className="py-3 px-3 align-middle font-mono font-bold text-brand-900">
                        <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-brand-50 border border-brand-200 text-brand-800 whitespace-nowrap">
                          <FileCheck className="w-3 h-3 text-brand-600 shrink-0" />
                          {item.receiptsCount}
                        </span>
                      </td>

                      {/* Execution Duration */}
                      <td className="py-3 px-3 align-middle font-mono text-brand-800 text-[11px] whitespace-nowrap">
                        {item.elapsedMs != null ? `${(item.elapsedMs / 1000).toFixed(2)}s` : '—'}
                      </td>

                      {/* Date & Time */}
                      <td className="py-3 px-3 align-middle text-brand-600 text-[11px] leading-tight">
                        {item.timestamp ? (
                          <div>
                            <span className="font-medium text-brand-900 block">{new Date(item.timestamp).toLocaleDateString()}</span>
                            <span className="text-[10px] text-brand-500 block">{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                          </div>
                        ) : '—'}
                      </td>

                      {/* Action Link */}
                      <td className="py-3 px-3 align-middle text-right">
                        <Link
                          to={`/reviews/${item.id}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-900 hover:text-brand-600 hover:underline whitespace-nowrap"
                        >
                          Inspect <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile / Tablet Responsive Card List */}
          <div className="block md:hidden divide-y divide-brand-100">
            {filteredList.map((item) => {
              const badgeConfig = {
                GOOD: 'bg-emerald-100 text-emerald-800 border-emerald-300',
                BAD: 'bg-rose-100 text-rose-800 border-rose-300',
                ESCALATE: 'bg-amber-100 text-amber-900 border-amber-300',
                'IN PROGRESS': 'bg-blue-100 text-blue-800 border-blue-300',
              }[item.resultLabel];

              const Icon =
                item.resultLabel === 'GOOD'
                  ? CheckCircle2
                  : item.resultLabel === 'BAD'
                  ? AlertTriangle
                  : item.resultLabel === 'ESCALATE'
                  ? HelpCircle
                  : Clock;

              return (
                <div key={item.id} className="p-4 space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${badgeConfig}`}>
                        <Icon className="w-3 h-3" />
                        {item.resultLabel}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-brand-100 text-brand-900 border border-brand-200 font-mono font-bold">
                        {item.verdict || 'SAFE'}
                      </span>
                    </div>
                    <RiskBadge risk={item.riskLevel} size="sm" />
                  </div>

                  <div>
                    <div className="flex items-center gap-1.5 text-xs font-bold text-brand-950">
                      <GitPullRequest className="w-3.5 h-3.5 text-brand-500 shrink-0" />
                      <span>{item.prNumber}</span>
                    </div>
                    <p className="text-xs text-brand-700 mt-0.5 font-medium leading-relaxed">{item.prTitle}</p>
                  </div>

                  <div className="flex flex-wrap items-center justify-between text-[11px] text-brand-600 gap-2 pt-1 border-t border-brand-50">
                    <span className="font-mono text-brand-800 font-semibold">{item.repo}</span>
                    <div className="flex items-center gap-3">
                      <span>{item.receiptsCount} receipts</span>
                      <span>{item.elapsedMs != null ? `${(item.elapsedMs / 1000).toFixed(2)}s` : '—'}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[11px] pt-1">
                    <span className="text-brand-500">{item.timestamp ? new Date(item.timestamp).toLocaleString() : '—'}</span>
                    <Link
                      to={`/reviews/${item.id}`}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-brand-900 hover:text-brand-600"
                    >
                      Inspect <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
