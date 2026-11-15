import { describe, expect, it } from "vitest";
import type { CalendarPayload, MonthRow, StatsPayload } from "../api/types";
import { selectionFromSearch, toStatsRequest, initialSelection } from "./selection";
import { buildInspectorModel, formatCount, formatPercent, hasReported, NO_VALUE } from "./inspectorModel";

const row = (year: number, over: Partial<MonthRow> = {}): MonthRow => ({
  year, month: 9, modis_reported: 10, viirs_reported: null, modis_eq: 10, viirs_eq: 18,
  cells: 3, modis_eq_status: "observed", viirs_eq_status: "estimated", ...over,
}); // prettier-ignore

const calendar = { months: [row(2005), row(2015, { viirs_reported: 20, viirs_eq: 20, viirs_eq_status: "observed" })] } as CalendarPayload;
const stats = (year: number) => ({ anomaly: { ref: { year, month: 9 } } }) as StatsPayload;

describe("buildInspectorModel", () => {
  it("flags an estimated month only on the scale that estimates it", () => {
    expect(buildInspectorModel(calendar, stats(2005), "viirs_eq").estimated).toBe(true);
    expect(buildInspectorModel(calendar, stats(2005), "modis_eq").estimated).toBe(false);
    expect(buildInspectorModel(calendar, stats(2015), "viirs_eq").estimated).toBe(false);
  });
  it("reads reported counts per sensor, without summing, and drops the harmonized figures", () => {
    const m = buildInspectorModel(calendar, stats(2015), "reported");
    expect(m.reported).toEqual({ modis: 10, viirs: 20 });
    expect(m.harmonized).toBe(false);
    expect(m.estimated).toBe(false);
    expect(buildInspectorModel(calendar, stats(2005), "reported").reported).toEqual({ modis: 10, viirs: null });
  });
  it("has no row when the month is outside the matrix", () => {
    expect(buildInspectorModel(calendar, stats(1999), "viirs_eq").row).toBeNull();
  });
});

describe("hasReported", () => {
  it("is false when no month has a reported value", () => {
    expect(hasReported(calendar)).toBe(true);
    expect(hasReported({ months: [row(2005, { modis_reported: null })] } as CalendarPayload)).toBe(false);
  });
});

describe("formatting", () => {
  it("uses a dash for missing values and signs the percent", () => {
    expect(formatCount(null, "es")).toBe(NO_VALUE);
    expect(formatPercent(undefined, "es")).toBe(NO_VALUE);
    expect(formatPercent(0.13, "en")).toBe("+13%");
    expect(formatPercent(-0.2, "en")).toContain("20%");
  });
});

describe("chosen month in the request", () => {
  it("adds ref to /stats only when a month is chosen", () => {
    expect(toStatsRequest(initialSelection)).toEqual({ preset: "cordoba", scale: "viirs_eq" });
    expect(toStatsRequest(selectionFromSearch("?month=2005-09"))).toEqual({ preset: "cordoba", scale: "viirs_eq", ref: "2005-09" });
  });
  it("omits ref for the latest month of the period (same request as the default)", () => {
    const sel = selectionFromSearch("?month=2016-12");
    expect(toStatsRequest(sel, "2016-12")).toEqual({ preset: "cordoba", scale: "viirs_eq" });
    expect(toStatsRequest(sel, "2016-11")).toEqual({ preset: "cordoba", scale: "viirs_eq", ref: "2016-12" });
  });
  it("ignores an invalid month in the URL", () => {
    expect(selectionFromSearch("?month=2005-13").month).toBeNull();
    expect(selectionFromSearch("?month=abc").month).toBeNull();
    expect(selectionFromSearch("").month).toBeNull();
  });
});
