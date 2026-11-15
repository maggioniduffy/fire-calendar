// Mirrors backend/src/firecal/stages/calendar/{service,stats,area,matrix}.py (SA3.x). Numbers the backend cannot
// compute are `null` (NaN/inf are mapped to null by `clean`).

/** Scales the API accepts. "reported" is not an API scale; see state/selection.ts. */
export type ApiScale = "viirs_eq" | "modis_eq";

export interface CircleArea {
  type: "circle";
  lat: number;
  lon: number;
  radius_km: number;
}
export interface PolygonArea {
  type: "polygon";
  /** GeoJSON Polygon geometry, ring closed, [lon, lat]. */
  geojson: { type: "Polygon"; coordinates: number[][][] };
}
export type AreaSpec = CircleArea | PolygonArea;

/** Body of POST /calendar and /stats: exactly one of `area` or `preset`. */
export interface CalendarRequest {
  area?: AreaSpec;
  preset?: string;
  /** "YYYY-MM" */
  start?: string;
  end?: string;
  scale?: ApiScale;
}
export interface StatsRequest extends CalendarRequest {
  /** Reference month "YYYY-MM". */
  ref?: string;
  /** Baseline years [y0, y1]. */
  baseline?: [number, number];
}
/** Body of POST /export.csv. `detections` answers 404 when the server has no raw detections. */
export interface ExportRequest extends CalendarRequest {
  kind?: "calendar" | "cells" | "detections";
}

export interface Meta {
  layer: string;
  source: string;
  /** "YYYY-MM-DD/YYYY-MM-DD" */
  period: string;
  method: string | null;
  calibration_version: string | null;
  notes: { es: string[]; en: string[] };
  retrospective: true;
  alert_system: false;
  estimated_note_es: string;
  estimated_note_en: string;
}

/** `describe()` in area.py. */
export type AreaInfo =
  | { type: "circle"; lat: number; lon: number; radius_km: number; area_km2: number; bbox: BBox }
  | { type: "polygon"; n_polygons: number; n_vertices: number; area_km2: number; bbox: BBox };
/** [lat_min, lat_max, lon_min, lon_max] */
export type BBox = [number, number, number, number];

export type EqStatus = "observed" | "estimated" | "none";

export interface MonthRow {
  year: number;
  month: number;
  modis_reported: number | null;
  viirs_reported: number | null;
  modis_eq: number | null;
  viirs_eq: number | null;
  /** Cells with any detection in the month. */
  cells: number;
  modis_eq_status: EqStatus;
  viirs_eq_status: EqStatus;
}

export interface YearRow {
  year: number;
  n_months: number;
  modis_reported: number | null;
  viirs_reported: number | null;
  modis_eq: number | null;
  viirs_eq: number | null;
  modis_reported_n_months: number;
  viirs_reported_n_months: number;
  modis_eq_n_months: number;
  viirs_eq_n_months: number;
  modis_reported_complete: boolean;
  viirs_reported_complete: boolean;
  modis_eq_complete: boolean;
  viirs_eq_complete: boolean;
  modis_eq_estimated_months: number;
  viirs_eq_estimated_months: number;
}

export interface BandRow {
  year: number;
  month?: number;
  estimate: number | null;
  lo: number | null;
  hi: number | null;
  nominal: number | null;
  band_method: string;
  verified: boolean;
}

export interface CalendarPayload {
  meta: Meta;
  area: AreaInfo;
  n_cells: number;
  period: { start: string; end: string };
  scale: ApiScale;
  months: MonthRow[];
  years: YearRow[];
  band: {
    month: BandRow[];
    year: BandRow[];
    target: ApiScale;
    band_method: string;
    /** Always false for arbitrary areas ("sin verificar"). */
    verified: boolean;
    note_es: string;
    note_en: string;
  };
}

export interface YM {
  year: number;
  month: number;
}

/** Anomaly of the reference month (climatology.anomaly + labels added by stats_payload). */
export interface AnomalyPayload {
  ref: YM | null;
  value: number | null;
  median: number | null;
  p10: number | null;
  p90: number | null;
  abs_anomaly: number | null;
  pct_anomaly: number | null;
  /** 0-100 */
  percentile: number | null;
  n: number;
  ref_label_es: string;
  ref_label_en: string;
}

/** `key_figures` in stats.py; `current_vs_median` is the anomaly without the labels. */
export interface KeyFigures {
  column: string;
  most_active_month: (YM & { value: number | null }) | null;
  most_active_year: { year: number; value: number | null } | null;
  partial_year_exceeds: { year: number; value: number | null } | null;
  total: number | null;
  peak_calendar_month: { month: number; median: number | null } | null;
  current_vs_median: Omit<AnomalyPayload, "ref_label_es" | "ref_label_en"> | null;
  period_covered: { first: YM; last: YM } | null;
  estimated_months: number;
  includes_estimated: boolean;
}

export interface StatsPayload {
  meta: Meta;
  area: AreaInfo;
  n_cells: number;
  period: { start: string; end: string };
  scale: ApiScale;
  climatology: {
    months: { month: number; n_years: number; median: number | null; p10: number | null; p90: number | null }[];
    baseline_years: number[];
    quantile_method: string;
  };
  anomaly: AnomalyPayload;
  key_figures: KeyFigures;
}
