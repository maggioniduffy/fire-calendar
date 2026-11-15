import type { ApiScale, CalendarRequest, StatsRequest } from "../api/types";

/** [lon, lat] */
export type LonLat = [number, number];

export type Area =
  | { kind: "preset"; id: "cordoba" }
  | { kind: "circle"; lat: number; lon: number; radiusKm: number; source: "manual" | "geolocation" }
  | { kind: "polygon"; vertices: LonLat[] };

/**
 * Series choice. The API (`CalendarRequest.scale`) only knows `viirs_eq` and `modis_eq`: "reported" (per-sensor
 * counts, SA4.5) is kept in state but requests `viirs_eq` for now, which already carries the reported columns.
 */
export type UiScale = "viirs_eq" | "modis_eq" | "reported";

/** Months "YYYY-MM"; both optional (the backend clips to the layer period). */
export interface Period {
  start?: string;
  end?: string;
}

export type AreaError = "invalid" | "radius" | "outside" | "vertices" | "size";

export interface DrawState {
  active: boolean;
  vertices: LonLat[];
  error: AreaError | null;
}

export interface SelectionState {
  area: Area;
  period: Period;
  scale: UiScale;
  /** Chosen month "YYYY-MM" (SA4.3+). */
  month: string | null;
  draw: DrawState;
}

// Limits copied from backend/src/firecal/stages/calendar/area.py.
export const MIN_RADIUS_KM = 5;
export const MAX_RADIUS_KM = 500;
export const MIN_AREA_KM2 = 100;
export const MAX_AREA_KM2 = 3_000_000;
export const DEFAULT_RADIUS_KM = 230;
/** [lat_min, lat_max, lon_min, lon_max] of the data domain. */
export const ARG_BBOX = [-56, -21, -74, -53] as const;
const KM_PER_DEG_LAT = 111.195;
const EARTH_RADIUS_KM = 6371.0088;

type Box = readonly [number, number, number, number];

function intersectsArg([latMin, latMax, lonMin, lonMax]: Box): boolean {
  const a = ARG_BBOX;
  return !(latMax < a[0] || latMin > a[1] || lonMax < a[2] || lonMin > a[3]);
}

function circleBox(lat: number, lon: number, radiusKm: number): Box {
  const dlat = radiusKm / KM_PER_DEG_LAT;
  const dlon = radiusKm / (KM_PER_DEG_LAT * Math.max(Math.cos((lat * Math.PI) / 180), 1e-6));
  return [Math.max(lat - dlat, -90), Math.min(lat + dlat, 90), Math.max(lon - dlon, -180), Math.min(lon + dlon, 180)];
}

/** Same rules as `CircleArea` in the backend; null when valid. */
export function validateCircle(lat: number, lon: number, radiusKm: number): AreaError | null {
  if (![lat, lon, radiusKm].every(Number.isFinite) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return "invalid";
  if (radiusKm < MIN_RADIUS_KM || radiusKm > MAX_RADIUS_KM) return "radius";
  return intersectsArg(circleBox(lat, lon, radiusKm)) ? null : "outside";
}

/** Cylindrical equal-area shoelace, as `_ring_area_km2` in the backend. Ring is not closed here. */
export function polygonAreaKm2(vertices: LonLat[]): number {
  let s = 0;
  for (let i = 0; i < vertices.length; i++) {
    const [lon1, lat1] = vertices[i];
    const [lon2, lat2] = vertices[(i + 1) % vertices.length];
    s += ((lon1 * Math.PI) / 180) * Math.sin((lat2 * Math.PI) / 180) - ((lon2 * Math.PI) / 180) * Math.sin((lat1 * Math.PI) / 180);
  }
  return (Math.abs(s) / 2) * EARTH_RADIUS_KM ** 2;
}

export function validatePolygon(vertices: LonLat[]): AreaError | null {
  if (vertices.length < 3) return "vertices";
  const lats = vertices.map((v) => v[1]);
  const lons = vertices.map((v) => v[0]);
  if (!intersectsArg([Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)])) return "outside";
  const km2 = polygonAreaKm2(vertices);
  return km2 < MIN_AREA_KM2 || km2 > MAX_AREA_KM2 ? "size" : null;
}

