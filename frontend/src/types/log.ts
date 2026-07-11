export type LogRecord = Record<string, unknown>;
export interface LogsResponse {
  act: LogRecord[];
  notify: LogRecord[];
  msg: LogRecord[];
}
