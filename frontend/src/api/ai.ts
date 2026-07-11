import { apiRequest } from "./client";
export const aiApi = {
  parse: (text: string, scene = "create_event") => apiRequest<Record<string, unknown>>("/api/llm/parse", {
    method: "POST",
    body: JSON.stringify({ text, scene, now: new Date().toISOString() }),
  }),
};
