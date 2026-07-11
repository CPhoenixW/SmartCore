export interface ApiEnvelope<T> {
  ok?: boolean;
  data: T;
  detail?: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | T | null;
  const envelope = body as ApiEnvelope<T> | null;

  if (!response.ok || envelope?.ok === false) {
    throw new ApiError(
      response.status,
      envelope?.detail ?? `HTTP ${response.status}`,
    );
  }

  if (envelope && typeof envelope === "object" && "data" in envelope) {
    return envelope.data;
  }

  return body as T;
}
