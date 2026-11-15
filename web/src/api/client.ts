import type {
  CalendarPayload,
  CalendarRequest,
  ExportRequest,
  StatsPayload,
  StatsRequest,
} from "./types";

/** Base URL of the data API. `/api` is proxied to the backend in dev (vite.config.ts) and mocked in e2e. */
export const BASE_URL: string = import.meta.env.VITE_DATA_URL ?? "/api";

/** The server answered with a non-2xx status. `detail` is FastAPI's message when present. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  constructor(status: number, detail: string | null) {
    super(`API ${status}${detail ? `: ${detail}` : ""}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function post(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let detail: string | null = null;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      // Body is not JSON.
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

export async function postCalendar(req: CalendarRequest, signal?: AbortSignal): Promise<CalendarPayload> {
  return (await post("/calendar", req, signal)).json() as Promise<CalendarPayload>;
}

export async function postStats(req: StatsRequest, signal?: AbortSignal): Promise<StatsPayload> {
  return (await post("/stats", req, signal)).json() as Promise<StatsPayload>;
}

/** CSV download; the caller reads the body and `Content-Disposition` (SA4.6). */
export function postExport(req: ExportRequest, signal?: AbortSignal): Promise<Response> {
  return post("/export.csv", req, signal);
}
