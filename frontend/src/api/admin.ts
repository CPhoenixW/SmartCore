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
  switchUser: (userId: string) => apiRequest<{ activeUser: AdminUser }>("/api/admin/activeUser", { method: "POST", body: JSON.stringify({ userId }) }),
};
