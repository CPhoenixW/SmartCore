export interface CurrentUser {
  userId?: string;
  role?: "admin" | "user";
  displayName: string;
  language: "zh" | "en";
  avatarUrl?: string | null;
  reminderChannel: "screen";
}
