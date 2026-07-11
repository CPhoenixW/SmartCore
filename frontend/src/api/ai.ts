import { apiRequest } from "./client";

interface ParseResponse<T extends Record<string, unknown>> {
  status: string;
  scene: string;
  text: string;
  parsed: T;
  now: string;
  provider: string;
  model: string;
}

export const aiApi = {
  async parse<T extends Record<string, unknown>>(text: string, scene = "create_event"): Promise<T> {
    const result = await apiRequest<ParseResponse<T>>("/api/llm/parse", {
      method: "POST",
      body: JSON.stringify({ text, scene, now: new Date().toISOString() }),
    });
    return result.parsed;
  },
};
