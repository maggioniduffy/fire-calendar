import { describe, expect, it } from "vitest";
import {
  initialSelection,
  parseNumber,
  polygonAreaKm2,
  selectionReducer,
  areaBounds,
  circleRing,
  toCellsRequest,
  toRequest,
  validateCircle,
  validatePolygon,
  type SelectionAction,
  type SelectionState,
} from "./selection";

const run = (actions: SelectionAction[], from: SelectionState = initialSelection) =>
  actions.reduce(selectionReducer, from);

// ~ 1 x 1 degree box near Córdoba city (about 10,000 km2).
const box: [number, number][] = [
  [-64.6, -32],
  [-63.6, -32],
  [-63.6, -31],
  [-64.6, -31],
];

describe("validateCircle", () => {
  it("accepts the geolocation default and the limits", () => {
    expect(validateCircle(-31.42, -64.18, 230)).toBeNull();
    expect(validateCircle(-31.42, -64.18, 5)).toBeNull();
    expect(validateCircle(-31.42, -64.18, 500)).toBeNull();
  });
  it("rejects a radius outside 5-500 km", () => {
    expect(validateCircle(-31, -64, 4.9)).toBe("radius");
    expect(validateCircle(-31, -64, 500.1)).toBe("radius");
  });
  it("rejects invalid and out-of-Argentina points", () => {
    expect(validateCircle(NaN, -64, 100)).toBe("invalid");
    expect(validateCircle(91, -64, 100)).toBe("invalid");
    expect(validateCircle(40.4, -3.7, 100)).toBe("outside"); // Madrid
    expect(validateCircle(-31, -64, 100)).toBeNull();
  });
});

describe("validatePolygon", () => {
  it("needs 3 vertices, Argentina and 100-3,000,000 km2", () => {
    expect(validatePolygon(box.slice(0, 2))).toBe("vertices");
    expect(validatePolygon(box)).toBeNull();
    expect(validatePolygon(box.map(([lo, la]) => [lo + 100, la] as [number, number]))).toBe("outside");
    expect(validatePolygon([[-64, -31], [-63.99, -31], [-64, -31.01]])).toBe("size");
  });
  it("computes the area like the backend (cylindrical equal-area)", () => {
    expect(polygonAreaKm2(box)).toBeGreaterThan(9000);
    expect(polygonAreaKm2(box)).toBeLessThan(11000);
  });
});

describe("parseNumber", () => {
  it("accepts dot and comma decimals and rejects junk", () => {
    expect(parseNumber(" -31.4 ")).toBe(-31.4);
    expect(parseNumber("-31,4")).toBe(-31.4);
    for (const bad of ["", "abc", "1e3", "--1", "1.2.3"]) expect(parseNumber(bad)).toBeNull();
  });
});

describe("selectionReducer", () => {
  it("starts on the Córdoba preset", () => {
    expect(toRequest(initialSelection)).toEqual({ scale: "viirs_eq", preset: "cordoba" });
  });

  it("sets a valid circle and ignores an invalid one", () => {
    const s = run([{ type: "setCircle", lat: -31.4201, lon: -64.1799, radiusKm: 230, source: "geolocation" }]);
    expect(s.area).toEqual({ kind: "circle", lat: -31.42, lon: -64.18, radiusKm: 230, source: "geolocation" });
    expect(toRequest(s).area).toEqual({ type: "circle", lat: -31.42, lon: -64.18, radius_km: 230 });
    expect(run([{ type: "setCircle", lat: -31, lon: -64, radiusKm: 1, source: "manual" }])).toBe(initialSelection);
  });

  it("draws a polygon and closes the ring in the request", () => {
    const s = run([
      { type: "drawStart" },
      ...box.map((vertex): SelectionAction => ({ type: "drawVertex", vertex })),
      { type: "drawFinish" },
    ]);
    expect(s.draw.active).toBe(false);
    expect(s.area.kind).toBe("polygon");
    const ring = (toRequest(s).area as { geojson: { coordinates: number[][][] } }).geojson.coordinates[0];
    expect(ring).toHaveLength(5);
    expect(ring[0]).toEqual(ring[4]);
  });

  it("keeps drawing with an error when closing with fewer than 3 vertices", () => {
    const s = run([
      { type: "drawStart" },
      { type: "drawVertex", vertex: box[0] },
      { type: "drawVertex", vertex: box[1] },
      { type: "drawFinish" },
    ]);
    expect(s.draw.active).toBe(true);
    expect(s.draw.error).toBe("vertices");
    expect(s.area).toEqual(initialSelection.area);
  });

  it("cancels the draft and ignores vertices when not drawing", () => {
    expect(run([{ type: "drawVertex", vertex: box[0] }])).toBe(initialSelection);
    const s = run([{ type: "drawStart" }, { type: "drawVertex", vertex: box[0] }, { type: "drawCancel" }]);
    expect(s.draw).toEqual({ active: false, vertices: [], error: null });
    expect(s.area).toEqual(initialSelection.area);
  });

  it("maps 'reported' to viirs_eq in the request but keeps it in state", () => {
    const s = run([{ type: "setScale", scale: "reported" }]);
    expect(s.scale).toBe("reported");
    expect(toRequest(s).scale).toBe("viirs_eq");
    expect(toRequest(run([{ type: "setScale", scale: "modis_eq" }])).scale).toBe("modis_eq");
  });

  it("includes the period only when set, and holds the month", () => {
    const s = run([{ type: "setPeriod", period: { start: "2005-01" } }, { type: "setMonth", month: "2015-09" }]);
    expect(toRequest(s)).toEqual({ scale: "viirs_eq", preset: "cordoba", start: "2005-01" });
    expect(s.month).toBe("2015-09");
  });

  it("returns to the preset", () => {
    const s = run([
      { type: "setCircle", lat: -31, lon: -64, radiusKm: 100, source: "manual" },
      { type: "setPreset" },
    ]);
    expect(s.area).toEqual(initialSelection.area);
  });
});

describe("map helpers", () => {
  it("builds the /cells body only once a month is chosen, without the period", () => {
    expect(toCellsRequest(initialSelection)).toBeNull();
    const s = run([{ type: "setMonth", month: "2016-12" }, { type: "setPeriod", period: { start: "2010-01" } }]);
    expect(toCellsRequest(s)).toEqual({ preset: "cordoba", scale: "viirs_eq", month: "2016-12" });
    expect(toCellsRequest(s, [-33, -30, -65, -62])).toEqual({
      preset: "cordoba",
      scale: "viirs_eq",
      month: "2016-12",
      bbox: [-33, -30, -65, -62],
    });
  });

  it("bounds a circle and a polygon as [west, south, east, north]", () => {
    const c = run([{ type: "setCircle", lat: -31.42, lon: -64.18, radiusKm: 111.195, source: "manual" }]);
    const [w, s, e, n] = areaBounds(c.area, [-65.8, -35, -61.7, -29.5]);
    expect(n - s).toBeCloseTo(2, 3);
    expect((w + e) / 2).toBeCloseTo(-64.18, 3);
    const p = run([{ type: "drawStart" }, ...box.map((v) => ({ type: "drawVertex", vertex: v }) as const), { type: "drawFinish" }]);
    expect(areaBounds(p.area, [0, 0, 0, 0])).toEqual([-64.6, -32, -63.6, -31]);
  });

  it("closes the circle ring", () => {
    const ring = circleRing(-31.42, -64.18, 230);
    expect(ring).toHaveLength(65);
    expect(ring[0]).toEqual(ring[64]);
  });
});
