import { describe, expect, it } from "vitest";
import { clampWidth, maxWidthFor, MIN_WIDTH, widthAfterKey } from "./PanelResizer";

describe("PanelResizer helpers", () => {
  it("caps the maximum at 40% of the viewport and 560 px, never below the minimum", () => {
    expect(maxWidthFor(1000)).toBe(400);
    expect(maxWidthFor(2000)).toBe(560);
    expect(maxWidthFor(300)).toBe(MIN_WIDTH);
  });
  it("clamps widths into [min, max]", () => {
    expect(clampWidth(100, 1000)).toBe(MIN_WIDTH);
    expect(clampWidth(900, 1000)).toBe(400);
    expect(clampWidth(300, 1000)).toBe(300);
  });
  it("steps with the arrow keys and clamps at the ends", () => {
    expect(widthAfterKey("ArrowRight", 260, 1000)).toBe(276);
    expect(widthAfterKey("ArrowLeft", 260, 1000)).toBe(244);
    expect(widthAfterKey("ArrowLeft", MIN_WIDTH, 1000)).toBe(MIN_WIDTH);
    expect(widthAfterKey("ArrowRight", 400, 1000)).toBe(400);
    expect(widthAfterKey("Home", 300, 1000)).toBe(MIN_WIDTH);
    expect(widthAfterKey("End", 300, 1000)).toBe(400);
    expect(widthAfterKey("x", 300, 1000)).toBeNull();
  });
});
