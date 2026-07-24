# Idea attachment editing design

Status: implemented; this document records the accepted contract and test scope.

## Scope and acceptance criteria

- The Idea edit form manages existing and newly uploaded attachments in one staged edit.
- Removing an existing attachment is reversible until Save. Cancel leaves the Idea unchanged.
- PDF/TXT/ZIP uploads become ready immediately. Image uploads must finish OCR and a concise
  summary before they can be attached.
- Save atomically applies title, description, handled state, attachment additions, and
  attachment removals. A partial database update is never returned as success.
- Every browser and Agent operation is scoped to the authenticated owner.
- A repeated OpenClaw tool call for the same media job never creates another paid OCR request.
- Existing Ideas and attachments remain readable throughout deployment.

## Pre-implementation gaps (resolved)

- `IdeaView.vue` hides the upload drop zone whenever an Idea is selected.
- The edit mutation sends only `title` and `description`.
- `PATCH /api/idea/{ideaId}` has no attachment delta contract.
- The current PATCH and DELETE handlers do not explicitly require the authenticated user.
- Browser media processing returns only `queued`; there is no durable job status to poll.
- Removing an attachment row does not define physical-file cleanup behavior.

## Data model

Keep `idea` and `ideaAttachment`. Add two non-destructive structures:

### `idea.revision`

- Integer, non-null, default `1`.
- Incremented by every successful edit.
- The client submits `expectedRevision`; stale edits receive HTTP 409.

### `ideaMediaJob`

| Field | Purpose |
| --- | --- |
| `jobId` | Primary key returned to the browser |
| `userId` | Owner boundary |
| `ideaId` | Optional edit target; null for a new Idea |
| `uploadId` | Unique active job per temporary upload |
| `stat` | `queued`, `processing`, `ready`, `failed`, `consumed` |
| `ocrText` | Bounded OCR result for server-side reuse |
| `summary` | Chinese Markdown summary, at most 100 characters |
| `errorMessage` | Safe user-facing failure reason |
| `createdAt`, `updatedAt`, `expiresAt` | Lifecycle and cleanup |

The OCR evidence remains server-side. The browser never receives or resubmits the evidence token.

## Web API

### Upload temporary files

`POST /api/idea/uploads` remains multipart and returns upload metadata.

### Process an image

`POST /api/idea/media-jobs`

```json
{
  "ideaId": "optional-existing-idea-id",
  "uploadId": "temporary-upload-id",
  "contextText": "current title and description"
}
```

Returns HTTP 202 with `{ "jobId": "...", "stat": "queued" }`. Documents do not use this
endpoint. Repeating the request returns the existing active job.

### Poll processing

`GET /api/idea/media-jobs/{jobId}` returns owner-scoped status, summary, and safe error text.
It never returns storage paths, OCR evidence, credentials, or raw provider responses.

### Atomic edit

`PATCH /api/idea/{ideaId}`

```json
{
  "expectedRevision": 3,
  "title": "Idea title",
  "description": "User-editable Markdown",
  "handled": false,
  "addUploadIds": ["ready-document-upload", "ready-image-upload"],
  "removeAttachmentIds": ["attachment-to-remove"]
}
```

Omitted attachment arrays mean no attachment change. The backend validates ownership, job state
for images, supported MIME types, unique IDs, and a maximum of ten final attachments. It then
updates metadata, transfers uploads to attachments, removes requested rows, increments revision,
and commits once.

The response is the complete updated Idea. HTTP 409 represents a stale revision or an image whose
media job is not ready. HTTP 404 does not reveal resources owned by another user.

## Agent API and OpenClaw contract

The media event includes `jobId`, `uploadId`, and optional `ideaId`. OpenClaw must:

1. Call `mediaImageOcr` exactly once for the job.
2. Produce one factual Chinese Markdown summary of at most 100 characters using OCR plus context.
3. Call `POST /agent/idea/media-job/complete` with the job ID, summary, and OCR evidence.
4. On OCR failure, call `POST /agent/idea/media-job/fail` once and stop.

The backend enforces this state machine. `mediaImageOcr` returns the cached result for a ready job,
returns `in_progress` while a call is active, and never starts a second provider request for the
same job. Skill wording is guidance; idempotency is a backend invariant.

## Frontend behavior

- The attachment manager is visible in both New and Edit modes.
- Existing images use thumbnails with enlarge/download actions. Documents use filename cards.
- A remove icon marks an existing attachment as `pending removal`; Undo restores it.
- New files show stable rows with `uploading`, `processing`, `ready`, or `failed` status.
- Failed image processing offers Retry and Remove. Save is disabled only while a selected image
  is uploading or processing.
- The generated image summary appears in an editable preview before Save. It is not silently
  mixed into the user's description.
- Cancel discards the staged delta. Temporary uploads/jobs expire and are cleaned server-side.
- After Save, the query cache is replaced with the returned Idea instead of relying on a fixed
  five-second refresh delay.

## Storage and deletion

- Database rows are committed before physical files are removed.
- After commit, removed files are unlinked with bounded, structured error logging.
- Startup and upload-path cleanup delete expired `ideaUpload` files and unreferenced media-job files.
- Deleting an entire Idea uses the same attachment cleanup path.
- Rollback never deletes an attachment still referenced by the database.

## Security and test matrix

- Test owner and non-owner access for Idea, attachment, upload, and media job IDs.
- Test add document, add image after OCR, remove, mixed add/remove, cancel, and maximum count.
- Test stale revision, missing upload, foreign attachment, failed OCR, duplicate job, and duplicate
  Agent completion.
- Test that four repeated OCR tool calls produce one upstream request.
- Test database rollback on any validation failure and best-effort file cleanup after commit.
- Test desktop/mobile edit layout, keyboard access, long filenames, image lightbox, and download.

## Migration, rollout, and rollback

- Add `idea.revision` with default `1` and create `ideaMediaJob`; no historical Idea data is
  rewritten or deleted.
- Deploy backend compatibility first, then the frontend and OpenClaw skill in the same verified
  release. Existing clients may continue sending metadata-only PATCH requests.
- Run a production smoke with a disposable Idea: add a document, process one image, remove one
  attachment, verify preview/download, then delete the disposable Idea.
- Rollback the application image normally. The additive column/table may remain without affecting
  the previous release.
