import type { Severity } from '../types';

interface Props {
  severity: Severity;
}

const CONFIG: Record<Severity, { label: string; classes: string }> = {
  PASS: { label: 'PASS', classes: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  INFO: { label: 'INFO', classes: 'bg-blue-100 text-blue-800 border-blue-300' },
  LOW: { label: 'LOW', classes: 'bg-slate-100 text-slate-800 border-slate-300' },
  MEDIUM: { label: 'MEDIUM', classes: 'bg-amber-100 text-amber-800 border-amber-300' },
  HIGH: { label: 'HIGH', classes: 'bg-orange-100 text-orange-800 border-orange-300' },
  CRITICAL: { label: 'CRITICAL', classes: 'bg-rose-100 text-rose-800 border-rose-300' },
};

export function SeverityBadge({ severity }: Props) {
  const config = CONFIG[severity] ?? { label: severity, classes: 'bg-gray-100 text-gray-800' };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wider uppercase border ${config.classes}`}
    >
      {config.label}
    </span>
  );
}
