import { apiRequest, buildQuery } from "./client";

export interface DailySummaryReport {
  summaryId: string;
  reportDate: string;
  content?: string | null;
  stat: "queued" | "complete" | "failed";
  generatedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export const dailySummaryApi = {
  list(query: { date?: string; text?: string } = {}) {
    return apiRequest<DailySummaryReport[]>(
      `/api/daily-summaries${buildQuery(query)}`,
    );
  },
  update(summaryId: string, payload: { content: string; expectedUpdatedAt?: string }) {
    return apiRequest<DailySummaryReport>(
      `/api/daily-summaries/${encodeURIComponent(summaryId)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },
};
