import { describe, expect, it } from "vitest";
import { colors, type ThemeName } from "../theme/tokens";
import { anomalyRatio, divergingColor, divergingStops, lightness, sequentialColor, sequentialStops } from "./scales";

const themes: ThemeName[] = ["light", "dark"];
const grid = Array.from({ length: 101 }, (_, i) => i / 100);

/** Lightness grows with the value on dark and falls on light; strictly monotonic either way. */
const direction: Record<ThemeName, 1 | -1> = { dark: 1, light: -1 };

const channels = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

describe("sequentialColor", () => {
  it.each(themes)("is strictly monotonic in lightness (%s)", (theme) => {
    const ls = grid.map((x) => lightness(sequentialColor(x * 50, 50, theme)!));
    for (let i = 1; i < ls.length; i++) expect((ls[i] - ls[i - 1]) * direction[theme]).toBeGreaterThan(0);
  });

  it.each(themes)("hits the first and last stop at 0 and max (%s)", (theme) => {
    const s = sequentialStops[theme];
    expect(sequentialColor(0, 10, theme)).toBe(s[0]);
    expect(sequentialColor(10, 10, theme)).toBe(s[s.length - 1]);
  });

  it("clamps below 0 and above max", () => {
    expect(sequentialColor(-5, 10)).toBe(sequentialColor(0, 10));
    expect(sequentialColor(99, 10)).toBe(sequentialColor(10, 10));
  });

  it("returns null (no data) for null, NaN, infinity and an unusable max", () => {
    expect(sequentialColor(null, 10)).toBeNull();
    expect(sequentialColor(undefined, 10)).toBeNull();
    expect(sequentialColor(NaN, 10)).toBeNull();
    expect(sequentialColor(Infinity, 10)).toBeNull();
    expect(sequentialColor(5, 0)).toBeNull();
    expect(sequentialColor(5, NaN)).toBeNull();
  });

  it("stays in one blue-violet hue family", () => {
    for (const theme of themes)
      for (const hex of sequentialStops[theme]) {
        const [r, g, b] = channels(hex);
        expect(b).toBeGreaterThanOrEqual(r);
        expect(b).toBeGreaterThan(g);
      }
  });
});

describe("divergingColor", () => {
  it.each(themes)("centre is the neutral --raised token (%s)", (theme) => {
    expect(divergingColor(0, theme)).toBe(colors[theme].raised.toUpperCase());
  });

  it.each(themes)("endpoints are the last blue and orange stops, clamped beyond ±1 (%s)", (theme) => {
    const d = divergingStops[theme];
    expect(divergingColor(-1, theme)).toBe(d.below.at(-1));
    expect(divergingColor(1, theme)).toBe(d.above.at(-1));
    expect(divergingColor(-7, theme)).toBe(divergingColor(-1, theme));
    expect(divergingColor(7, theme)).toBe(divergingColor(1, theme));
  });

  it.each(themes)("lightness is monotonic away from the centre on each side (%s)", (theme) => {
    for (const sign of [-1, 1]) {
      const ls = grid.map((x) => lightness(divergingColor(sign * x, theme)!));
      for (let i = 1; i < ls.length; i++) expect((ls[i] - ls[i - 1]) * direction[theme]).toBeGreaterThan(0);
    }
  });

  it("below is blue and above is orange at full magnitude", () => {
    for (const theme of themes) {
      const [br, , bb] = channels(divergingColor(-1, theme)!);
      const [ar, , ab] = channels(divergingColor(1, theme)!);
      expect(bb).toBeGreaterThan(br);
      expect(ar).toBeGreaterThan(ab);
    }
  });

  it("returns null (no data) for null, NaN and infinity", () => {
    expect(divergingColor(null)).toBeNull();
    expect(divergingColor(NaN)).toBeNull();
    expect(divergingColor(-Infinity)).toBeNull();
  });
});

describe("anomalyRatio", () => {
  it("is the relative departure from the median", () => {
    expect(anomalyRatio(150, 100)).toBe(0.5);
    expect(anomalyRatio(50, 100)).toBe(-0.5);
  });
  it("handles a zero median and missing numbers", () => {
    expect(anomalyRatio(0, 0)).toBe(0);
    expect(anomalyRatio(3, 0)).toBe(1);
    expect(anomalyRatio(3, null)).toBeNull();
    expect(anomalyRatio(NaN, 5)).toBeNull();
    expect(anomalyRatio(null, 5)).toBeNull();
  });
});
