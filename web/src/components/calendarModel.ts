import type { CalendarPayload, EqStatus, StatsPayload } from "../api/types";
import { anomalyRatio } from "../charts/scales";

export interface CalendarCell {
  /** "YYYY-MM" */
  ym: string;
  year: number;
  month: number;
  /** Count in the payload's scale; null = no data (month absent from the payload or value null). */
  value: number | null;
  /** "estimated" when the payload says this month's equivalent is modelled, not observed. */
  status: EqStatus | "none";
  /** Climatology median of this calendar month (stats), null when unavailable. */
  median: number | null;
  /** Signed relative departure from the median; null when it cannot be computed. */
  ratio: number | null;
}

export interface CalendarGrid {
  years: number[];
  cells: Map<string, CalendarCell>;
  /** Largest count shown (sequential ramp maximum); 0 when there is no data. */
  max: number;
  /** Latest month with data, "YYYY-MM", or null. */
  latest: string | null;
}

export const ymKey = (year: number, month: number) => `${year}-${String(month).padStart(2, "0")}`;

/** Year × month grid from `/calendar` months (count) and `/stats` climatology (anomaly), for the payload's scale. */
export function buildGrid(calendar: CalendarPayload, stats: StatsPayload): CalendarGrid {
  const col = calendar.scale === "modis_eq" ? "modis_eq" : "viirs_eq";
  const statusCol = col === "modis_eq" ? "modis_eq_status" : "viirs_eq_status";
  const medians = new Map(stats.climatology.months.map((m) => [m.month, m.median]));
  const cells = new Map<string, CalendarCell>();
  let max = 0;
  let latest: string | null = null;
  const years = new Set<number>();
  for (const row of calendar.months) {
    years.add(row.year);
    const raw = row[col];
    const value = typeof raw === "number" && Number.isFinite(raw) ? raw : null;
    const median = medians.get(row.month) ?? null;
    const ym = ymKey(row.year, row.month);
    cells.set(ym, {
      ym,
      year: row.year,
      month: row.month,
      value,
      status: value === null ? "none" : row[statusCol],
      median,
      ratio: anomalyRatio(value, median),
    });
    if (value !== null) {
      max = Math.max(max, value);
      if (latest === null || ym > latest) latest = ym;
    }
  }
  if (years.size === 0) return { years: [], cells, max, latest };
  const lo = Math.min(...years);
  const hi = Math.max(...years);
  return { years: Array.from({ length: hi - lo + 1 }, (_, i) => lo + i), cells, max, latest };
}

/** The cell for "YYYY-MM", or an empty "no data" cell when the payload has no such month. */
export function cellAt(grid: CalendarGrid, ym: string): CalendarCell {
  const known = grid.cells.get(ym);
  if (known) return known;
  const [y, m] = ym.split("-").map(Number);
  return { ym, year: y, month: m, value: null, status: "none", median: null, ratio: null };
}

/**
 * Neighbour of `ym` for a roving-focus key; null when it would leave the grid. The grid is drawn sideways (years
 * across, months down), so Left/Right step a year, Up/Down step a month (wrapping across years) and Home/End jump
 * to the first/last year of the same month row.
 */
export function neighbour(grid: CalendarGrid, ym: string, key: string): string | null {
  if (grid.years.length === 0) return null;
  const [y, m] = ym.split("-").map(Number);
  const first = grid.years[0];
  const last = grid.years[grid.years.length - 1];
  let year = y;
  let month = m;
  switch (key) {
    case "ArrowLeft":
      year -= 1;
      break;
    case "ArrowRight":
      year += 1;
      break;
    case "ArrowUp":
      month -= 1;
      break;
    case "ArrowDown":
      month += 1;
      break;
    case "Home":
      year = first;
      break;
    case "End":
      year = last;
      break;
    default:
      return null;
  }
  if (month < 1) {
    month = 12;
    year -= 1;
  } else if (month > 12) {
    month = 1;
    year += 1;
  }
  if (year < first || year > last) return null;
  return ymKey(year, month);
}
