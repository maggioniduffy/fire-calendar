import type { CalendarPayload, MonthRow, StatsPayload, YM } from "../api/types";
import type { UiScale } from "./selection";

/** What the inspector shows for the chosen month, derived from the /calendar and /stats answers. */
export interface InspectorModel {
  /** Month the figures describe: the chosen one, else the latest available (`stats.anomaly.ref`). */
  ref: YM | null;
  /** Row of that month in `calendar.months`. */
  row: MonthRow | null;
  /** The month's value on the chosen harmonized scale is an estimate (not detected by that sensor). */
  estimated: boolean;
  /** Per-sensor reported counts (series "Reportado"); not harmonized and not summed. */
  reported: { modis: number | null; viirs: number | null } | null;
  /** Median, anomaly and most active month exist only for the harmonized scales. */
  harmonized: boolean;
}

export function buildInspectorModel(calendar: CalendarPayload, stats: StatsPayload, scale: UiScale): InspectorModel {
  const ref = stats.anomaly.ref;
  const row = ref ? (calendar.months.find((m) => m.year === ref.year && m.month === ref.month) ?? null) : null;
  const harmonized = scale !== "reported";
  const estimated = harmonized && row !== null && row[`${scale}_status`] === "estimated";
  const reported = harmonized ? null : { modis: row?.modis_reported ?? null, viirs: row?.viirs_reported ?? null };
  return { ref, row, estimated, reported, harmonized };
}

/** True when the area has per-sensor reported counts at all (otherwise the "Reportado" option is disabled). */
export function hasReported(calendar: CalendarPayload): boolean {
  return calendar.months.some((m) => m.modis_reported !== null || m.viirs_reported !== null);
}

export const NO_VALUE = "—";

export function formatCount(value: number | null | undefined, lang: string): string {
  if (value === null || value === undefined) return NO_VALUE;
  return new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(value);
}

/** "+13 %" from a ratio (0.1296); signed. */
export function formatPercent(ratio: number | null | undefined, lang: string): string {
  if (ratio === null || ratio === undefined) return NO_VALUE;
  return new Intl.NumberFormat(lang, { style: "percent", maximumFractionDigits: 0, signDisplay: "exceptZero" }).format(ratio);
}

/** "septiembre de 2015" / "September 2015". */
export function formatMonth(ym: YM, lang: string): string {
  return new Intl.DateTimeFormat(lang, { month: "long", year: "numeric", timeZone: "UTC" }).format(Date.UTC(ym.year, ym.month - 1, 1));
}

/** "2005-01-01/2016-12-31" -> "2005-01-01 – 2016-12-31". */
export function formatPeriod(period: string): string {
  return period.split("/").join(" – ");
}
