export interface Idea {
  ideaId: string;
  content: string;
  handled: boolean;
  srcType?: string;
  mediaPath?: string | null;
  createdAt?: string;
  updatedAt?: string;
}