/** Parses a user-typed number ("-31,4" and "-31.4" both work); null when it is not one. */
export function parseNumber(text: string): number | null {
  const s = text.trim().replace(",", ".");
  if (s === "" || !/^[+-]?(\d+\.?\d*|\.\d+)$/.test(s)) return null;
  return Number(s);
}

const round = (v: number, digits: number) => Number(v.toFixed(digits));

export const emptyDraw: DrawState = { active: false, vertices: [], error: null };

export const initialSelection: SelectionState = {
  area: { kind: "preset", id: "cordoba" },
  period: {},
  scale: "viirs_eq",
  month: null,
  draw: emptyDraw,
};

export type SelectionAction =
  | { type: "setPreset" }
  | { type: "setCircle"; lat: number; lon: number; radiusKm: number; source: "manual" | "geolocation" }
  | { type: "drawStart" }
  | { type: "drawVertex"; vertex: LonLat }
  | { type: "drawFinish" }
  | { type: "drawCancel" }
  | { type: "setPeriod"; period: Period }
  | { type: "setScale"; scale: UiScale }
  | { type: "setMonth"; month: string | null };

export function selectionReducer(state: SelectionState, action: SelectionAction): SelectionState {
  switch (action.type) {
    case "setPreset":
      return { ...state, area: initialSelection.area, draw: emptyDraw };
    case "setCircle": {
      if (validateCircle(action.lat, action.lon, action.radiusKm)) return state;
      const digits = action.source === "geolocation" ? 2 : 4; // ~1 km: enough for a 230 km circle
      const { lat, lon, radiusKm, source } = action;
      return { ...state, area: { kind: "circle", lat: round(lat, digits), lon: round(lon, digits), radiusKm, source }, draw: emptyDraw };
    }
    case "drawStart":
      return { ...state, draw: { active: true, vertices: [], error: null } };
    case "drawVertex":
      if (!state.draw.active) return state;
      return {
        ...state,
        draw: { ...state.draw, error: null, vertices: [...state.draw.vertices, [round(action.vertex[0], 4), round(action.vertex[1], 4)]] },
      };
    case "drawFinish": {
      if (!state.draw.active) return state;
      const error = validatePolygon(state.draw.vertices);
      if (error) return { ...state, draw: { ...state.draw, error } };
      return { ...state, area: { kind: "polygon", vertices: state.draw.vertices }, draw: emptyDraw };
    }
    case "drawCancel":
      return { ...state, draw: emptyDraw };
    case "setPeriod":
      return { ...state, period: action.period };
    case "setScale":
      return { ...state, scale: action.scale };
    case "setMonth":
      return { ...state, month: action.month };
  }
}

/** The API scale for a UI scale ("reported" requests viirs_eq until SA4.5 decides otherwise). */
export function apiScale(scale: UiScale): ApiScale {
  return scale === "modis_eq" ? "modis_eq" : "viirs_eq";
}

/** Body shared by /calendar and /stats for the current selection. */
export function toRequest(state: SelectionState): CalendarRequest {
  const { area, period } = state;
  const base: CalendarRequest = { scale: apiScale(state.scale) };
  if (period.start) base.start = period.start;
  if (period.end) base.end = period.end;
  if (area.kind === "preset") return { ...base, preset: area.id };
  if (area.kind === "circle") {
    return { ...base, area: { type: "circle", lat: area.lat, lon: area.lon, radius_km: area.radiusKm } };
  }
  const ring = [...area.vertices, area.vertices[0]];
  return { ...base, area: { type: "polygon", geojson: { type: "Polygon", coordinates: [ring] } } };
}

export function toStatsRequest(state: SelectionState): StatsRequest {
  return toRequest(state); // `ref` stays unset until the chosen month drives the inspector (SA4.5)
}
