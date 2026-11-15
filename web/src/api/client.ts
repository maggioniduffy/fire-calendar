import type {
  CalendarPayload,
  CalendarRequest,
  CellsPayload,
  CellsRequest,
  DetectionsPayload,
  ExportRequest,
  StatsPayload,
  StatsRequest,
} from "./types";
import { ApiError } from "./errors";
import { staticClient } from "./staticData";

/** Base URL of the data API. `/api` is proxied to the backend in dev (vite.config.ts) and mocked in e2e. */
export const BASE_URL = "/api";

/** Static data mode (SA7.2): precomputed JSON under `VITE_DATA_URL`, no API. */
export const STATIC_MODE = Boolean(import.meta.env.VITE_DATA_URL);

export { ApiError };

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
  if (STATIC_MODE) return staticClient.postCalendar(req, signal);
  return (await post("/calendar", req, signal)).json() as Promise<CalendarPayload>;
}

export async function postStats(req: StatsRequest, signal?: AbortSignal): Promise<StatsPayload> {
  if (STATIC_MODE) return staticClient.postStats(req, signal);
  return (await post("/stats", req, signal)).json() as Promise<StatsPayload>;
}

/** CSV download; the caller reads the body and `Content-Disposition` (SA4.6). */
export function postExport(req: ExportRequest, signal?: AbortSignal): Promise<Response> {
  if (STATIC_MODE) return staticClient.postExport(req, signal);
  return post("/export.csv", req, signal);
}

/** Cells (0.1 degree) with counts for one month inside the area and the view window. */
export async function getCells(req: CellsRequest, signal?: AbortSignal): Promise<CellsPayload> {
  if (STATIC_MODE) return staticClient.getCells(req, signal);
  return (await post("/cells", req, signal)).json() as Promise<CellsPayload>;
}

/** Raw detections for one month in the view window (`req.bbox` required); `ApiError` 404 when unavailable. */
export async function getDetections(
  req: CellsRequest & { bbox: NonNullable<CellsRequest["bbox"]> },
  signal?: AbortSignal,
): Promise<DetectionsPayload> {
  if (STATIC_MODE) return staticClient.getDetections(req, signal);
  return (await post("/detections", req, signal)).json() as Promise<DetectionsPayload>;
}
