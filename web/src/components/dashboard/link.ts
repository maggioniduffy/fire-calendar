import { createContext, useContext } from "react";

/**
 * What is under the pointer in any chart: a month (year + month), a calendar month in every year (year null,
 * seasonality) or a whole year (month null, yearly totals).
 */
export interface Hover {
  year: number | null;
  month: number | null;
}

/** Cross-chart state: hover highlights a month in every chart, a click selects it (selection.month). */
export interface MonthLink {
  hover: Hover | null;
  setHover: (h: Hover | null) => void;
  /** The month chosen in the selection state ("YYYY-MM" parsed). */
  selected: { year: number; month: number } | null;
  select: (key: string) => void;
}

export const LinkContext = createContext<MonthLink | null>(null);

export function useMonthLink(): MonthLink {
  const v = useContext(LinkContext);
  if (!v) throw new Error("useMonthLink needs a Dashboard");
  return v;
}

/** Path data for a polyline, broken wherever a point is null. */
export function linePaths(points: ({ x: number; y: number } | null)[]): string[] {
  const out: string[] = [];
  let cur = "";
  for (const p of points) {
    if (!p) {
      if (cur) out.push(cur);
      cur = "";
    } else cur += `${cur ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
  }
  if (cur) out.push(cur);
  return out;
}

/** Closed polygon between an upper and a lower edge (same x order). */
export function bandPath(upper: { x: number; y: number }[], lower: { x: number; y: number }[]): string {
  if (!upper.length) return "";
  const f = (p: { x: number; y: number }) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
  return `M${upper.map(f).join("L")}L${[...lower].reverse().map(f).join("L")}Z`;
}
