import { apiRequest, buildQuery } from "./client";

export interface AssistantMessageResult {
  sessionId: string;
  conversationId: string;
  response: string;
}

export interface AssistantConversationSummary {
  conversationId: string;
  title: string;
  stat: "active" | "archived";
  createdAt: string;
  updatedAt: string;
  lastMessageAt?: string | null;
}

export interface AssistantMessage {
  messageId: string;
  conversationId: string;
  role: "user" | "assistant";
  text: string;
  stat: "complete" | "failed" | "pending";
  createdAt: string;
}

export interface AssistantConversation extends AssistantConversationSummary {
  messages: AssistantMessage[];
}

export interface AssistantSearchResult {
  conversationId: string;
  title: string;
  messageId: string;
  role: "user" | "assistant";
  text: string;
  snippet: string;
  createdAt: string;
}

export interface AssistantImportMessage {
  role: "user" | "assistant";
  text: string;
  messageId?: string;
  clientMessageId?: string;
  createdAt?: string;
}

export type AssistantStreamEvent =
  | { type: "status"; phase: string; message?: string }
  | { type: "message"; text: string; mode?: string }
  | { type: "tool"; state: "start" | "done"; name?: string; message?: string }
  | { type: "done"; sessionId: string; conversationId?: string; response: string }
  | { type: "error"; message: string }
  | { type: "end" };

function localTimezone(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai"; } catch { return "Asia/Shanghai"; }
}

export const assistantApi = {
  async send(text: string, conversationId?: string, clientMessageId?: string): Promise<AssistantMessageResult> {
    return apiRequest<AssistantMessageResult>("/api/assistant/message", {
      method: "POST",
      body: JSON.stringify({ text, conversationId, sessionId: conversationId, clientMessageId }),
    });
  },
  async stream(
    text: string,
    conversationId: string | undefined,
    onEvent: (event: AssistantStreamEvent) => void,
    clientMessageId?: string,
  ): Promise<AssistantMessageResult> {
    const response = await fetch("/api/assistant/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ text, conversationId, sessionId: conversationId, clientMessageId, timezone: localTimezone() }),
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
            if (event.type === "done") result = { sessionId: event.sessionId, conversationId: event.conversationId || event.sessionId, response: event.response };
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
  list(query?: string, limit = 30): Promise<{ items: AssistantConversationSummary[] | AssistantSearchResult[]; query: string }> {
    return apiRequest<{ items: AssistantConversationSummary[] | AssistantSearchResult[]; query: string }>(`/api/assistant/conversations${buildQuery({ q: query, limit })}`);
  },
  read(conversationId: string): Promise<AssistantConversation> {
    return apiRequest<AssistantConversation>(`/api/assistant/conversations/${encodeURIComponent(conversationId)}`);
  },
  importHistory(conversationId: string, messages: AssistantImportMessage[]): Promise<AssistantConversationSummary & { imported: number }> {
    return apiRequest<AssistantConversationSummary & { imported: number }>(`/api/assistant/conversations/${encodeURIComponent(conversationId)}/import`, {
      method: "POST",
      body: JSON.stringify({ messages }),
    });
  },
  create(title?: string): Promise<AssistantConversationSummary> {
    return apiRequest<AssistantConversationSummary>("/api/assistant/conversations", {
      method: "POST",
      body: JSON.stringify(title ? { title } : {}),
    });
  },
  archive(conversationId: string): Promise<{ conversationId: string; stat: "archived" }> {
    return apiRequest<{ conversationId: string; stat: "archived" }>(`/api/assistant/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });
  },
};
