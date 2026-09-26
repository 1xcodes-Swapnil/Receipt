import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import type { PatternLibraryEntry } from '../types';
import { Spinner } from '../components/Spinner';
import { ErrorMessage } from '../components/ErrorMessage';
import { TerminalViewer } from '../components/TerminalViewer';
import {
  BookOpen,
  Search,
  Filter,
  X
} from 'lucide-react';

export default function PatternLibrary() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryParam = searchParams.get('q') || '';

  const [patterns, setPatterns] = useState<PatternLibraryEntry[]>([]);
  const [searchQuery, setSearchQuery] = useState(queryParam);
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedPattern, setSelectedPattern] = useState<PatternLibraryEntry | null>(null);

  const loadPatterns = async () => {
    setLoading(true);
    setError(null);
    try {
      let data: PatternLibraryEntry[];
      if (searchQuery.trim()) {
        data = await api.searchPatterns(searchQuery.trim());
      } else {
        data = await api.listPatterns(selectedArea || undefined);
      }
      setPatterns(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch pattern library');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPatterns();
  }, [searchQuery, selectedArea]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery) {
      setSearchParams({ q: searchQuery });
    } else {
      setSearchParams({});
    }
    loadPatterns();
  };

  const areas = ['all', 'statistics', 'math', 'validation', 'concurrency', 'types'];

  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-8">
      
      {/* Header Banner */}
      <div className="card-ice flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-900 text-white text-xs font-semibold mb-2">
            <BookOpen className="w-3.5 h-3.5 text-brand-300" />
            Verified Pattern Library Catalog
          </div>
          <h1 className="font-serif-title font-bold text-2xl sm:text-3xl text-brand-950">
            Bug Signatures & Regression Tests
          </h1>
          <p className="text-brand-700 text-xs mt-1 max-w-2xl">
            Contains patterns extracted from completed Immunity pipelines. Every entry includes signature, affected area, and regression test reference.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-brand-900 bg-white px-3.5 py-1.5 rounded-full border border-brand-200">
            {patterns.length} Patterns Active
          </span>
        </div>
      </div>

      {/* Controls Bar: Search & Category Filter Pills */}
      <div className="card-white space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-lg">
            <Search className="w-4 h-4 text-brand-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search patterns by description, signature, or keyword..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 bg-brand-50 border border-brand-200 rounded-full text-xs font-medium text-brand-900 placeholder:text-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white"
            />
          </form>

          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
            <Filter className="w-3.5 h-3.5 text-brand-500 shrink-0" />
            {areas.map((area) => {
              const isSelected = (area === 'all' && !selectedArea) || selectedArea === area;
              return (
                <button
                  key={area}
                  onClick={() => setSelectedArea(area === 'all' ? null : area)}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-semibold capitalize whitespace-nowrap transition-all ${
                    isSelected
                      ? 'bg-brand-900 text-white'
                      : 'bg-brand-50 text-brand-800 border border-brand-200 hover:bg-brand-100'
                  }`}
                >
                  {area}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {error && <ErrorMessage message={error} />}

      {loading ? (
        <div className="py-12 text-center">
          <Spinner label="Searching pattern library entries..." />
        </div>
      ) : patterns.length === 0 ? (
        <div className="card-white text-center py-16 space-y-3">
          <BookOpen className="w-12 h-12 text-brand-300 mx-auto" />
          <h3 className="font-serif-title font-bold text-lg text-brand-950">No Patterns Found</h3>
          <p className="text-xs text-brand-600">Try clearing your search filter or selecting a different affected area.</p>
          <button
            onClick={() => {
              setSearchQuery('');
              setSelectedArea(null);
              setSearchParams({});
            }}
            className="btn-pill-secondary text-xs"
          >
            Clear Search Filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {patterns.map((p) => (
            <div
              key={p.id}
              onClick={() => setSelectedPattern(p)}
              className="card-white group cursor-pointer hover:border-brand-400 transition-all duration-300 flex flex-col justify-between space-y-4"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-brand-100 text-brand-800 border border-brand-200">
                    {p.affected_area || 'General'}
                  </span>
                  <span className="text-[11px] font-mono text-brand-400">#{p.id.slice(0, 6)}</span>
                </div>

                <h3 className="font-semibold text-sm text-brand-950 group-hover:text-brand-700 transition-colors line-clamp-2">
                  {p.description}
                </h3>

                <code className="block text-[11px] font-mono bg-brand-50 p-2 rounded-xl text-brand-800 border border-brand-200/60 truncate">
                  {p.pattern_signature}
                </code>
              </div>

              <div className="pt-3 border-t border-brand-100 flex items-center justify-between text-xs text-brand-600">
                <span className="truncate max-w-[180px]">
                  Test: {p.regression_test_ref || 'pytest'}
                </span>
                <span className="font-semibold text-brand-900 group-hover:translate-x-1 transition-transform">
                  View Detail →
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pattern Detail Modal */}
      {selectedPattern && (
        <div className="fixed inset-0 z-50 bg-brand-950/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="card-white max-w-2xl w-full max-h-[90vh] overflow-y-auto space-y-6 animate-scale-up">
            <div className="flex items-start justify-between border-b border-brand-100 pb-4">
              <div>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-brand-900 text-white uppercase tracking-wider">
                  Pattern Detail
                </span>
                <h2 className="font-serif-title font-bold text-xl text-brand-950 mt-1">
                  {selectedPattern.description}
                </h2>
              </div>
              <button
                onClick={() => setSelectedPattern(null)}
                className="text-brand-400 hover:text-brand-950 p-1.5 rounded-full hover:bg-brand-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <span className="text-brand-500 font-semibold block mb-1">Pattern Signature</span>
                <code className="block bg-brand-50 p-3 rounded-xl border border-brand-200 font-mono text-brand-950 text-xs">
                  {selectedPattern.pattern_signature}
                </code>
              </div>

              {selectedPattern.regression_test_ref && (
                <div>
                  <span className="text-brand-500 font-semibold block mb-1">Regression Test Reference</span>
                  <code className="block bg-brand-50 p-3 rounded-xl border border-brand-200 font-mono text-emerald-800 text-xs">
                    {selectedPattern.regression_test_ref}
                  </code>
                </div>
              )}

              {selectedPattern.metadata_json && (
                <TerminalViewer
                  title="Pattern Metadata JSON"
                  output={selectedPattern.metadata_json}
                />
              )}
            </div>

            <div className="pt-4 border-t border-brand-100 flex justify-end">
              <button
                onClick={() => setSelectedPattern(null)}
                className="btn-pill-primary text-xs"
              >
                Close Modal
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
