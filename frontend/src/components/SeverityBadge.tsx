import type { Severity } from '../types';

interface Props {
  severity: Severity;
}

const CONFIG: Record<Severity, string> = {
  PASS: 'bg-green-100 text-green-800 border-green-200',
  INFO: 'bg-blue-50 text-blue-700 border-blue-200',
  LOW: 'bg-sky-100 text-sky-700 border-sky-200',
  MEDIUM: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  HIGH: 'bg-orange-100 text-orange-800 border-orange-200',
  CRITICAL: 'bg-red-100 text-red-800 border-red-200',
};

export function SeverityBadge({ severity }: Props) {
  return (
    <span className={`badge border ${CONFIG[severity] ?? CONFIG.INFO} text-xs font-medium`}>
      {severity}
    </span>
  );
}
