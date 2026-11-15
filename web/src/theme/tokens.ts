// Design tokens from docs/design.md. tokens.css must hold the same values;
// tokens.test.ts checks that they match.

export type ThemeName = "light" | "dark";

export const colorTokenNames = [
  "bg",
  "surface",
  "raised",
  "border",
  "text",
  "muted",
  "ctrl",
  "onctrl",
  "accent",
  "secondary",
  "casing",
  "enso-nino",
  "enso-nina",
] as const;

export type ColorToken = (typeof colorTokenNames)[number];

export const colors: Record<ThemeName, Record<ColorToken, string>> = {
  light: {
    bg: "#F1EEE6",
    surface: "#F9F7F2",
    raised: "#EFECE4",
    border: "#DDD8CD",
    text: "#2A343B",
    muted: "#5F6468",
    ctrl: "#3E505B",
    onctrl: "#F5F2EA",
    accent: "#8EB8E5",
    secondary: "#A4AF69",
    casing: "#2A343B",
    "enso-nino": "#C4552B",
    "enso-nina": "#3F7FB5",
  },
  dark: {
    bg: "#16212A",
    surface: "#1F2D37",
    raised: "#2A3A46",
    border: "#3E505B",
    text: "#ECE7DC",
    muted: "#A3AEB4",
    ctrl: "#4D6372",
    onctrl: "#ECE7DC",
    accent: "#FDDA0D",
    secondary: "#A4AF69",
    casing: "#16212A",
    "enso-nino": "#E98A5C",
    "enso-nina": "#6FA8DC",
  },
};

/** --space-1..6 in px. */
export const space = [4, 8, 12, 16, 24, 32] as const;
/** --radius-1..3 in px. */
export const radius = [4, 8, 12] as const;

/** "#RRGGBB" → [r, g, b] for deck.gl colour accessors. */
export function hexToRgb(hex: string): [number, number, number] {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`Not a #RRGGBB colour: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
