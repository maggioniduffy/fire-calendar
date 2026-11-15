import { describe, expect, it } from "vitest";
import es from "../i18n/es";
import en from "../i18n/en";
import { modisScale, sourceLevelText, statusView } from "./monthStatus";

describe("sourceLevelText", () => {
  it("names one level in plain words", () => {
    expect(sourceLevelText({ source_level: "nrt", source_levels: "nrt" }, es)).toBe(es.status.levels.nrt);
    expect(sourceLevelText({ source_level: "country-sp" }, en)).toBe(en.status.levels["country-sp"]);
  });
  it("joins every level of a mixed month, in order", () => {
    expect(sourceLevelText({ source_level: "mixed", source_levels: "api-sp+nrt" }, en)).toBe(
      `${en.status.levels["api-sp"]} + ${en.status.levels.nrt}`,
    );
  });
  it("is empty without level and keeps unknown codes", () => {
    expect(sourceLevelText({}, es)).toBe("");
    expect(sourceLevelText({ source_level: null, source_levels: null }, es)).toBe("");
    expect(sourceLevelText({ source_levels: "x-new" }, es)).toBe("x-new");
  });
});

describe("statusView", () => {
  it("flags provisional months only when the payload says so", () => {
    expect(statusView({ provisional: true, source_level: "nrt" }, "viirs_eq", es).provisional).toBe(true);
    expect(statusView({ provisional: false }, "viirs_eq", es).provisional).toBe(false);
    expect(statusView({}, "viirs_eq", es).provisional).toBe(false);
    expect(statusView(null, "viirs_eq", es)).toEqual({ provisional: false, sourceText: "", drift: false });
  });
  it("shows drift only in the scales that include MODIS", () => {
    const row = { modis_drift: true };
    expect(statusView(row, "modis_eq", es).drift).toBe(true);
    expect(statusView(row, "reported", es).drift).toBe(true);
    expect(statusView(row, "viirs_eq", es).drift).toBe(false);
    expect(statusView({ modis_drift: false }, "modis_eq", es).drift).toBe(false);
    expect(modisScale("viirs_eq")).toBe(false);
  });
});
