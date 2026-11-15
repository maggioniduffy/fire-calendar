import type { RegionInfo } from "../api/staticClient";
import type { LonLat } from "./selection";

/** Spanish collation: "Ñ", accents and case sort as a reader expects. */
const collator = new Intl.Collator(["es-AR", "es"], { sensitivity: "base", numeric: true });
const byName = (a: RegionInfo, b: RegionInfo) => collator.compare(a.name, b.name);

export const provincesOf = (areas: readonly RegionInfo[]): RegionInfo[] => areas.filter((a) => a.kind === "province").sort(byName);

export const departmentsOf = (areas: readonly RegionInfo[], provinceId: string): RegionInfo[] =>
  areas.filter((a) => a.kind === "department" && a.province_id === provinceId).sort(byName);

/** Province of an area id (the area itself when it is a province); null when unknown. */
export function provinceIdOf(areas: readonly RegionInfo[], id: string): string | null {
  const a = areas.find((x) => x.id === id);
  if (!a) return null;
  return a.kind === "province" ? a.id : a.province_id;
}

/** Ray casting on one ring [lon, lat] (closed or not). */
function inRing(ring: readonly (readonly number[])[], lon: number, lat: number): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Whether the point is inside any exterior ring of an outline. */
export const pointInOutline = (outline: readonly (readonly number[])[][], lon: number, lat: number): boolean =>
  outline.some((ring) => inRing(ring, lon, lat));

/**
 * Province containing the point: bbox pre-filter on `areas`, then point-in-polygon on the outlines (fetched lazily by
 * `outlineOf`). Null outside every province. Nothing leaves the browser: the outlines come to the point.
 */
export async function provinceAtPoint(
  areas: readonly RegionInfo[],
  lat: number,
  lon: number,
  outlineOf: (id: string) => Promise<LonLat[][] | number[][][]>,
): Promise<string | null> {
  const candidates = areas.filter((a) => a.kind === "province" && lat >= a.bbox[0] && lat <= a.bbox[1] && lon >= a.bbox[2] && lon <= a.bbox[3]);
  for (const c of candidates) if (pointInOutline(await outlineOf(c.id), lon, lat)) return c.id;
  return null;
}
