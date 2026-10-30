import { apiRequest } from "./client";

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export interface PushPublicKeyResult {
  enabled: boolean;
  publicKey: string | null;
}

export const notificationsApi = {
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
