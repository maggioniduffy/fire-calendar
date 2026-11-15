import { describe, expect, it } from "vitest";
import type { CalendarPayload, EnsoBlock, MonthRow, StatsPayload } from "../api/types";
import { buildGrid, cellAt, ensoAt, ensoIndex, neighbour } from "./calendarModel";

const row = (year: number, month: number, v: number | null, status: MonthRow["viirs_eq_status"] = "observed"): MonthRow => ({
  year,
  month,
  modis_reported: null,
  viirs_reported: null,
  modis_eq: null,
  viirs_eq: v,
  cells: 1,
  modis_eq_status: "none",
  viirs_eq_status: status,
});

const calendar = {
  scale: "viirs_eq",
  months: [row(2005, 1, 10, "estimated"), row(2005, 2, null, "none"), row(2007, 1, 30)],
} as unknown as CalendarPayload;
const stats = {
  climatology: { months: [{ month: 1, n_years: 2, median: 20, p10: 0, p25: 10, p75: 30, p90: 0 }, { month: 2, n_years: 0, median: null, p10: null, p25: null, p75: null, p90: null }] },
} as unknown as StatsPayload;

describe("buildGrid", () => {
  const g = buildGrid(calendar, stats);
  it("spans every year between the first and last, including missing ones", () => {
    expect(g.years).toEqual([2005, 2006, 2007]);
  });
  it("takes max and latest only from months with data", () => {
    expect(g.max).toBe(30);
    expect(g.latest).toBe("2007-01");
  });
  it("computes the anomaly ratio against the climatology median and keeps the estimated status", () => {
    expect(g.cells.get("2005-01")).toMatchObject({ value: 10, status: "estimated", median: 20, ratio: -0.5 });
    expect(g.cells.get("2007-01")?.ratio).toBe(0.5);
    expect(g.cells.get("2005-02")).toMatchObject({ value: null, status: "none", ratio: null });
  });
  it("answers a no-data cell for a month the payload lacks", () => {
    expect(cellAt(g, "2006-06")).toMatchObject({ value: null, status: "none" });
  });
});

describe("neighbour", () => {
  const g = buildGrid(calendar, stats);
  it("moves by year with Left/Right and by month with Up/Down, wrapping months across years", () => {
    expect(neighbour(g, "2005-05", "ArrowRight")).toBe("2006-05");
    expect(neighbour(g, "2006-05", "ArrowLeft")).toBe("2005-05");
    expect(neighbour(g, "2006-05", "ArrowDown")).toBe("2006-06");
    expect(neighbour(g, "2006-05", "ArrowUp")).toBe("2006-04");
    expect(neighbour(g, "2006-12", "ArrowDown")).toBe("2007-01");
    expect(neighbour(g, "2006-01", "ArrowUp")).toBe("2005-12");
  });
  it("jumps to the first and last year of the same month row with Home/End", () => {
    expect(neighbour(g, "2006-05", "Home")).toBe("2005-05");
    expect(neighbour(g, "2006-05", "End")).toBe("2007-05");
  });
  it("stops at the edges of the grid", () => {
    expect(neighbour(g, "2005-01", "ArrowLeft")).toBeNull();
    expect(neighbour(g, "2007-12", "ArrowRight")).toBeNull();
    expect(neighbour(g, "2005-01", "ArrowUp")).toBeNull();
    expect(neighbour(g, "2007-12", "ArrowDown")).toBeNull();
    expect(neighbour(g, "2006-05", "x")).toBeNull();
  });
});

describe("ENSO lookup by ym", () => {
  const enso = {
    months: [
      { ym: "2010-01", oni: 1.5, phase: "nino" },
      { ym: "2010-02", oni: -0.8, phase: "nina" },
      { ym: "2010-03", oni: null, phase: "neutral" },
    ],
  } as unknown as EnsoBlock;

  it("finds the phase and ONI of a month", () => {
    const idx = ensoIndex(enso);
    expect(ensoAt(idx, "2010-01")).toEqual({ ym: "2010-01", oni: 1.5, phase: "nino" });
    expect(ensoAt(idx, "2010-02").phase).toBe("nina");
  });

  it("a month without ONI or outside the block has no phase", () => {
    const idx = ensoIndex(enso);
    expect(ensoAt(idx, "2010-03").phase).toBeNull();
    expect(ensoAt(idx, "1999-07")).toEqual({ ym: "1999-07", oni: null, phase: null });
  });

  it("a null block gives an empty index", () => {
    expect(ensoIndex(null).size).toBe(0);
  });
});
