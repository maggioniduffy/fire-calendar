// Static data mode (SA7.2): the same calls as client.ts answered from precomputed JSON under `VITE_DATA_URL`.
// Layout and payloads: plan/07-submission.md, "SA7.2 contract (v1)".
import { ApiError } from "./errors";
import type {
  AnomalyPayload,
  ApiScale,
  BBox,
  CalendarPayload,
  CalendarRequest,
  CellsPayload,
  CellsRequest,
  DetectionsPayload,
  ExportRequest,
  KeyFigures,
  MapCell,
  StatsPayload,
  StatsRequest,
} from "./types";

export interface Manifest {
  version: number;
  generated_at: string;
  layer: string;
  calibration_version: string | null;
  period: { start: string; end: string };
  scales: string[];
  default_area: string;
  boundaries: { source: string; license: string; attribution: string; url: string; sha256: string };
  skipped: { name: string; reason: string }[];
  detections?: { available: boolean; fields: string[]; tile_deg: number; months: number; source: string; note: string };
}

export interface RegionInfo {
  id: string;
  kind: "province" | "department";
  name: string;
  province_id: string | null;
  bbox: BBox;
  area_km2: number;
  n_cells: number;
}

/** `areas/{id}.json`: outline rings [lon, lat] and the [cell_lat, cell_lon] of the cells inside. */
export interface RegionDetail {
  id: string;
  name: string;
  kind: "province" | "department";
  outline: number[][][];
  cells: [number, number][];
}

interface StatsFile {
  meta: StatsPayload["meta"];
  area: StatsPayload["area"];
  n_cells: number;
  period: StatsPayload["period"];
  scale: ApiScale;
  default_ref: string;
  climatology_by_year: Record<string, StatsPayload["climatology"]>;
  by_ref: Record<string, { anomaly: Omit<AnomalyPayload, "ref_label_es" | "ref_label_en">; key_figures: KeyFigures }>;
}

interface CellsFile {
  month: string;
  scale: ApiScale;
  cells: [number, number, number, number | boolean][];
}
type DetectionRow = [number, number, string, string, string, number | null, string | null, number | null];
interface DetectionIndex { month: string; tiles: Record<string, number> }
const MAX_DETECTIONS = 5000; // backend/src/firecal/stages/calendar/cells.py
const rint = (value: number) => {
  const lower = Math.floor(value);
  const fraction = value - lower;
  return fraction < 0.5 ? lower : fraction > 0.5 ? lower + 1 : lower % 2 === 0 ? lower : lower + 1;
};
const cellCenter = (coordinate: number, origin: number) =>
  Math.floor((rint(coordinate * 1000) - origin * 1000) / 100) / 10 + origin + 0.05;

// Labels of backend/src/firecal/stages/calendar/service.py (REF_LABEL_*), shown by the inspector.
const REF_LABEL_ES = "último mes disponible (retrospectivo)";
const REF_LABEL_EN = "latest available month (retrospective)";
const REF_LABEL_CHOSEN_ES = "mes de referencia elegido (retrospectivo)";
const REF_LABEL_CHOSEN_EN = "chosen reference month (retrospective)";
/** [lat_min, lat_max, lon_min, lon_max] of the data domain (ARG_BBOX in selection.ts). */
const ARG: BBox = [-56, -21, -74, -53];

const cellKey = (lat: number, lon: number) => `${lat.toFixed(2)},${lon.toFixed(2)}`;

async function mapBounded<T, U>(items: T[], limit: number, fn: (item: T) => Promise<U>): Promise<U[]> {
  const out = new Array<U>(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) { const i = next++; out[i] = await fn(items[i]); }
  }));
  return out;
}

function selectMonths(req: CellsRequest, calendar: CalendarPayload): string[] {
  const available = calendar.months.map((r) => `${r.year}-${String(r.month).padStart(2, "0")}`);
  if (req.month) {
    if (!available.includes(req.month)) throw new ApiError(422, "requested month is outside the layer period");
    return [req.month];
  }
  const selected = req.start && req.end
    ? available.filter((ym) => ym >= req.start! && ym <= req.end!)
    : available.filter((ym) => {
        const [y, m] = ym.split("-").map(Number);
        return y >= req.years![0] && y <= req.years![1] && req.months!.includes(m);
      });
  if (!selected.length) throw new ApiError(422, "requested period is outside the layer period");
  return selected;
}

