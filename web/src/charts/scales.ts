// Colour scales shared by the calendar (SA4.3/4.4) and the dashboard (SA4.8).
//
// Both scales are colour-blind safe by construction: the sequential one varies a single hue (violet) and carries
// the value in lightness only; the diverging one is blue vs. orange (the pair that survives deuteranopia and
// protanopia) and again carries magnitude in lightness. Hexes are plain data, not tokens: the neutral centre of
// the diverging ramp IS a token (`--raised`), read from theme/tokens.ts.
//
// Direction of lightness (documented decision): on the dark theme more fire is lighter (as docs/design.md asks);
// on the cream light theme more fire is darker, so the heaviest months are also the heaviest "ink".
// Both are strictly monotonic in L*; scales.test.ts checks it.

import { colors, type ThemeName } from "../theme/tokens";

/** Colour stops from "low" to "high". */
export type Stops = readonly string[];

/** Sequential single-hue ramp (violet), low → high value. */
export const sequentialStops: Record<ThemeName, Stops> = {
  light: ["#ECE8F8", "#CFC6F0", "#A798DC", "#7B67BF", "#543F94", "#2F2260"],
  dark: ["#2B2640", "#3F3470", "#5B4B9E", "#8573C8", "#B3A5E8", "#E0D9FA"],
};

/** Diverging ramps from the neutral centre outwards, magnitude 0 → 1 (blue: below, orange: above). */
export const divergingStops: Record<ThemeName, { below: Stops; above: Stops }> = {
  light: {
    below: ["#BBD1EA", "#7FA6D6", "#2F5F9E"],
    above: ["#F3CBA0", "#E8985A", "#B4531A"],
  },
  dark: {
    below: ["#3F5F85", "#5E8DC4", "#9CC1F2"],
    above: ["#8A5A33", "#D08540", "#FFB878"],
  },
};

type Rgb = [number, number, number];

function parse(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function format([r, g, b]: Rgb): string {
  return "#" + [r, g, b].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("").toUpperCase();
}

/** Linear interpolation along evenly spaced stops; `t` in [0, 1]. */
function along(stops: Stops, t: number): string {
  const x = t * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  const f = x - i;
  const a = parse(stops[i]);
  const b = parse(stops[i + 1]);
  return format([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]);
}

/** CIE L* (0-100) of a "#RRGGBB" colour; used to verify that ramps are monotonic in lightness. */
export function lightness(hex: string): number {
  const lin = parse(hex).map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  const y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  return y > 216 / 24389 ? 116 * Math.cbrt(y) - 16 : (24389 / 27) * y;
}

const finite = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/**
 * Colour of a count on the sequential ramp: `value` 0 → first stop, `value >= max` → last stop (clamped, so a
 * value above the maximum does not extrapolate; negative values clamp to the first stop). Linear in value.
 * Returns `null` ("no data") when `value` is null/NaN/Infinity or `max` is not a positive finite number.
 */
export function sequentialColor(value: number | null | undefined, max: number, theme: ThemeName = "light"): string | null {
  if (!finite(value) || !Number.isFinite(max) || max <= 0) return null;
  return along(sequentialStops[theme], Math.min(Math.max(value / max, 0), 1));
}

/**
 * Colour of an anomaly on the diverging ramp. `ratio` is the signed relative departure from the median
 * ((value − median) / median, see `anomalyRatio`): 0 → neutral `--raised`, −1 or less → full blue ("below"),
 * +1 or more → full orange ("above"); in between it is interpolated and clamped.
 * Returns `null` ("no data") for null/NaN/Infinity.
 */
export function divergingColor(ratio: number | null | undefined, theme: ThemeName = "light"): string | null {
  if (!finite(ratio)) return null;
  const r = Math.min(Math.max(ratio, -1), 1);
  const side = r < 0 ? divergingStops[theme].below : divergingStops[theme].above;
  return along([colors[theme].raised.toUpperCase(), ...side], Math.abs(r));
}

/** Signed relative departure for `divergingColor`; null when the median is missing or a number is not finite. */
export function anomalyRatio(value: number | null | undefined, median: number | null | undefined): number | null {
  if (!finite(value) || !finite(median) || median < 0) return null;
  if (median === 0) return value > 0 ? 1 : 0;
  return (value - median) / median;
}

/** CSS `linear-gradient` for a legend bar of the sequential ramp. */
export function sequentialGradient(theme: ThemeName = "light"): string {
  return `linear-gradient(90deg, ${sequentialStops[theme].join(", ")})`;
}

/** CSS `linear-gradient` for a legend bar of the diverging ramp: blue at left, neutral centre, orange at right. */
export function divergingGradient(theme: ThemeName = "light"): string {
  const d = divergingStops[theme];
  return `linear-gradient(90deg, ${[...[...d.below].reverse(), colors[theme].raised, ...d.above].join(", ")})`;
}
