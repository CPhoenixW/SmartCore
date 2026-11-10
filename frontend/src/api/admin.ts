import { apiRequest } from "./client";

export interface AdminUser {
  userId: string;
  loginName?: string | null;
  displayName: string;
  role: "admin" | "user";
  stat: string;
}

export const adminApi = {
  users: () => apiRequest<AdminUser[]>("/api/admin/users"),
  async switchUser(userId: string) {
    const result = await apiRequest<{ activeUser: AdminUser }>("/api/admin/activeUser", { method: "POST", body: JSON.stringify({ userId }) });
    try { window.localStorage.removeItem("smartcore:assistant:primary:v2"); } catch {}
    return result;
  },
};
