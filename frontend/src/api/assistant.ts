import { apiRequest } from "./client";

export interface AssistantMessageResult {
  sessionId: string;
  response: string;
}

export type AssistantStreamEvent =
  | { type: "status"; phase: string; message?: string }
  | { type: "message"; text: string; mode?: string }
  | { type: "tool"; state: "start" | "done"; name?: string; message?: string }
  | { type: "done"; sessionId: string; response: string }
  | { type: "error"; message: string }
  | { type: "end" };

function localTimezone(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai"; } catch { return "Asia/Shanghai"; }
}

export const assistantApi = {
  async send(text: string, sessionId?: string): Promise<AssistantMessageResult> {
    return apiRequest<AssistantMessageResult>("/api/assistant/message", {
      method: "POST",
      body: JSON.stringify({ text, sessionId }),
    });
  },
  async stream(
    text: string,
    sessionId: string | undefined,
    onEvent: (event: AssistantStreamEvent) => void,
  ): Promise<AssistantMessageResult> {
    const response = await fetch("/api/assistant/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ text, sessionId, timezone: localTimezone() }),
      cache: "no-store",
    });
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(body?.detail || `HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: AssistantMessageResult | null = null;
    const consume = (chunk: string) => {
      buffer += chunk;
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame.split("\n").find((line) => line.startsWith("data:"));
        if (data) {
          try {
            const event = JSON.parse(data.slice(5).trim()) as AssistantStreamEvent;
            onEvent(event);
            if (event.type === "done") result = { sessionId: event.sessionId, response: event.response };
            if (event.type === "error") throw new Error(event.message);
          } catch (error) {
            if (error instanceof Error && error.message) throw error;
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    };
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      consume(decoder.decode(value, { stream: true }));
    }
    consume(decoder.decode());
    if (!result) throw new Error("助手没有返回结果");
    return result;
  },
};
