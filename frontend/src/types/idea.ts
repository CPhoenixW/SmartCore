export interface Idea {
  ideaId: string;
  title: string;
  description: string;
  handled: boolean;
  srcType?: string;
  attachments: IdeaAttachment[];
  createdAt?: string;
}
export interface IdeaAttachment { attachmentId: string; fileName: string; mimeType: string; url: string; sizeBytes: number; createdAt?: string }
export interface IdeaUpload { uploadId: string; fileName: string; mimeType: string; sizeBytes: number }
