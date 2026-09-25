/**
 * API client for the Receipts FastAPI backend (Phase 2).
 */
import type {
  HealthResponse,
  Receipt,
  ReviewEvent,
  ReviewRequest,
  ReviewRun,
  ReviewRunDetail,
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
  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  createReview(repo: string, prNumber: number, body: ReviewRequest = {}): Promise<ReviewRun> {
    return request<ReviewRun>(`/repos/${encodeURIComponent(repo)}/prs/${prNumber}/review`, {
      method: 'POST',
      body: JSON.stringify(body),
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

  /**
   * Open an SSE connection for a review run.
   * Returns an EventSource. Caller must close it when done.
   */
  streamReview(runId: string): EventSource {
    return new EventSource(`${BASE_URL}/reviews/${runId}/stream`);
  },
};
