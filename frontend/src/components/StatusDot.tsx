import type { AgentStatus } from '../types';

interface Props {
  status: AgentStatus;
}

const CONFIG: Record<AgentStatus, { label: string; dot: string }> = {
  pending: { label: 'Pending', dot: 'bg-gray-400' },
  running: { label: 'Running', dot: 'bg-blue-500 animate-pulse' },
  completed: { label: 'Completed', dot: 'bg-green-500' },
  error: { label: 'Error', dot: 'bg-red-500' },
  timeout: { label: 'Timeout', dot: 'bg-orange-500' },
  insufficient_evidence: { label: 'Insufficient Evidence', dot: 'bg-yellow-500' },
};

export function StatusDot({ status }: Props) {
  const { label, dot } = CONFIG[status] ?? CONFIG.pending;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
      <span className="text-sm text-gray-600">{label}</span>
    </span>
  );
}
