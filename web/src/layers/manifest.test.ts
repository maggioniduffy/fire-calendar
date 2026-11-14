import { describe, expect, it } from "vitest";
import { parseManifest, splitPeriod } from "./manifest";
import { fakeLayer } from "./fakeLayer";

const valid = {
  id: "fire-grid",
  title: "Focos",
  kind: "grid",
  source: "NASA FIRMS",
  period: "2000-11-01/2026-08-31",
  license: "NASA open data",
  updated_at: "2026-11-14T00:00:00Z",
  files: ["grid.parquet"],
};

describe("manifest", () => {
  it("accepts a valid manifest with or without experimental", () => {
    expect(parseManifest(valid).id).toBe("fire-grid");
    expect(parseManifest({ ...valid, experimental: true }).experimental).toBe(true);
  });

  it.each([
    ["no source", { ...valid, source: undefined }],
    ["empty license", { ...valid, license: "" }],
    ["bad kind", { ...valid, kind: "raster" }],
    ["bad period", { ...valid, period: "2000" }],
    ["bad experimental", { ...valid, experimental: "yes" }],
    ["bad files", { ...valid, files: "grid.parquet" }],
  ])("rejects %s", (_, m) => {
    expect(() => parseManifest(m)).toThrow();
  });

  it("splits the period", () => {
    expect(splitPeriod(valid.period)).toEqual(["2000-11-01", "2026-08-31"]);
  });

  it("the fake fixture follows the contract and stays in Córdoba province", () => {
    expect(fakeLayer.manifest.kind).toBe("points");
    expect(fakeLayer.points.length).toBeGreaterThan(0);
    for (const p of fakeLayer.points) {
      expect(p.lon).toBeGreaterThan(-66);
      expect(p.lon).toBeLessThan(-61.7);
      expect(p.lat).toBeGreaterThan(-35.1);
      expect(p.lat).toBeLessThan(-29.4);
    }
  });
});
