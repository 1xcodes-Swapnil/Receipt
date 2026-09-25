import { NavLink, Outlet } from 'react-router-dom';

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', exact: true },
  { path: '/review', label: 'PR Review' },
  { path: '/immunity', label: 'Bug Immunity', phase: 2 },
  { path: '/replay', label: 'Replay', phase: 2 },
  { path: '/audit', label: 'Audit Trail', phase: 2 },
];

export function Layout() {
  return (
    <div className="min-h-screen bg-surface flex flex-col">
      {/* Top bar */}
      <header className="bg-white border-b border-border sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 h-12 flex items-center gap-8">
          <span className="font-semibold text-sm tracking-tight text-gray-900">
            Receipts
          </span>
          <nav className="flex items-center gap-1 text-sm">
            {NAV_ITEMS.map(({ path, label, exact, phase }) => (
              <NavLink
                key={path}
                to={path}
                end={exact}
                className={({ isActive }) =>
                  [
                    'px-3 py-1.5 rounded-md transition-colors',
                    isActive
                      ? 'bg-surface text-gray-900 font-medium'
                      : 'text-muted hover:text-gray-700 hover:bg-gray-50',
                    phase ? 'opacity-50' : '',
                  ].join(' ')
                }
              >
                {label}
                {phase && (
                  <span className="ml-1 text-xs text-gray-400">
                    P{phase}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted bg-surface border border-border px-2 py-0.5 rounded">
              Phase 1
            </span>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
