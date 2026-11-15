// Pure helpers for the Dashboard tab (SA4.8): scales, aggregations and CSV. No React, no DOM.
import type { ApiScale, CalendarPayload, EqStatus, MonthRow, StatsPayload, YearRow } from "../api/types";

export type Domain = readonly [number, number];

/** Linear map from `domain` to `range` (a degenerate domain maps to the range start). */
export function linear(domain: Domain, range: Domain): (v: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  if (d1 === d0) return () => r0;
  return (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
}

/** "Nice" tick values covering [min, max] (about `count` of them): first <= min, last >= max. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!(max > min)) return [min];
  const raw = (max - min) / Math.max(count, 1);
  const pow = 10 ** Math.floor(Math.log10(raw));
  const f = raw / pow;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * pow;
  const out: number[] = [];
  let v = Math.floor(min / step) * step;
  for (;;) {
    out.push(Number(v.toPrecision(12)));
    if (v >= max - step * 1e-9) break;
    v += step;
  }
  return out;
}

/** Upper bound of an axis starting at 0, rounded up to a nice tick. */
export function niceMax(max: number): number {
  if (!(max > 0)) return 1;
  const t = niceTicks(0, max);
  return t[t.length - 1];
}

export const monthKey = (year: number, month: number): string => `${year}-${String(month).padStart(2, "0")}`;

export function parseMonthKey(key: string): { year: number; month: number } | null {
  const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(key);
  return m ? { year: Number(m[1]), month: Number(m[2]) } : null;
}

/** Column of the payload that carries the harmonized series for an API scale. */
export const eqColumn = (scale: ApiScale): "viirs_eq" | "modis_eq" => scale;

export interface MonthPoint {
  key: string;
  year: number;
  month: number;
  /** Position on the time axis: months since year 0. */
  index: number;
  value: number | null;
  status: EqStatus;
  modisReported: number | null;
  viirsReported: number | null;
  lo: number | null;
  hi: number | null;
}

/** Monthly rows of /calendar with the harmonized value (the payload's scale) and its band, in time order. */
export function monthlySeries(cal: CalendarPayload): MonthPoint[] {
  const col = eqColumn(cal.scale);
  const band = new Map<string, { lo: number | null; hi: number | null }>();
  for (const b of cal.band.month) if (b.month !== undefined) band.set(monthKey(b.year, b.month), b);
  return cal.months
    .map((m: MonthRow) => {
      const key = monthKey(m.year, m.month);
      const b = band.get(key);
      return {
        key,
        year: m.year,
        month: m.month,
        index: m.year * 12 + (m.month - 1),
        value: m[col],
        status: m[`${col}_status`],
        modisReported: m.modis_reported,
        viirsReported: m.viirs_reported,
        lo: b?.lo ?? null,
        hi: b?.hi ?? null,
      };
    })
    .sort((a, b) => a.index - b.index);
}

export interface YearPoint {
  year: number;
  value: number | null;
  nMonths: number;
  /** True when every month of the year has a value (partial years are drawn lighter). */
  complete: boolean;
  estimatedMonths: number;
}

export function yearlyTotals(cal: CalendarPayload): YearPoint[] {
  const col = eqColumn(cal.scale);
  return cal.years
    .map((y: YearRow) => ({
      year: y.year,
      value: y[col],
      nMonths: y[`${col}_n_months`],
      complete: y[`${col}_complete`],
      estimatedMonths: y[`${col}_estimated_months`],
    }))
    .sort((a, b) => a.year - b.year);
}

/** Sum of the non-null values (what the yearly totals and key_figures.total must add up to). */
export function sumValues(points: { value: number | null }[]): number {
  return points.reduce((s, p) => s + (p.value ?? 0), 0);
}

export interface SeasonPoint {
  month: number;
  median: number | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  nYears: number;
  /** Value of the latest year in the series for this calendar month (null = not observed). */
  latest: number | null;
}

/** Climatology per calendar month (median, p10, p25, p75, p90) plus the latest year. */
export function seasonality(cal: CalendarPayload, stats: StatsPayload): { latestYear: number | null; points: SeasonPoint[] } {
  const series = monthlySeries(cal);
  const latestYear = series.length ? Math.max(...series.map((p) => p.year)) : null;
  const byMonth = new Map(stats.climatology.months.map((c) => [c.month, c]));
  const points: SeasonPoint[] = [];
  for (let month = 1; month <= 12; month++) {
    const c = byMonth.get(month);
    points.push({
      month,
      median: c?.median ?? null,
      p10: c?.p10 ?? null,
      p25: c?.p25 ?? null,
      p75: c?.p75 ?? null,
      p90: c?.p90 ?? null,
      nYears: c?.n_years ?? 0,
      latest: series.find((p) => p.year === latestYear && p.month === month)?.value ?? null,
    });
  }
  return { latestYear, points };
}

export interface AnomalyPoint {
  key: string;
  year: number;
  month: number;
  index: number;
  value: number;
  median: number;
  /** value minus the median of the same calendar month. */
  diff: number;
}

/** Monthly value minus the climatological median of its calendar month; months without either are skipped. */
export function anomalies(cal: CalendarPayload, stats: StatsPayload): AnomalyPoint[] {
  if (stats.scale !== cal.scale) return [];
  const med = new Map(stats.climatology.months.map((c) => [c.month, c.median]));
  const out: AnomalyPoint[] = [];
  for (const p of monthlySeries(cal)) {
    const m = med.get(p.month);
    if (p.value === null || m === null || m === undefined) continue;
    out.push({ key: p.key, year: p.year, month: p.month, index: p.index, value: p.value, median: m, diff: p.value - m });
  }
  return out;
}

const csvCell = (v: unknown): string => {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
};

/** RFC 4180 CSV with a header row; null/undefined become empty cells. */
export function toCsv(header: readonly string[], rows: readonly (readonly unknown[])[]): string {
  return [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
