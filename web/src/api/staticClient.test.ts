import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { buildStats, clipWindow, createStaticClient } from "./staticClient";

const meta = { layer: "L", source: "S" } as never;
const areaInfo = { type: "polygon", n_polygons: 1, n_vertices: 4, area_km2: 1000, bbox: [-32, -31, -65, -64] } as never;
const row = (year: number, month: number, viirs_eq: number | null) => ({ year, month, viirs_eq, modis_eq: null, cells: 1 });

const files: Record<string, unknown> = {
  "manifest.json": { version: 1, default_area: "p-x", boundaries: { attribution: "A" } },
  "areas.json": {
    areas: [{ id: "p-x", kind: "province", name: "X", province_id: null, bbox: [-32, -31, -65, -64], area_km2: 1, n_cells: 2 }],
  },
  "areas/p-x.json": {
    id: "p-x",
    name: "X",
    kind: "province",
    outline: [[[-65, -32], [-64, -32], [-64, -31], [-65, -31], [-65, -32]]],
    cells: [[-31.45, -64.55], [-31.35, -64.55]],
  },
  "calendar/p-x/viirs_eq.json": {
    meta, area: areaInfo, n_cells: 2, period: { start: "2020-01", end: "2020-03" }, scale: "viirs_eq",
    months: [row(2020, 1, 5), row(2020, 2, 0), row(2020, 3, null)],
  },
  "stats/p-x/viirs_eq.json": {
    meta, area: areaInfo, n_cells: 2, period: { start: "2020-01", end: "2020-03" }, scale: "viirs_eq", default_ref: "2020-03",
    climatology_by_year: { "2020": { months: [], baseline_years: [2019], quantile_method: "q" }, "2019": { months: [], baseline_years: [2018], quantile_method: "q" } },
    by_ref: {
      "2020-03": { anomaly: { ref: { year: 2020, month: 3 }, value: 1 }, key_figures: { total: 1 } },
      "2019-12": { anomaly: { ref: { year: 2019, month: 12 }, value: 2 }, key_figures: { total: 2 } },
    },
  },
  "cells/viirs_eq/2020-01.json": {
    month: "2020-01", scale: "viirs_eq",
    cells: [[-31.35, -64.55, 3, 0], [-31.45, -64.55, 2, 1], [-31.45, -63.05, 9, 0], [-40.05, -64.55, 7, 0]],
  },
  "export/p-x/viirs_eq.csv": "year,month\n2020,1\n",
};

function fakeFetch() {
  return vi.fn(async (url: string | URL | Request) => {
    const path = String(url).replace("https://data.test/v1/", "");
    if (!(path in files)) return new Response("nope", { status: 404 });
    const body = files[path];
    return typeof body === "string" ? new Response(body) : Response.json(body);
  });
}
const make = () => {
  const f = fakeFetch();
  return { f, c: createStaticClient("https://data.test/v1/", f as unknown as typeof fetch) };
};

describe("static client: path mapping", () => {
  it("maps calendar, stats, export and manifest requests to the contract paths", async () => {
    const { f, c } = make();
    await c.postCalendar({ region: "p-x", scale: "viirs_eq" });
    await c.postStats({ region: "p-x", scale: "viirs_eq" });
    await c.manifest();
    const csv = await c.postExport({ region: "p-x", scale: "viirs_eq", kind: "calendar" });
    expect(f.mock.calls.map((x) => x[0])).toEqual([
      "https://data.test/v1/calendar/p-x/viirs_eq.json",
      "https://data.test/v1/stats/p-x/viirs_eq.json",
      "https://data.test/v1/manifest.json",
      "https://data.test/v1/export/p-x/viirs_eq.csv",
    ]);
    expect(await csv.text()).toContain("year,month");
    expect(csv.headers.get("Content-Disposition")).toBe('attachment; filename="firecal_calendar_p-x_viirs_eq.csv"');
  });

  it("defaults the scale to viirs_eq, caches JSON per URL and rejects non-region requests", async () => {
    const { f, c } = make();
    await c.postCalendar({ region: "p-x" });
    await c.postCalendar({ region: "p-x", scale: "viirs_eq" });
    expect(f).toHaveBeenCalledTimes(1);
    await expect(c.postCalendar({ preset: "cordoba" })).rejects.toMatchObject({ status: 400 });
  });

  it("only publishes the calendar CSV and never raw detections", async () => {
    const { c } = make();
    await expect(c.postExport({ region: "p-x", kind: "cells" })).rejects.toBeInstanceOf(ApiError);
    await expect(c.getDetections({ region: "p-x", month: "2020-01", bbox: [-32, -31, -65, -64] })).rejects.toMatchObject({ status: 404 });
  });
});