/** The view window clipped to the area bbox and the data domain; null when they do not overlap (cells.py `_window`). */
export function clipWindow(view: BBox, area: BBox): BBox | null {
  const w: BBox = [
    Math.max(view[0], area[0], ARG[0]),
    Math.min(view[1], area[1], ARG[1]),
    Math.max(view[2], area[2], ARG[2]),
    Math.min(view[3], area[3], ARG[3]),
  ];
  return w[0] > w[1] || w[2] > w[3] ? null : w;
}

/** Rebuilds the `/stats` answer for `ref` (default: the latest month, labels "unchosen") from the export file. */
export function buildStats(file: StatsFile, ref: string | undefined): StatsPayload {
  const chosen = ref !== undefined;
  const key = ref ?? file.default_ref;
  const entry = file.by_ref[key];
  const climatology = file.climatology_by_year[key.slice(0, 4)];
  if (!entry || !climatology) throw new ApiError(404, `no statistics for reference month ${key}`);
  return {
    meta: file.meta,
    area: file.area,
    n_cells: file.n_cells,
    period: file.period,
    scale: file.scale,
    climatology,
    anomaly: {
      ...entry.anomaly,
      ref_label_es: chosen ? REF_LABEL_CHOSEN_ES : REF_LABEL_ES,
      ref_label_en: chosen ? REF_LABEL_CHOSEN_EN : REF_LABEL_EN,
    },
    key_figures: entry.key_figures,
  };
}

/** Cells of the area inside the (clipped) window, sorted by lat then lon; `total` is the area's month value. */
export function buildCells(
  national: CellsFile | null,
  calendar: CalendarPayload,
  region: RegionDetail,
  info: RegionInfo,
  req: CellsRequest,
): CellsPayload {
  const scale = calendar.scale;
  const monthKeyValue = req.month!;
  const [year, month] = monthKeyValue.split("-").map(Number);
  const row = calendar.months.find((m) => m.year === year && m.month === month);
  const win = req.bbox ? clipWindow(req.bbox, info.bbox) : null;
  const inside = new Set(region.cells.map(([la, lo]) => cellKey(la, lo)));
  const cells: MapCell[] = [];
  for (const [lat, lon, value, est] of national?.cells ?? []) {
    if (!(value > 0) || !inside.has(cellKey(lat, lon))) continue;
    if (req.bbox && (!win || lat < win[0] || lat > win[1] || lon < win[2] || lon > win[3])) continue;
    cells.push({ cell_lat: lat, cell_lon: lon, value, estimated: Boolean(est) });
  }
  cells.sort((a, b) => a.cell_lat - b.cell_lat || a.cell_lon - b.cell_lon);
  return {
    meta: calendar.meta,
    area: calendar.area,
    outline: region.outline,
    period: { start: monthKeyValue, end: monthKeyValue },
    month: monthKeyValue,
    scale,
    bbox: win,
    cells,
    total: row ? row[scale] : null,
  };
}

export interface StaticClient {
  manifest(signal?: AbortSignal): Promise<Manifest>;
  areas(signal?: AbortSignal): Promise<RegionInfo[]>;
  region(id: string, signal?: AbortSignal): Promise<RegionDetail>;
  postCalendar(req: CalendarRequest, signal?: AbortSignal): Promise<CalendarPayload>;
  postStats(req: StatsRequest, signal?: AbortSignal): Promise<StatsPayload>;
  postExport(req: ExportRequest, signal?: AbortSignal): Promise<Response>;
  getCells(req: CellsRequest, signal?: AbortSignal): Promise<CellsPayload>;
  getDetections(req: CellsRequest & { bbox: BBox }, signal?: AbortSignal): Promise<DetectionsPayload>;
}

