import type { RiskLevel } from '../types';
import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react';

interface Props {
  risk: RiskLevel | null;
  size?: 'sm' | 'md';
}

const CONFIG: Record<RiskLevel, { label: string; classes: string; icon: React.ElementType }> = {
  low: {
    label: 'Low Risk',
    classes: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
    icon: ShieldCheck,
  },
  medium: {
    label: 'Medium Risk',
    classes: 'bg-amber-50 text-amber-700 border border-amber-200',
    icon: Shield,
  },
  high: {
    label: 'High Risk',
    classes: 'bg-rose-50 text-rose-700 border border-rose-200',
    icon: ShieldAlert,
  },
};

export function RiskBadge({ risk, size = 'md' }: Props) {
  if (!risk) return <span className="text-gray-400 text-xs">—</span>;
  const { label, classes, icon: Icon } = CONFIG[risk];
  return (
    <span
      className={`inline-flex items-center gap-1 px-3 py-1 rounded-full ${
        size === 'sm' ? 'text-xs' : 'text-xs font-semibold'
      } ${classes}`}
    >
      <Icon className="w-3.5 h-3.5" />
      {label}
    </span>
  );
}
