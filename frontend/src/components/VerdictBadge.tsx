import type { Verdict } from '../types';

interface Props {
  verdict: Verdict | null;
  size?: 'sm' | 'md';
}

const CONFIG: Record<Verdict, { label: string; classes: string }> = {
  SAFE: {
    label: 'SAFE',
    classes: 'bg-green-100 text-green-800 border border-green-200',
  },
  BUG_DETECTED: {
    label: 'BUG DETECTED',
    classes: 'bg-red-100 text-red-800 border border-red-200',
  },
  ESCALATE: {
    label: 'ESCALATE',
    classes: 'bg-yellow-100 text-yellow-800 border border-yellow-200',
  },
};

export function VerdictBadge({ verdict, size = 'md' }: Props) {
  if (!verdict) {
    return (
      <span className={`badge bg-gray-100 text-gray-500 border border-gray-200 ${size === 'sm' ? 'text-xs' : 'text-sm'}`}>
        —
      </span>
    );
  }
  const { label, classes } = CONFIG[verdict];
  return (
    <span className={`badge ${classes} ${size === 'sm' ? 'text-xs' : 'text-sm'} font-semibold tracking-wide`}>
      {label}
    </span>
  );
}
