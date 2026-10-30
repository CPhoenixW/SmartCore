import { apiRequest } from "./client";

export interface AssistantMessageResult {
  sessionId: string;
  response: string;
}

export const assistantApi = {
  async send(text: string, sessionId?: string): Promise<AssistantMessageResult> {
    return apiRequest<AssistantMessageResult>("/api/assistant/message", {
      method: "POST",
      body: JSON.stringify({ text, sessionId }),
    });
  },
};
