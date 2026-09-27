import { useState, useEffect } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { api } from '../services/api';
import {
  ShieldCheck,
  Zap,
  RotateCcw,
  BookOpen,
  Search,
  Activity,
  PlusCircle,
  FileCheck,
  CheckCircle2,
  ExternalLink,
  ArrowRight,
  FileText
} from 'lucide-react';

export function Layout() {
  const [healthStatus, setHealthStatus] = useState<{ status: string; version: string } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    api.health()
      .then((data) => setHealthStatus(data))
      .catch(() => setHealthStatus(null));
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/patterns?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: Activity },
    { to: '/demo', label: 'Demo Execution', icon: Zap },
    { to: '/activity', label: 'PR Activity Logs', icon: FileText },
    { to: '/review', label: 'Trigger Review', icon: PlusCircle },
    { to: '/immunity', label: 'Bug Immunity V7', icon: ShieldCheck },
    { to: '/patterns', label: 'Pattern Library', icon: BookOpen },
    { to: '/replay', label: 'Replay Benchmark', icon: RotateCcw },
    { to: '/audit', label: 'Audit Trail', icon: FileCheck },
  ];

  return (
    <div className="min-h-screen bg-brand-50 flex flex-col font-sans text-brand-900 selection:bg-brand-200 w-full max-w-full overflow-x-hidden">
      
      {/* Top Announcement / Health Banner */}
      <div className="bg-brand-200/90 text-brand-900 border-b border-brand-300/70 px-4 py-2 text-xs font-medium backdrop-blur-sm">
        <div className="w-[98%] mx-auto flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 bg-brand-900 text-white text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider shrink-0">
              IBM BOB
            </span>
            <span className="text-brand-900 text-[11px] sm:text-xs">
              <strong>NO EVIDENCE, NO FLAG.</strong> Findings backed by executable test evidence.
            </span>
          </div>

          <div className="flex items-center gap-3 sm:gap-4 text-[11px] shrink-0">
            <span className="flex items-center gap-1.5 font-medium">
              <span className={`w-2 h-2 rounded-full ${healthStatus ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
              {healthStatus ? `Backend Online (v${healthStatus.version})` : 'Backend Connecting...'}
            </span>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-brand-800 hover:text-brand-950 flex items-center gap-1 font-semibold hover:underline"
            >
              OpenAPI Docs <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </div>

      {/* Main Header / Navigation Bar */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-brand-200/80 shadow-sm w-full">
        <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-3.5 flex flex-wrap items-center justify-between gap-3">
          
          {/* Brand Logo & Tagline */}
          <NavLink to="/" className="flex items-center gap-3 group shrink-0">
            <div className="w-10 h-10 rounded-2xl bg-brand-900 text-white flex items-center justify-center font-serif-title font-bold text-xl shadow-soft-xl group-hover:scale-105 transition-transform duration-200">
              R
            </div>
            <div className="flex items-center gap-2">
              <span className="font-serif-title font-bold text-xl tracking-tight text-brand-950 group-hover:text-brand-700 transition-colors">
                Receipts
              </span>
              <span className="hidden md:inline-block text-[11px] font-semibold px-2.5 py-0.5 bg-brand-100 text-brand-800 rounded-full border border-brand-200">
                Evidence-First Review
              </span>
            </div>
          </NavLink>

          {/* Center Navigation Links - Desktop */}
          <nav className="hidden xl:flex items-center gap-1 bg-brand-50/90 p-1.5 rounded-full border border-brand-200/70">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive: isExact }) =>
                    `flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 whitespace-nowrap ${
                      isExact || (item.to !== '/' && location.pathname.startsWith(item.to))
                        ? 'bg-brand-900 text-white shadow-sm'
                        : 'text-brand-800 hover:text-brand-950 hover:bg-white/80'
                    }`
                  }
                >
                  <Icon className="w-3.5 h-3.5" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>

          {/* Right Action Controls: Search & Primary Button */}
          <div className="flex items-center gap-3 shrink-0">
            <form onSubmit={handleSearchSubmit} className="relative hidden lg:block">
              <Search className="w-3.5 h-3.5 text-brand-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search pattern library..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-2 bg-brand-50 border border-brand-200 text-xs font-medium rounded-full text-brand-900 placeholder:text-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:bg-white w-40 lg:w-48 transition-all duration-200"
              />
            </form>

            <button
              onClick={() => navigate('/review')}
              className="btn-pill-primary text-xs shrink-0 px-5 py-2.5 whitespace-nowrap shadow-md hover:shadow-lg"
            >
              <Zap className="w-3.5 h-3.5 text-amber-300" />
              <span>Run New Review</span>
            </button>
          </div>
        </div>

        {/* Navigation Bar for Mobile and Laptops (< XL breakpoint) */}
        <div className="xl:hidden bg-brand-50/95 border-t border-brand-200 px-4 py-2 overflow-x-auto flex items-center gap-2 scrollbar-none">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.to || (item.to !== '/' && location.pathname.startsWith(item.to));

            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={`whitespace-nowrap flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold shrink-0 transition-all ${
                  isActive ? 'bg-brand-900 text-white shadow-sm' : 'bg-white text-brand-800 border border-brand-200 hover:bg-brand-100'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {item.label}
              </NavLink>
            );
          })}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 w-full max-w-full overflow-x-hidden">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="bg-brand-100/80 border-t border-brand-200/80 pt-12 pb-10 text-brand-900 w-full">
        <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-10">
            
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-brand-900 text-white flex items-center justify-center font-serif-title font-bold text-lg">
                  R
                </div>
                <span className="font-serif-title font-bold text-lg text-brand-950">Receipts</span>
              </div>
              <p className="text-xs text-brand-700 leading-relaxed">
                Evidence-First AI Code Review & Bug Immunity system. Powered by cryptographic audit receipts and automated fix verification.
              </p>
            </div>

            <div>
              <h4 className="font-serif-title font-semibold text-sm text-brand-950 mb-3">Core Workflows</h4>
              <ul className="space-y-2 text-xs text-brand-800">
                <li><NavLink to="/dashboard" className="hover:text-brand-950">Review Orchestrator & Metrics</NavLink></li>
                <li><NavLink to="/activity" className="hover:text-brand-950">PR Activity & Review Logs</NavLink></li>
                <li><NavLink to="/immunity" className="hover:text-brand-950">Bug-to-Immunity V7 Pipeline</NavLink></li>
                <li><NavLink to="/patterns" className="hover:text-brand-950">Pattern Library Catalog</NavLink></li>
                <li><NavLink to="/replay" className="hover:text-brand-950">Replay Benchmark Suite</NavLink></li>
              </ul>
            </div>

            <div>
              <h4 className="font-serif-title font-semibold text-sm text-brand-950 mb-3">Verification & Invariants</h4>
              <ul className="space-y-2 text-xs text-brand-800">
                <li><NavLink to="/audit" className="hover:text-brand-950">Cryptographic SHA-256 Chain</NavLink></li>
                <li><a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="hover:text-brand-950">FastAPI OpenAPI Specification</a></li>
                <li><span className="text-brand-600">Executable Pytest Receipts</span></li>
              </ul>
            </div>

            <div className="space-y-3">
              <h4 className="font-serif-title font-semibold text-sm text-brand-950">Built with IBM Bob</h4>
              <p className="text-xs text-brand-700 leading-relaxed">
                Every bug finding produces a cryptographic audit receipt — missing evidence returns ESCALATE.
              </p>
              <button
                onClick={() => navigate('/review')}
                className="btn-pill-primary text-xs w-full justify-center"
              >
                Start Automated Review <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

          </div>

          <div className="pt-6 border-t border-brand-200/80 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-brand-600">
            <p>© {new Date().getFullYear()} Receipts — Evidence-First AI Code Review. All rights reserved.</p>
            <p className="flex items-center gap-1 font-mono text-[11px]">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> API Server: http://localhost:8000
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
