import { apiRequest } from "./client";

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export interface PushPublicKeyResult {
  enabled: boolean;
  publicKey: string | null;
}

export interface NotificationRecord {
  notifyId: string;
  evtId?: string | null;
  channel: string;
  title: string;
  content: string;
  scheduledAt: string;
  sentAt?: string | null;
  stat: string;
  deliveryState?: string | null;
  deliveryDetail?: string | null;
  failReason?: string | null;
}

export const notificationsApi = {
  list: (limit = 8) => apiRequest<NotificationRecord[]>(`/api/notifications?limit=${Math.max(1, Math.min(limit, 100))}`),
  publicKey: () => apiRequest<PushPublicKeyResult>("/api/notifications/push/public-key"),
  subscribe: (payload: PushSubscriptionPayload) => apiRequest<{ subscribed: boolean }>("/api/notifications/push-subscription", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  unsubscribe: (payload: PushSubscriptionPayload) => apiRequest<{ subscribed: boolean }>("/api/notifications/push-subscription", {
    method: "DELETE",
    body: JSON.stringify(payload),
  }),
};

export function vapidKeyBytes(value: string): Uint8Array {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/") + padding;
  const raw = window.atob(base64);
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
}
