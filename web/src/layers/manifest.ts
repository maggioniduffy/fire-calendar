// Client-side view of the layer contract in docs/architecture.md.
// The backend validates manifests with pydantic; this check guards the UI.

export type LayerKind = "events" | "points" | "grid" | "series" | "polygons";

export interface LayerManifest {
  id: string;
  title: string;
  kind: LayerKind;
  source: string;
  period: string;
  license: string;
  updated_at: string;
  experimental?: boolean;
  files: string[];
}

const kinds: readonly LayerKind[] = ["events", "points", "grid", "series", "polygons"];
const required = ["id", "title", "source", "period", "license", "updated_at"] as const;

export function parseManifest(value: unknown): LayerManifest {
  if (typeof value !== "object" || value === null) throw new Error("manifest: not an object");
  const m = value as Record<string, unknown>;
  for (const key of required) {
    if (typeof m[key] !== "string" || m[key] === "") throw new Error(`manifest: missing ${key}`);
  }
  if (!kinds.includes(m.kind as LayerKind)) throw new Error("manifest: bad kind");
  if (!Array.isArray(m.files) || !m.files.every((f) => typeof f === "string")) {
    throw new Error("manifest: bad files");
  }
  if (m.experimental !== undefined && typeof m.experimental !== "boolean") {
    throw new Error("manifest: bad experimental");
  }
  if (!/^\d{4}-\d{2}(-\d{2})?\/\d{4}-\d{2}(-\d{2})?$/.test(m.period as string)) {
    throw new Error("manifest: period must be start/end");
  }
  return m as unknown as LayerManifest;
}

/** "2000-11-01/2026-08-31" → ["2000-11-01", "2026-08-31"]. */
export function splitPeriod(period: string): [string, string] {
  const [start, end] = period.split("/");
  return [start, end];
}

export type Confidence = "l" | "n" | "h" | string;

export interface Hotspot {
  id: string;
  lon: number;
  lat: number;
  date: string;
  sensor: "MODIS" | "VIIRS";
  frp: number;
  /** VIIRS: l/n/h; MODIS: 0–100 as text. */
  confidence: Confidence;
}

export interface PointLayer {
  manifest: LayerManifest;
  points: Hotspot[];
}
