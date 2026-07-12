import { apiRequest } from "./client";
import type { CurrentUser } from "@/types/user";

export const userApi = {
  me: () => apiRequest<CurrentUser>("/api/user/me"),
  update: (payload: Partial<CurrentUser>) => apiRequest<CurrentUser>("/api/user/me", { method: "PATCH", body: JSON.stringify(payload) }),
  uploadAvatar: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiRequest<Pick<CurrentUser, "avatarUrl">>("/api/user/avatar", { method: "POST", body });
  },
};
