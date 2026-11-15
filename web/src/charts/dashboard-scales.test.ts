import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { CalendarPayload, StatsPayload } from "../api/types";
import { anomalies, linear, monthKey, monthlySeries, niceMax, niceTicks, parseMonthKey, seasonality, sumValues, toCsv, yearlyTotals } from "./dashboard-scales";

const dir = join(__dirname, "../../e2e/fixtures/api");
const read = <T>(f: string) => JSON.parse(readFileSync(join(dir, f), "utf8")) as T;
const cal = read<CalendarPayload>("calendar-cordoba-viirs_eq.json");
const stats = read<StatsPayload>("stats-cordoba-viirs_eq.json");

describe("scales", () => {
  it("linear maps domain to range", () => {
    const f = linear([0, 10], [100, 200]);
    expect(f(0)).toBe(100);
    expect(f(5)).toBe(150);
    expect(linear([3, 3], [7, 9])(3)).toBe(7);
  });
  it("niceTicks and niceMax", () => {
    expect(niceTicks(0, 97, 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceMax(97)).toBe(100);
    expect(niceMax(0)).toBe(1);
  });
  it("month keys round trip", () => {
    expect(monthKey(2016, 3)).toBe("2016-03");
    expect(parseMonthKey("2016-03")).toEqual({ year: 2016, month: 3 });
    expect(parseMonthKey("2016-13")).toBeNull();
  });
});

describe("aggregations (synthetic Córdoba fixture)", () => {
  it("yearly totals equal the sum of the months, per year and overall", () => {
    const months = monthlySeries(cal);
    for (const y of yearlyTotals(cal)) {
      expect(y.value).toBeCloseTo(sumValues(months.filter((m) => m.year === y.year)), 6);
    }
    expect(sumValues(yearlyTotals(cal))).toBeCloseTo(sumValues(months), 6);
  });
  it("equals the stats key figure total", () => {
    expect(sumValues(monthlySeries(cal))).toBeCloseTo(stats.key_figures.total!, 6);
  });
  it("monthly series is sorted and carries the band", () => {
    const s = monthlySeries(cal);
    expect(s).toHaveLength(cal.months.length);
    expect(s.every((p, i) => i === 0 || p.index > s[i - 1].index)).toBe(true);
    expect(s[0].lo).not.toBeNull();
    expect(s[0].lo!).toBeLessThanOrEqual(s[0].value!);
  });
  it("seasonality has 12 months and the latest year", () => {
    const { latestYear, points } = seasonality(cal, stats);
    expect(latestYear).toBe(2016);
    expect(points).toHaveLength(12);
    expect(points[11].latest).toBe(stats.anomaly.value); // December 2016 is the reference month
    expect(points[8].median).toBe(stats.key_figures.peak_calendar_month!.median);
    for (const p of points) {
      const c = stats.climatology.months.find((m) => m.month === p.month)!;
      expect([p.p10, p.p25, p.median, p.p75, p.p90]).toEqual([c.p10, c.p25, c.median, c.p75, c.p90]);
      expect(p.p10! <= p.p25! && p.p25! <= p.median! && p.median! <= p.p75! && p.p75! <= p.p90!).toBe(true);
    }
  });
  it("anomaly is value minus the median of the calendar month", () => {
    const a = anomalies(cal, stats);
    const dec = a.find((p) => p.key === "2016-12")!;
    expect(dec.diff).toBeCloseTo(stats.anomaly.abs_anomaly!, 6);
    expect(anomalies(cal, { ...stats, scale: "modis_eq" })).toEqual([]);
  });
});

describe("toCsv", () => {
  it("writes a header, escapes and leaves nulls empty", () => {
    expect(toCsv(["a", "b"], [[1, null], ['x,"y"', 2]])).toBe('a,b\r\n1,\r\n"x,""y""",2\r\n');
  });
});