describe("static client: stats", () => {
  it("without ref answers default_ref with the unchosen labels", async () => {
    const { c } = make();
    const s = await c.postStats({ region: "p-x" });
    expect(s.anomaly.value).toBe(1);
    expect(s.anomaly.ref_label_en).toBe("latest available month (retrospective)");
    expect(s.anomaly.ref_label_es).toBe("último mes disponible (retrospectivo)");
    expect(s.climatology.baseline_years).toEqual([2019]);
  });

  it("with ref takes the climatology of the ref year and the chosen labels", async () => {
    const { c } = make();
    const s = await c.postStats({ region: "p-x", ref: "2019-12" });
    expect(s.anomaly.value).toBe(2);
    expect(s.key_figures).toEqual({ total: 2 });
    expect(s.climatology.baseline_years).toEqual([2018]);
    expect(s.anomaly.ref_label_en).toBe("chosen reference month (retrospective)");
    expect(s.anomaly.ref_label_es).toBe("mes de referencia elegido (retrospectivo)");
  });

  it("a ref outside the file is a 404", async () => {
    const { c } = make();
    await expect(c.postStats({ region: "p-x", ref: "1999-01" })).rejects.toMatchObject({ status: 404 });
    expect(() => buildStats(files["stats/p-x/viirs_eq.json"] as never, "2020-05")).toThrow(ApiError);
  });
});

describe("static client: cells", () => {
  it("keeps the area's cells, sorted, with the outline and the calendar total", async () => {
    const { c } = make();
    const r = await c.getCells({ region: "p-x", scale: "viirs_eq", month: "2020-01" });
    // (-31.45,-63.05) is outside the area and (-40.05,-64.55) outside the cell list.
    expect(r.cells).toEqual([
      { cell_lat: -31.45, cell_lon: -64.55, value: 2, estimated: true },
      { cell_lat: -31.35, cell_lon: -64.55, value: 3, estimated: false },
    ]);
    expect(r.total).toBe(5);
    expect(r.outline).toHaveLength(1);
    expect(r.month).toBe("2020-01");
    expect(r.bbox).toBeNull();
  });

  it("applies the view window clipped to the area bbox", async () => {
    const { c } = make();
    const r = await c.getCells({ region: "p-x", month: "2020-01", bbox: [-31.5, -20, -66, -64.5] });
    expect(r.bbox).toEqual([-31.5, -31, -65, -64.5]);
    expect(r.cells.map((x) => x.cell_lat)).toEqual([-31.45, -31.35]);
    const none = await c.getCells({ region: "p-x", month: "2020-01", bbox: [-31.4, -31.36, -66, -64.5] });
    expect(none.cells).toEqual([]);
    const away = await c.getCells({ region: "p-x", month: "2020-01", bbox: [-50, -45, -70, -66] });
    expect(away.bbox).toBeNull();
    expect(away.cells).toEqual([]);
  });

  it("a month without a cells file is empty when the calendar has it, a 404 otherwise; total can be null", async () => {
    const { c } = make();
    const empty = await c.getCells({ region: "p-x", month: "2020-03" });
    expect(empty.cells).toEqual([]);
    expect(empty.total).toBeNull();
    expect((await c.getCells({ region: "p-x", month: "2020-02" })).total).toBe(0);
    await expect(c.getCells({ region: "p-x", month: "2030-01" })).rejects.toMatchObject({ status: 404 });
  });

  it("a missing calendar or area file is a 404 and is not cached", async () => {
    const { f, c } = make();
    await expect(c.postCalendar({ region: "p-nope" })).rejects.toMatchObject({ status: 404 });
    await expect(c.postCalendar({ region: "p-nope" })).rejects.toMatchObject({ status: 404 });
    expect(f).toHaveBeenCalledTimes(2);
  });
});

describe("clipWindow", () => {
  it("intersects with the area and the data domain", () => {
    expect(clipWindow([-60, -10, -80, -50], [-35, -30, -66, -60])).toEqual([-35, -30, -66, -60]);
    expect(clipWindow([-31, -30, -66, -65], [-35, -34, -66, -60])).toBeNull();
  });
});
