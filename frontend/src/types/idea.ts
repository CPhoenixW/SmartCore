export interface Idea {
  ideaId: string;
  title: string;
  description: string;
  handled: boolean;
  srcType?: string;
  attachments: IdeaAttachment[];
  revision: number;
  createdAt?: string;
}
export interface IdeaAttachment { attachmentId: string; fileName: string; mimeType: string; url: string; sizeBytes: number; createdAt?: string }
export interface IdeaUpload { uploadId: string; fileName: string; mimeType: string; sizeBytes: number }
export interface IdeaMediaJob {
  jobId: string;
  ideaId: string;
  uploadId: string;
  stat: "queued" | "processing" | "ocr_ready" | "ready" | "failed" | "consumed";
  summary?: string | null;
  errorMessage?: string | null;
  createdAt: string;
  updatedAt: string;
}
