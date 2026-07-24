import { afterEach, describe, expect, it, vi } from "vitest";
import { ideaApi } from "@/api/idea";
import {
  expectFetch,
  jsonResponse,
  mockJsonFetch,
  restoreHttpMocks,
} from "./helpers/http";

afterEach(restoreHttpMocks);

describe("idea attachment editing API", () => {
  it("sends an atomic attachment delta with the expected revision", async () => {
    const fetchMock = mockJsonFetch({
      ideaId: "idea-1",
      title: "Updated",
      description: "",
      handled: false,
      revision: 4,
      attachments: [],
    });

    await ideaApi.update("idea-1", {
      expectedRevision: 3,
      title: "Updated",
      addUploadIds: ["upload-1"],
      removeAttachmentIds: ["attachment-1"],
    });

    expectFetch(
      fetchMock,
      "/api/idea/idea-1",
      "PATCH",
      {
        body: JSON.stringify({
          expectedRevision: 3,
          title: "Updated",
          addUploadIds: ["upload-1"],
          removeAttachmentIds: ["attachment-1"],
        }),
      },
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
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(jsonResponse(job, 202)));
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
