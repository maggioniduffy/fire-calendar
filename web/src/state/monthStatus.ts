import type { Messages } from "../i18n";
import type { MonthStatus } from "../api/types";

/** Flags of a month that the UI marks; `drift` already accounts for the scale it is shown in. */
export interface StatusView {
  provisional: boolean;
  /** Source level(s) in plain words, "" when the payload carries none. */
  sourceText: string;
  drift: boolean;
}

/** Scales in which MODIS counts are part of the figure: only there the orbit-drift note applies. */
export const modisScale = (scale: string): boolean => scale === "modis_eq" || scale === "reported";

/** "api-sp+nrt" -> "procesamiento estándar (API de FIRMS) + tiempo casi real (NRT)". Unknown codes are kept as they are. */
export function sourceLevelText(status: MonthStatus, t: Messages): string {
  const levels = t.status.levels as Record<string, string>;
  const raw = status.source_levels || status.source_level || "";
  return raw
    .split("+")
    .filter(Boolean)
    .map((l) => levels[l] ?? l)
    .join(" + ");
}

export function statusView(status: MonthStatus | null | undefined, scale: string, t: Messages): StatusView {
  if (!status) return { provisional: false, sourceText: "", drift: false };
  return {
    provisional: status.provisional === true,
    sourceText: sourceLevelText(status, t),
    drift: status.modis_drift === true && modisScale(scale),
  };
}
