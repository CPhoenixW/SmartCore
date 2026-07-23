import { afterEach, describe, expect, it, vi } from "vitest";
import { ideaApi } from "@/api/idea";

afterEach(() => vi.restoreAllMocks());

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("idea attachment editing API", () => {
  it("sends an atomic attachment delta with the expected revision", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      ideaId: "idea-1",
      title: "Updated",
      description: "",
      handled: false,
      revision: 4,
      attachments: [],
    }));
    vi.stubGlobal("fetch", fetchMock);

    await ideaApi.update("idea-1", {
      expectedRevision: 3,
      title: "Updated",
      addUploadIds: ["upload-1"],
      removeAttachmentIds: ["attachment-1"],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/idea/idea-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          expectedRevision: 3,
          title: "Updated",
          addUploadIds: ["upload-1"],
          removeAttachmentIds: ["attachment-1"],
        }),
      }),
    );
  });

  it("creates and polls an image media job", async () => {
    const job = {
      jobId: "job-1",
      ideaId: "idea-1",
      uploadId: "upload-1",
      stat: "ready",
      summary: "图片摘要",
      createdAt: "now",
      updatedAt: "now",
    };
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(response(job, 202)));
    vi.stubGlobal("fetch", fetchMock);

    await ideaApi.createMediaJob({
      ideaId: "idea-1",
      uploadId: "upload-1",
      contextText: "context",
    });
    await ideaApi.getMediaJob("job-1");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.at(0)?.[0]).toBe("/api/idea/media-jobs");
    expect(fetchMock.mock.calls.at(1)?.[0]).toBe("/api/idea/media-jobs/job-1");
  });
});
