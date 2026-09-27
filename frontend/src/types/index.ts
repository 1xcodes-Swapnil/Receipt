// Receipts — Complete TypeScript Type Definitions (All Backend Entities & APIs)

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
export type ImmunityStatus =
  | 'pending'
  | 'running'
  | 'passed'
  | 'failed'
  | 'blocked'
  | 'escalated';

export interface Repository {
  id: string;
  name: string;
  url: string | null;
  local_path: string | null;
  created_at: string;
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
  bob_evidence_ref?: string | null;
  created_at: string;
}

export interface ReceiptTicket extends Receipt {
  repo?: string;
  pr_number?: number;
  verdict?: string;
  risk_level?: string;
  phase_source?: string;
}

export interface DemoLogExecution {
  raw_log_path: string;
  start_time: string;
  log_dir: string;
  phases: Array<{
    phase_number: number;
    name: string;
    status: string;
    duration_ms: number;
    items?: Array<{ name: string; details: string; status: string }>;
    repository?: string;
    run_id?: string;
    verdict?: string;
    risk?: string;
    elapsed_ms?: number;
    strategy_trace?: Array<{
      step: number;
      strategy: string;
      result: string;
      reason: string;
      confidence: number;
    }>;
    fail_receipts_count?: number;
    receipts?: Array<{
      receipt_id: string;
      severity: string;
      title: string;
      agent: string;
      command: string;
    }>;
    pipeline_id?: string;
    overall_status?: string;
    workspace_path?: string;
    stages?: Array<{ stage: string; status: string; duration_ms: number | null }>;
    metrics?: {
      cases_seeded: number;
      valid_cases: number;
      invalid_cases: number;
      catch_rate: number;
      false_alarm_pct: number;
      accuracy: number;
      caught_bugs: number;
      missed_bugs: number;
      false_alarms: number;
    };
    cases?: Array<{ case_id: string; verdict: string; correct: boolean }>;
    audit?: {
      valid: boolean;
      total_events: number;
      error_count: number;
      run_id: string;
      intact: boolean;
    };
  }>;
  summary: {
    verdict: string;
    confidence: number;
    elapsed_ms: number;
    strategies_run: number;
    evidence_items: number;
    immunity_status: string;
    replay_accuracy: number;
    catch_rate: number;
    false_alarms: number;
    audit_valid: boolean;
    audit_events: number;
  };
}

export interface ReviewRunDetail extends ReviewRun {
  pull_request: PullRequest | null;
  agent_executions: AgentExecution[];
  receipts: Receipt[];
}

export interface ReviewRequest {
  pr_title?: string;
  author?: string;
  base_branch?: string;
  head_branch?: string;
  commit_sha?: string;
}

export interface ReviewEvent {
  id?: string;
  event_type: string;
  review_run_id: string;
  agent_type: string | null;
  payload?: string | null;
  timestamp?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface HealthResponse {
  status: string;
  version: string;
}

// ---------------------------------------------------------------------------
// Immunity Pipeline
// ---------------------------------------------------------------------------

export interface ImmunityStage {
  id: string;
  pipeline_id: string;
  stage_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  evidence: string | null;
  error: string | null;
  artifact_ref: string | null;
  created_at: string;
}

export interface SiblingFinding {
  id: string;
  pipeline_id: string;
  candidate_location: string;
  similarity_reason: string | null;
  confidence: number;
  verification_status: string;
  evidence: string | null;
  created_at: string;
}

export interface ImmunityPipeline {
  id: string;
  review_run_id: string;
  status: ImmunityStatus;
  source_receipt_ids: string | null;
  current_stage: string | null;
  created_at: string;
  updated_at: string;
}

export interface ImmunityPipelineDetail extends ImmunityPipeline {
  stages: ImmunityStage[];
  sibling_findings: SiblingFinding[];
}

export interface ImmunityRequest {
  source_receipt_ids?: string[];
}

// ---------------------------------------------------------------------------
// Pattern Library
// ---------------------------------------------------------------------------

export interface PatternLibraryEntry {
  id: string;
  pattern_signature: string;
  description: string;
  source_pipeline_id: string | null;
  regression_test_ref: string | null;
  affected_area: string | null;
  metadata_json: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Replay Engine
// ---------------------------------------------------------------------------

export interface ReplayCase {
  id: string;
  label: string;
  description: string | null;
  repository_path: string | null;
  included_files: string | null;
  ground_truth: string;
  ground_truth_source: string;
  ground_truth_notes: string | null;
  is_valid: boolean;
  validation_error: string | null;
  created_at: string;
}

export interface ReplayResult {
  id: string;
  replay_case_id: string;
  verdict: Verdict | null;
  correct: boolean | null;
  caught_bug: boolean | null;
  false_alarm: boolean | null;
  missed_bug: boolean | null;
  escalated: boolean | null;
  execution_failed: boolean;
  elapsed_ms: number | null;
  review_run_id: string | null;
  output: string | null;
  error: string | null;
  planner_trace_json: string | null;
  strategies_used: string | null;
  strategy_count: number | null;
  created_at: string;
}

export interface ReplayRun {
  id: string;
  label: string | null;
  status: string;
  metrics_json: string | null;
  total_cases: number;
  cases_run: number;
  cases_failed: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ReplayRequest {
  case_ids?: string[];
  label?: string;
}

// ---------------------------------------------------------------------------
// Audit Verification
// ---------------------------------------------------------------------------

export interface AuditEvent {
  id: string;
  review_run_id: string | null;
  event_type: string;
  payload: string | null;
  canonical_payload: string | null;
  integrity_hash: string | null;
  prev_hash: string | null;
  entity_ref: string | null;
  sequence: number | null;
  created_at: string;
}

export interface AuditVerification {
  valid: boolean;
  total_events: number;
  error_count: number;
  errors: Array<{ event_id?: string; detail: string; [key: string]: unknown }>;
}

// ---------------------------------------------------------------------------
// Adaptive Evidence Core (Phase 5+)
// ---------------------------------------------------------------------------

export interface EvidenceItem {
  id: string;
  review_run_id: string;
  claim_id: string | null;
  strategy_name: string;
  evidence_type: string | null;
  result: string;
  confidence: number;
  command: string | null;
  raw_output: string | null;
  file_ref: string | null;
  line_ref: number | null;
  is_independent: boolean;
  depends_on_evidence_id: string | null;
  created_at: string;
}

export interface ReviewClaim {
  id: string;
  review_run_id: string;
  claim_type: string;
  claim_text: string;
  status: string;
  verdict_contribution: string;
  created_at: string;
}

export interface EvidenceGap {
  id: string;
  review_run_id: string;
  claim_id: string | null;
  gap_type: string;
  description: string;
  suggested_strategy: string | null;
  resolved: boolean;
  created_at: string;
}

export interface StrategyTraceEntry {
  id: string;
  review_run_id: string;
  step_number: number;
  claim_id: string | null;
  strategy_name: string;
  selection_reason: string | null;
  prerequisites_met: boolean;
  execution_result: string | null;
  evidence_item_id: string | null;
  remaining_gap: string | null;
  next_decision: string | null;
  stopping_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
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
  documentation_check: 'Documentation Check',
  history_check: 'History Check',
};
