import { apiRequest } from "./client";

export interface FeishuPair {
  pairId: string;
  botId: string;
  botName: string;
  deviceName: string;
  deviceKind: "feishuBot";
  claimCode: string;
  stat: string;
  expiresAt: string;
  bindId?: string;
}

export interface UserFeishuBinding {
  bindId: string;
  botId: string;
  botName: string;
  chatType: string;
  chatHint: string;
  stat: string;
  isPrimary: boolean;
  createdAt: string;
  lastSeenAt?: string | null;
}

export const feishuPairApi = {
  start: () => apiRequest<FeishuPair>("/api/feishu/pair/start", { method: "POST" }),
  read: (pairId: string) => apiRequest<FeishuPair>(`/api/feishu/pair/${encodeURIComponent(pairId)}`),
  confirm: (pairId: string) => apiRequest<FeishuPair>(`/api/feishu/pair/${encodeURIComponent(pairId)}/confirm`, { method: "POST" }),
  bindings: () => apiRequest<UserFeishuBinding[]>("/api/feishu/bindings"),
  removeBinding: (bindId: string) => apiRequest<{ bindId: string; deleted: boolean }>(`/api/feishu/bindings/${encodeURIComponent(bindId)}`, { method: "DELETE" }),
};
