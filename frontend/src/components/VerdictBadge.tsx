import type { Verdict } from '../types';
import { CheckCircle2, AlertTriangle, AlertCircle, HelpCircle } from 'lucide-react';

interface Props {
  verdict: Verdict | null;
  size?: 'sm' | 'md' | 'lg';
}

const CONFIG: Record<Verdict, { label: string; classes: string; icon: React.ElementType }> = {
  SAFE: {
    label: 'SAFE',
    classes: 'bg-emerald-50 text-emerald-700 border border-emerald-200/80 shadow-sm',
    icon: CheckCircle2,
  },
  BUG_DETECTED: {
    label: 'BUG DETECTED',
    classes: 'bg-rose-50 text-rose-700 border border-rose-200/80 shadow-sm',
    icon: AlertTriangle,
  },
  ESCALATE: {
    label: 'ESCALATE',
    classes: 'bg-amber-50 text-amber-800 border border-amber-200/80 shadow-sm',
    icon: AlertCircle,
  },
};

export function VerdictBadge({ verdict, size = 'md' }: Props) {
  if (!verdict) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-500 border border-gray-200">
        <HelpCircle className="w-3.5 h-3.5" />
        PENDING
      </span>
    );
  }

  const { label, classes, icon: Icon } = CONFIG[verdict];
  const sizeClasses = {
    sm: 'px-2.5 py-0.5 text-xs gap-1',
    md: 'px-3.5 py-1 text-xs gap-1.5',
    lg: 'px-4 py-1.5 text-sm gap-2',
  }[size];

  return (
    <span className={`inline-flex items-center font-bold tracking-wider rounded-full ${classes} ${sizeClasses}`}>
      <Icon className={size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-4 h-4' : 'w-3.5 h-3.5'} />
      {label}
    </span>
  );
}
