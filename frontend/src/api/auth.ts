import { apiRequest } from "./client";
import type { CurrentUser } from "@/types/user";

export interface AuthStatus {
  authenticated: boolean;
  needsSetup: boolean;
  defaultUserId: string;
  user: CurrentUser | null;
}

export const authApi = {
  status: () => apiRequest<AuthStatus>("/api/auth/status"),
  setup: (password: string, displayName?: string) => apiRequest<CurrentUser>("/api/auth/setup", {
    method: "POST",
    body: JSON.stringify({ password, displayName: displayName || null }),
  }),
  login: (userId: string, password: string) => apiRequest<CurrentUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ userId, password }),
  }),
  logout: () => apiRequest<{ loggedOut: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => apiRequest<CurrentUser>("/api/auth/me"),
};
