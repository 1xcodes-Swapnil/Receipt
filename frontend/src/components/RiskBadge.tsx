import type { RiskLevel } from '../types';

const CONFIG: Record<RiskLevel, string> = {
  low: 'bg-green-50 text-green-700 border-green-200',
  medium: 'bg-yellow-50 text-yellow-800 border-yellow-200',
  high: 'bg-red-50 text-red-800 border-red-200',
};

export function RiskBadge({ risk }: { risk: RiskLevel | string }) {
  const cls = CONFIG[risk as RiskLevel] ?? 'bg-gray-100 text-gray-600 border-gray-200';
  return (
    <span className={`badge border text-xs font-medium uppercase tracking-wide ${cls}`}>
      {risk} risk
    </span>
  );
}
