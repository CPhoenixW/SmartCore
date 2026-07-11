export interface CurrentUser {
  userId?: string;
  displayName: string;
  language: "zh" | "en";
  avatarUrl?: string | null;
  reminderChannel: "screen" | "feishu";
}
