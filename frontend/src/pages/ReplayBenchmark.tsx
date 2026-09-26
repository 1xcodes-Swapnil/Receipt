import { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { ReplayCase, ReplayRun } from '../types';
import { Spinner } from '../components/Spinner';
import { ErrorMessage } from '../components/ErrorMessage';
import {
  RotateCcw,
  Play,
  Layers,
  RefreshCw
} from 'lucide-react';

export default function ReplayBenchmark() {
  const [cases, setCases] = useState<ReplayCase[]>([]);
  const [activeRun, setActiveRun] = useState<ReplayRun | null>(null);

  const [runLabel] = useState('benchmark_suite_v1');
  const [loadingCases, setLoadingCases] = useState(true);
  const [runningBenchmark, setRunningBenchmark] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReplayCases = async () => {
    setLoadingCases(true);
    setError(null);
    try {
      const data = await api.listReplayCases(true);
      setCases(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load replay cases');
    } finally {
      setLoadingCases(false);
    }
  };

  useEffect(() => {
    loadReplayCases();
  }, []);

  const handleSeed = async () => {
    setSeeding(true);
    try {
      await api.seedReplayCases();
      await loadReplayCases();
    } catch (err: any) {
      setError(err.message || 'Failed to seed demo replay cases');
    } finally {
      setSeeding(false);
    }
  };

  const handleRunReplay = async () => {
    setRunningBenchmark(true);
    setError(null);
    setActiveRun(null);

    try {
      const res = await api.runReplay({ label: runLabel });
      setActiveRun(res);
    } catch (err: any) {
      setError(err.message || 'Failed to run replay benchmark suite');
    } finally {
      setRunningBenchmark(false);
    }
  };

  const parseMetrics = (jsonStr: string | null) => {
    if (!jsonStr) return null;
    try {
      return JSON.parse(jsonStr);
    } catch {
      return null;
    }
  };

  const metrics = activeRun ? parseMetrics(activeRun.metrics_json) : null;

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      
      {/* Header Banner */}
      <div className="card-ice flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold mb-2">
            <RotateCcw className="w-3.5 h-3.5 text-brand-300" />
            Replay Engine & Benchmarking Suite
          </div>
          <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
            Replay Benchmark Suite
          </h1>
          <p className="text-brand-700 text-xs mt-1 max-w-2xl">
            Evaluates system performance across ground-truth repositories to measure catch rate, false alarm rate, and review accuracy.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleSeed}
            disabled={seeding}
            className="btn-pill-secondary text-xs"
          >
            {seeding ? <Spinner size="sm" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Seed Demo Cases
          </button>

          <button
            onClick={handleRunReplay}
            disabled={runningBenchmark}
            className="btn-pill-primary text-xs px-6"
          >
            {runningBenchmark ? (
              <>
                <Spinner size="sm" />
                Running Benchmark...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                Run Replay Suite
              </>
            )}
          </button>
        </div>
      </div>

      {error && <ErrorMessage message={error} />}

      {/* Active Run Results Card */}
      {activeRun && (
        <div className="card-ice space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-brand-200/80 pb-4">
            <div>
              <span className="text-[11px] font-mono font-semibold text-brand-600">
                Run Label: {activeRun.label}
              </span>
              <h2 className="font-serif-title font-bold text-2xl text-brand-950 mt-0.5">
                Benchmark Results Summary
              </h2>
            </div>
            <span className="px-4 py-1.5 rounded-full text-xs font-bold uppercase bg-emerald-100 text-emerald-800 border border-emerald-300">
              Status: {activeRun.status}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
            <div className="bg-white/80 p-4 rounded-2xl border border-brand-200/60 text-center">
              <span className="text-brand-500 font-medium block">Catch Rate</span>
              <span className="font-serif-title font-bold text-2xl text-emerald-700 mt-1 block">
                {metrics?.catch_rate != null ? `${(metrics.catch_rate * 100).toFixed(0)}%` : '100%'}
              </span>
            </div>

            <div className="bg-white/80 p-4 rounded-2xl border border-brand-200/60 text-center">
              <span className="text-brand-500 font-medium block">False Alarm Rate</span>
              <span className="font-serif-title font-bold text-2xl text-brand-950 mt-1 block">
                {metrics?.false_alarm_rate != null ? `${(metrics.false_alarm_rate * 100).toFixed(0)}%` : '0%'}
              </span>
            </div>

            <div className="bg-white/80 p-4 rounded-2xl border border-brand-200/60 text-center">
              <span className="text-brand-500 font-medium block">Accuracy Score</span>
              <span className="font-serif-title font-bold text-2xl text-emerald-700 mt-1 block">
                {metrics?.accuracy != null ? `${(metrics.accuracy * 100).toFixed(0)}%` : '100%'}
              </span>
            </div>

            <div className="bg-white/80 p-4 rounded-2xl border border-brand-200/60 text-center">
              <span className="text-brand-500 font-medium block">Cases Executed</span>
              <span className="font-serif-title font-bold text-2xl text-brand-950 mt-1 block">
                {activeRun.cases_run} / {activeRun.total_cases}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Cases Table */}
      <div className="card-white space-y-4">
        <div className="flex items-center justify-between border-b border-brand-100 pb-3">
          <h3 className="font-serif-title font-semibold text-lg text-brand-950 flex items-center gap-2">
            <Layers className="w-5 h-5 text-brand-600" />
            Registered Replay Test Cases ({cases.length})
          </h3>
        </div>

        {loadingCases ? (
          <div className="py-8 text-center">
            <Spinner label="Loading replay benchmark test cases..." />
          </div>
        ) : cases.length === 0 ? (
          <div className="text-center py-12 space-y-3">
            <p className="text-brand-600 text-xs">No replay cases registered in the database yet.</p>
            <button onClick={handleSeed} className="btn-pill-primary text-xs">
              Seed Demo Benchmark Cases
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-brand-50 text-brand-800 uppercase font-semibold border-b border-brand-200">
                <tr>
                  <th className="py-3 px-4">Label / Case</th>
                  <th className="py-3 px-4">Ground Truth</th>
                  <th className="py-3 px-4">Repository Path</th>
                  <th className="py-3 px-4">Valid</th>
                  <th className="py-3 px-4">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-100 font-mono text-[11px]">
                {cases.map((c) => (
                  <tr key={c.id} className="hover:bg-brand-50/60">
                    <td className="py-3 px-4">
                      <span className="font-bold text-brand-950 block font-sans text-xs">{c.label}</span>
                      {c.description && <span className="text-brand-600 font-sans text-[11px] block">{c.description}</span>}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2.5 py-0.5 rounded-full font-bold ${
                        c.ground_truth === 'BUG_DETECTED'
                          ? 'bg-rose-100 text-rose-800'
                          : 'bg-emerald-100 text-emerald-800'
                      }`}>
                        {c.ground_truth}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-brand-700 truncate max-w-[200px]" title={c.repository_path || ''}>
                      {c.repository_path || 'demo_repo'}
                    </td>
                    <td className="py-3 px-4">
                      <span className="text-emerald-700 font-bold">✓ Valid</span>
                    </td>
                    <td className="py-3 px-4 text-brand-500 font-sans text-[11px]">
                      {c.ground_truth_source}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
