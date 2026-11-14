import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { colorTokenNames, colors, hexToRgb, radius, space } from "./tokens";

const css = readFileSync(join(__dirname, "tokens.css"), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  expect(start, `selector ${selector} in tokens.css`).toBeGreaterThanOrEqual(0);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

describe("design tokens", () => {
  it.each([
    ["light", ':root[data-theme="light"]'],
    ["dark", ':root[data-theme="dark"]'],
  ] as const)("%s colours in tokens.css match tokens.ts", (theme, selector) => {
    const vars = block(selector);
    for (const name of colorTokenNames) {
      expect(vars[name]?.toUpperCase(), `--${name}`).toBe(colors[theme][name].toUpperCase());
    }
  });

  it("spacing and radii match", () => {
    const vars = block(":root {\n  --space-1");
    space.forEach((px, i) => expect(vars[`space-${i + 1}`]).toBe(`${px}px`));
    radius.forEach((px, i) => expect(vars[`radius-${i + 1}`]).toBe(`${px}px`));
  });

  it("never uses pure white or black", () => {
    for (const theme of Object.values(colors)) {
      for (const hex of Object.values(theme)) {
        expect(["#FFFFFF", "#000000"]).not.toContain(hex.toUpperCase());
      }
    }
  });

  it("converts hex to rgb", () => {
    expect(hexToRgb("#8EB8E5")).toEqual([142, 184, 229]);
    expect(() => hexToRgb("red")).toThrow();
  });
});
