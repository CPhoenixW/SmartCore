export type MemoryType = "profile" | "preference" | "habit" | "goal" | "relationship" | "fact";
export type MemorySource = "auto_extracted" | "user_explicit";

export interface MemoryItem {
  memoryId: string;
  type: MemoryType;
  typeLabel: string;
  content: string;
  source: MemorySource;
  confidence: number;
  createdAt: string;
  updatedAt: string;
  lastUsedAt: string | null;
  expiresAt: string | null;
}

export interface MemoryListResponse {
  enabled: boolean;
  items: MemoryItem[];
  types: { value: MemoryType; label: string }[];
}

export interface MemoryCreatePayload {
  content: string;
  type?: MemoryType;
}

export interface MemoryUpdatePayload {
  content?: string;
  type?: MemoryType;
}