/** `base`: data root URL (no trailing slash needed). `fetchFn` is injectable for tests. */
export function createStaticClient(base: string, fetchFn: typeof fetch = (...a) => fetch(...a)): StaticClient {
  const root = base.replace(/\/+$/, "");
  const cache = new Map<string, Promise<unknown>>();

  const raw = async (path: string, signal?: AbortSignal): Promise<Response> => {
    const res = await fetchFn(`${root}/${path}`, { signal });
    if (!res.ok) throw new ApiError(res.status, `${path}`);
    return res;
  };
  /** JSON by URL, cached in memory; failures are not cached. */
  const json = <T>(path: string, signal?: AbortSignal): Promise<T> => {
    let p = cache.get(path) as Promise<T> | undefined;
    if (!p) {
      // The shared request is not tied to one caller's signal (a cancelled caller must not poison the cache).
      p = raw(path).then((r) => r.json() as Promise<T>);
      p.catch(() => cache.delete(path));
      cache.set(path, p);
    }
    return signal
      ? Promise.race([
          p,
          new Promise<never>((_, rej) => {
            if (signal.aborted) rej(signal.reason);
            signal.addEventListener("abort", () => rej(signal.reason), { once: true });
          }),
        ])
      : p;
  };

  const regionId = (req: CalendarRequest): string => {
    if (!req.region) throw new ApiError(400, "static data answers the provinces and departments only");
    return req.region;
  };
  const scaleOf = (req: CalendarRequest): ApiScale => req.scale ?? "viirs_eq";
  const info = async (id: string, signal?: AbortSignal) => {
    const found = (await json<{ areas: RegionInfo[] }>("areas.json", signal)).areas.find((a) => a.id === id);
    if (!found) throw new ApiError(404, `unknown area ${id}`);
    return found;
  };

  return {
    manifest: (signal) => json<Manifest>("manifest.json", signal),
    areas: async (signal) => (await json<{ areas: RegionInfo[] }>("areas.json", signal)).areas,
    region: (id, signal) => json<RegionDetail>(`areas/${id}.json`, signal),
    postCalendar: async (req, signal) => json<CalendarPayload>(`calendar/${regionId(req)}/${scaleOf(req)}.json`, signal),
    async postStats(req, signal) {
      const file = await json<StatsFile>(`stats/${regionId(req)}/${scaleOf(req)}.json`, signal);
      return buildStats(file, req.ref);
    },
    async postExport(req, signal) {
      if ((req.kind ?? "calendar") !== "calendar") throw new ApiError(404, "only the calendar CSV is published");
      const id = regionId(req);
      const scale = scaleOf(req);
      const res = await raw(`export/${id}/${scale}.csv`, signal);
      const headers = new Headers({
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="firecal_calendar_${id}_${scale}.csv"`,
      });
      return new Response(await res.blob(), { status: 200, headers });
    },
    async getCells(req, signal) {
      const id = regionId(req);
      const scale = scaleOf(req);
      const [calendar, detail, meta] = await Promise.all([
        json<CalendarPayload>(`calendar/${id}/${scale}.json`, signal),
        json<RegionDetail>(`areas/${id}.json`, signal),
        info(id, signal),
      ]);
      if (req.month) {
        let national: CellsFile | null = null;
        try {
          national = await json<CellsFile>(`cells/${scale}/${req.month}.json`, signal);
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e;
          const [y, m] = req.month.split("-").map(Number);
          if (!calendar.months.some((r) => r.year === y && r.month === m)) throw e;
        }
        return buildCells(national, calendar, detail, meta, req);
      }
      const selected = selectMonths(req, calendar);
      const files = await mapBounded(selected, 6, async (ym) => {
        try { return await json<CellsFile>(`cells/${scale}/${ym}.json`, signal); }
        catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; }
      });
      const inside = new Set(detail.cells.map(([la, lo]) => cellKey(la, lo)));
      const win = req.bbox ? clipWindow(req.bbox, meta.bbox) : null;
      const sums = new Map<string, MapCell>();
      for (const file of files) for (const [lat, lon, value, est] of file?.cells ?? []) {
        const key = cellKey(lat, lon);
        if (!inside.has(key)) continue;
        const prior = sums.get(key) ?? { cell_lat: lat, cell_lon: lon, value: 0, estimated: false };
        prior.value += value; prior.estimated ||= Boolean(est); sums.set(key, prior);
      }
      const cells = [...sums.values()].filter((c) => c.value > 0 && (!req.bbox || (!!win && c.cell_lat >= win[0] && c.cell_lat <= win[1] && c.cell_lon >= win[2] && c.cell_lon <= win[3]))).sort((a,b) => a.cell_lat-b.cell_lat || a.cell_lon-b.cell_lon);
      const rows = selected.map((ym) => { const [y,m] = ym.split("-").map(Number); return calendar.months.find((r) => r.year === y && r.month === m); });
      const vals = rows.map((r) => r?.[scale] ?? null);
      const statusRows = rows.filter((r): r is NonNullable<typeof r> => !!r);
      const levels = [...new Set(statusRows.map((r) => r.source_level).filter((x): x is NonNullable<typeof x> => x != null))];
      const result: CellsPayload = {
        meta: calendar.meta, area: calendar.area, outline: detail.outline,
        period: { start: selected[0], end: selected[selected.length - 1] }, months: selected.length,
        selection: req.start ? { kind: "range", start: req.start, end: req.end! } : { kind: "season", months: req.months!, years: req.years! },
        scale, bbox: win, cells, total: vals.some((v) => v === null) ? null : vals.reduce<number>((a, v) => a + (v ?? 0), 0),
        provisional: statusRows.some((r) => Boolean(r.provisional)), source_level: levels.length === 1 ? levels[0] : levels.length ? "mixed" : null,
        modis_drift: statusRows.some((r) => Boolean(r.modis_drift)),
      };
      return result;
    },
    async getDetections(req, signal) {
      const manifest = await json<Manifest>("manifest.json", signal);
      if (!manifest.detections?.available) throw new ApiError(404, "raw detections are not published");
      const id = regionId(req);
      const scale = scaleOf(req);
      const [calendar, detail, area] = await Promise.all([
        json<CalendarPayload>(`calendar/${id}/${scale}.json`, signal),
        json<RegionDetail>(`areas/${id}.json`, signal), info(id, signal),
      ]);
      const months = selectMonths(req, calendar);
      const win = clipWindow(req.bbox, area.bbox);
      const tileDeg = manifest.detections.tile_deg || 1;
      const inArea = new Set(detail.cells.map(([la, lo]) => cellKey(la, lo)));
      const rows: DetectionRow[] = [];
      if (win) {
        const indexes = await mapBounded(months, 6, async (ym) => {
          try { return await json<DetectionIndex>(`detections/${ym}/index.json`, signal); }
          catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; }
        });
        const jobs: Promise<DetectionRow[]>[] = [];
        indexes.forEach((index, mi) => {
          if (!index) return;
          for (const key of Object.keys(index.tiles)) {
            const [la, lo] = key.split("_").map(Number);
            if (la > win[1] || la + tileDeg < win[0] || lo > win[3] || lo + tileDeg < win[2]) continue;
            jobs.push(json<DetectionRow[]>(`detections/${months[mi]}/${key}.json`, signal));
          }
        });
        const batches = await mapBounded(jobs, 6, (p) => p);
        for (const batch of batches) for (const row of batch) {
          const [lat, lon, date] = row;
          const ym = date.slice(0, 7);
          if (!months.includes(ym) || lat < win[0] || lat > win[1] || lon < win[2] || lon > win[3]) continue;
          if (!inArea.has(cellKey(cellCenter(lat, -90), cellCenter(lon, -180)))) continue;
          rows.push(row);
        }
      }
      rows.sort((a,b) => a[2].localeCompare(b[2]) || a[3].localeCompare(b[3]) || a[4].localeCompare(b[4]) || a[0]-b[0] || a[1]-b[1]);
      const total = rows.length;
      const sampled = !req.month && total > MAX_DETECTIONS;
      const selectedRows = sampled
        ? Array.from({length: MAX_DETECTIONS}, (_, i) => rows[rint(i * (total - 1) / (MAX_DETECTIONS - 1))])
        : rows.slice(0, MAX_DETECTIONS);
      const points = selectedRows.map(([lat,lon,acq_date,,sensor,frp,daynight]) => ({lat,lon,acq_date,sensor,frp,daynight}));
      const isMonth = !!req.month;
      const period = isMonth ? { start: req.month!, end: req.month! } : { start: months[0], end: months[months.length-1] };
      return {
        meta: { ...calendar.meta, source: "NASA FIRMS (MODIS, VIIRS S-NPP, VIIRS NOAA-20)" },
        ...(isMonth ? { month: req.month } : { period, selection: req.start ? {kind:"range" as const,start:req.start,end:req.end!} : {kind:"season" as const,months:req.months!,years:req.years!} }),
        bbox: win, points, total, truncated: total > MAX_DETECTIONS, max_points: MAX_DETECTIONS,
        note: manifest.detections.note, ...(sampled ? { sampled: true } : {}),
      };
    },
  };
}
