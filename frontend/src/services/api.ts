/**
 * Comprehensive API client for the Receipts FastAPI backend.
 */
import type {
  AuditEvent,
  AuditVerification,
  DemoLogExecution,
  EvidenceGap,
  EvidenceItem,
  HealthResponse,
  ImmunityPipeline,
  ImmunityPipelineDetail,
  ImmunityRequest,
  ImmunityStage,
  PatternLibraryEntry,
  Receipt,
  ReceiptTicket,
  ReplayCase,
  ReplayRequest,
  ReplayResult,
  ReplayRun,
  ReviewClaim,
  ReviewEvent,
  ReviewRequest,
  ReviewRun,
  ReviewRunDetail,
  StrategyTraceEntry,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      detail = JSON.parse(text)?.detail ?? text;
    } catch {
      // use raw text
    }
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }

  return res.json() as Promise<T>;
}

export const api = {
  // System Health
  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  // Code Reviews
  createReview(repo: string, prNumber: number, body: ReviewRequest = {}): Promise<ReviewRun> {
    const trimmedRepo = repo.trim();
    const safePathRepo = trimmedRepo === 'demo_repo' ? 'demo_repo' : encodeURIComponent(trimmedRepo);
    const payload = { repo_name: trimmedRepo, ...body };
    return request<ReviewRun>(`/repos/${safePathRepo}/prs/${prNumber}/review`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getReview(runId: string): Promise<ReviewRunDetail> {
    return request<ReviewRunDetail>(`/reviews/${runId}`);
  },

  getReceipts(runId: string): Promise<Receipt[]> {
    return request<Receipt[]>(`/reviews/${runId}/receipts`);
  },

  getEvents(runId: string): Promise<ReviewEvent[]> {
    return request<ReviewEvent[]>(`/reviews/${runId}/events`);
  },

  streamReview(runId: string): EventSource {
    return new EventSource(`${BASE_URL}/reviews/${runId}/stream`);
  },

  // Immunity Pipeline
  startImmunity(runId: string, body: ImmunityRequest = {}): Promise<ImmunityPipeline> {
    return request<ImmunityPipeline>(`/reviews/${runId}/immunity`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  getImmunityPipeline(pipelineId: string): Promise<ImmunityPipelineDetail> {
    return request<ImmunityPipelineDetail>(`/immunity/${pipelineId}`);
  },

  getImmunityStages(pipelineId: string): Promise<ImmunityStage[]> {
    return request<ImmunityStage[]>(`/immunity/${pipelineId}/stages`);
  },

  // Pattern Library
  listPatterns(affectedArea?: string, limit = 50, offset = 0): Promise<PatternLibraryEntry[]> {
    const params = new URLSearchParams();
    if (affectedArea) params.set('affected_area', affectedArea);
    params.set('limit', limit.toString());
    params.set('offset', offset.toString());
    return request<PatternLibraryEntry[]>(`/patterns?${params.toString()}`);
  },

  searchPatterns(query: string, limit = 20): Promise<PatternLibraryEntry[]> {
    const params = new URLSearchParams({ q: query, limit: limit.toString() });
    return request<PatternLibraryEntry[]>(`/patterns/search?${params.toString()}`);
  },

  getPattern(patternId: string): Promise<PatternLibraryEntry> {
    return request<PatternLibraryEntry>(`/patterns/${patternId}`);
  },

  // Replay Engine
  listReplayCases(includeInvalid = false): Promise<ReplayCase[]> {
    return request<ReplayCase[]>(`/replay/cases?include_invalid=${includeInvalid}`);
  },

  getReplayCase(caseId: string): Promise<ReplayCase> {
    return request<ReplayCase>(`/replay/cases/${caseId}`);
  },

  getCaseResults(caseId: string): Promise<ReplayResult[]> {
    return request<ReplayResult[]>(`/replay/cases/${caseId}/results`);
  },

  runReplay(body: ReplayRequest = {}): Promise<ReplayRun> {
    return request<ReplayRun>('/replay/run', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  getReplayRun(runId: string): Promise<ReplayRun> {
    return request<ReplayRun>(`/replay/runs/${runId}`);
  },

  seedReplayCases(): Promise<ReplayCase[]> {
    return request<ReplayCase[]>('/replay/seed', { method: 'POST' });
  },

  validateReplayCases(): Promise<{ valid: number; invalid: number; total: number }> {
    return request<{ valid: number; invalid: number; total: number }>('/replay/validate', {
      method: 'POST',
    });
  },

  // Audit Verification
  getAuditEvents(runId: string): Promise<AuditEvent[]> {
    return request<AuditEvent[]>(`/reviews/${runId}/audit`);
  },

  verifyAuditChain(runId: string): Promise<AuditVerification> {
    return request<AuditVerification>(`/reviews/${runId}/audit/verify`);
  },

  // Adaptive Evidence (Phase 5+)
  getEvidence(runId: string): Promise<EvidenceItem[]> {
    return request<EvidenceItem[]>(`/reviews/${runId}/evidence`);
  },

  getClaims(runId: string): Promise<ReviewClaim[]> {
    return request<ReviewClaim[]>(`/reviews/${runId}/claims`);
  },

  getEvidenceGaps(runId: string): Promise<EvidenceGap[]> {
    return request<EvidenceGap[]>(`/reviews/${runId}/evidence-gaps`);
  },

  getStrategyTrace(runId: string): Promise<StrategyTraceEntry[]> {
    return request<StrategyTraceEntry[]>(`/reviews/${runId}/strategy-trace`);
  },

  // Demo Log 6 Phases & Receipt Tickets
  getDemoLogExecution(): Promise<DemoLogExecution> {
    return request<DemoLogExecution>('/demo/log');
  },

  getReceiptTicket(receiptId: string): Promise<ReceiptTicket> {
    return request<ReceiptTicket>(`/receipts/${receiptId}`);
  },
};
