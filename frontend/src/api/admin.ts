import { apiRequest } from "./client";

export interface AdminUser {
  userId: string;
  loginName?: string | null;
  displayName: string;
  role: "admin" | "user";
  stat: string;
}

export interface FeishuBot {
  botId: string;
  userId: string;
  deviceId?: string | null;
  botName: string;
  appIdHint: string;
  enabled: boolean;
  isDefault: boolean;
  hasRecipient: boolean;
  lastTestAt?: string | null;
  lastTestStat?: string | null;
  lastTestMessage?: string | null;
}

export interface FeishuBotInput {
  botName: string;
  appId: string;
  appSecret: string;
  verificationToken: string;
  encryptKey: string;
  defaultChatId?: string;
  isDefault?: boolean;
}

export interface FeishuBind { bindId: string; chatId: string; chatType: string; stat: string; isPrimary: boolean; createdAt: string; lastSeenAt?: string | null; }

export const adminApi = {
  users: () => apiRequest<AdminUser[]>("/api/admin/users"),
  switchUser: (userId: string) => apiRequest<{ activeUser: AdminUser }>("/api/admin/activeUser", { method: "POST", body: JSON.stringify({ userId }) }),
  feishuBots: () => apiRequest<FeishuBot[]>("/api/admin/feishuBots"),
  createFeishuBot: (data: FeishuBotInput) => apiRequest<FeishuBot>("/api/admin/feishuBots", { method: "POST", body: JSON.stringify(data) }),
  updateFeishuBot: (botId: string, data: Partial<FeishuBotInput>) => apiRequest<FeishuBot>(`/api/admin/feishuBots/${botId}`, { method: "PATCH", body: JSON.stringify(data) }),
  toggleFeishuBot: (botId: string) => apiRequest<FeishuBot>(`/api/admin/feishuBots/${botId}/toggle`, { method: "POST" }),
  deleteFeishuBot: (botId: string) => apiRequest<{ deleted: boolean }>(`/api/admin/feishuBots/${botId}`, { method: "DELETE" }),
  startFeishuPair: (botId: string) => apiRequest<{ pairId: string; claimCode: string; expiresAt: string; stat: string; botId: string }>(`/api/admin/feishuBots/${botId}/pair/start`, { method: "POST" }),
  confirmFeishuPair: (botId: string, pairId: string) => apiRequest<{ bindId: string; chatId: string; stat: string; isPrimary: boolean }>(`/api/admin/feishuBots/${botId}/pair/${pairId}/confirm`, { method: "POST" }),
  feishuBinds: (botId: string) => apiRequest<FeishuBind[]>(`/api/admin/feishuBots/${botId}/binds`),
  setPrimaryFeishuBind: (botId: string, bindId: string) => apiRequest<FeishuBind>(`/api/admin/feishuBots/${botId}/binds/${bindId}/primary`, { method: "POST" }),
  deleteFeishuBind: (botId: string, bindId: string) => apiRequest<{ deleted: boolean }>(`/api/admin/feishuBots/${botId}/binds/${bindId}`, { method: "DELETE" }),
  testFeishuBot: (botId: string) => apiRequest<FeishuBot>(`/api/admin/feishuBots/${botId}/test`, { method: "POST" }),
};
