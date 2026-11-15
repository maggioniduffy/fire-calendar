import { format } from "../i18n";
import type { Messages } from "../i18n";
import { regionInfo } from "../api/staticData";
import type { Area } from "./selection";

/** Display name of the chosen area (shown in the top bar). */
export function areaName(area: Area, t: Messages): string {
  if (area.kind === "preset") return t.area.nameCordoba;
  if (area.kind === "region") return regionInfo(area.id)?.name ?? area.id;
  if (area.kind === "polygon") return t.area.nameDrawn;
  if (area.source === "geolocation") return t.area.nameLocation;
  return format(t.area.nameCircle, { lat: area.lat.toFixed(2), lon: area.lon.toFixed(2), radius: area.radiusKm });
}
