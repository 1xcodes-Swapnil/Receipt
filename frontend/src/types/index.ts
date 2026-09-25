// Receipts — TypeScript type definitions (Phase 2)

export type Verdict = 'SAFE' | 'BUG_DETECTED' | 'ESCALATE';
export type ReviewStatus = 'pending' | 'running' | 'completed' | 'failed';
export type AgentStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'error'
  | 'timeout'
  | 'insufficient_evidence';
export type AgentType =
  | 'test_runner'
  | 'catching_test'
  | 'documentation_check'
  | 'history_check';
export type Severity = 'PASS' | 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type RiskLevel = 'low' | 'medium' | 'high';

export interface ReviewRun {
  id: string;
  pr_id: string;
  risk_level: RiskLevel;
  status: ReviewStatus;
  confidence: number | null;
  verdict: Verdict | null;
  started_at: string | null;
  completed_at: string | null;
  elapsed_ms: number | null;
}

export interface AgentExecution {
  id: string;
  review_run_id: string;
  agent_type: AgentType;
  status: AgentStatus;
  started_at: string | null;
  completed_at: string | null;
}

export interface Receipt {
  id: string;
  review_run_id: string;
  agent_execution_id: string;
  agent: string | null;
  title: string;
  command: string | null;
  test_ref: string | null;
  result_summary: string;
  raw_output: string | null;
  file_ref: string | null;
  severity: Severity;
  confidence: number;
  created_at: string;
}

export interface ReviewRunDetail extends ReviewRun {
  pull_request: PullRequest | null;
  agent_executions: AgentExecution[];
  receipts: Receipt[];
}

export interface PullRequest {
  id: string;
  repo_id: string;
  number: number;
  title: string;
  author: string | null;
  base_branch: string;
  head_branch: string | null;
  commit_sha: string | null;
  created_at: string;
}

export interface ReviewRequest {
  pr_title?: string;
  author?: string;
  base_branch?: string;
  head_branch?: string;
  commit_sha?: string;
}

export interface ReviewEvent {
  event_type: string;
  review_run_id: string;
  agent_type: string | null;
  timestamp: string;
  [key: string]: unknown;
}

export interface HealthResponse {
  status: string;
  version: string;
}

// Live agent state derived from SSE events
export interface AgentCard {
  agent_type: AgentType;
  label: string;
  status: AgentStatus;
  result: string | null;
  receipt_count: number;
  duration_ms: number | null;
  started_at: number | null;
}

export const AGENT_LABELS: Record<string, string> = {
  test_runner: 'Test Runner',
  catching_test: 'Catching Test',
  documentation_check: 'Documentation',
  history_check: 'History',
};
