import { apiRequest } from "./client";
import type { CurrentUser } from "@/types/user";

export interface AuthStatus {
  authenticated: boolean;
  needsSetup: boolean;
  defaultUserId: string;
  user: CurrentUser | null;
}

export interface BrowserSession {
  sessionId: string;
  actorUserId: string;
  activeUserId: string;
  userAgent: string | null;
  createdAt: string;
  lastSeenAt: string | null;
  expiresAt: string;
  current: boolean;
}

export const authApi = {
  status: () => apiRequest<AuthStatus>("/api/auth/status"),
  setup: (password: string, displayName?: string) => apiRequest<CurrentUser>("/api/auth/setup", {
    method: "POST",
    body: JSON.stringify({ password, displayName: displayName || null }),
  }),
  register: (loginName: string, password: string, displayName?: string) => apiRequest<CurrentUser>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ loginName, password, displayName: displayName || null }),
  }),
  login: (userId: string, password: string) => apiRequest<CurrentUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ userId, password }),
  }),
  logout: () => apiRequest<{ loggedOut: boolean }>("/api/auth/logout", { method: "POST" }),
  logoutAll: () => apiRequest<{ loggedOut: boolean; revokedSessions: number }>("/api/auth/logout-all", { method: "POST" }),
  sessions: () => apiRequest<BrowserSession[]>("/api/auth/sessions"),
  revokeSession: (sessionId: string) => apiRequest<{ sessionId: string; revoked: boolean }>(`/api/auth/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }),
  changePassword: (currentPassword: string, newPassword: string) => apiRequest<{ passwordChanged: boolean; revokedSessions: number }>("/api/auth/password", {
    method: "POST",
    body: JSON.stringify({ currentPassword, newPassword }),
  }),
  me: () => apiRequest<CurrentUser>("/api/auth/me"),
};
