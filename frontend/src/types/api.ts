export interface ApiEnvelope<T> {
  ok: boolean;
  data: T;
  detail?: string;
}

export interface ApiErrorBody {
  ok?: boolean;
  detail?: string;
}
