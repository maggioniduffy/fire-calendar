import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "./api";

/**
 * SA4.7: axe (WCAG 2 A/AA) with no violations on the Map and Dashboard tabs, in both themes and at phone width.
 * Keyboard-only polygon drawing is out of scope: lat/lon + radius is the keyboard alternative (docs/design.md).
 */
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
});

async function ready(page: Page, theme: "light" | "dark") {
  await page.goto("/");
  await page.getByTestId(`theme-${theme}`).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await expect(page.getByTestId("calendar-grid")).toBeVisible();
  await expect(page.getByTestId("fig-count")).toBeVisible();
}

/** Readable list of violations: id, impact and the first selectors with the failing summary. */
async function violations(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return r.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    nodes: v.nodes.slice(0, 4).map((n) => `${n.target.join(" ")} :: ${n.failureSummary?.split("\n").slice(1, 3).join(" ")}`),
  }));
}

async function noHorizontalScroll(page: Page) {
  const wide = await page.evaluate(() => document.scrollingElement!.scrollWidth > window.innerWidth);
  expect(wide, "horizontal scroll").toBe(false);
}

for (const theme of ["light", "dark"] as const) {
  test(`Map tab: no axe violations (${theme})`, async ({ page }) => {
    await ready(page, theme);
    expect(await violations(page), "count mode").toEqual([]);
    await page.getByTestId("calendar-mode-anomaly").click();
    await expect(page.getByTestId("calendar-legend")).toHaveAttribute("data-mode", "anomaly");
    expect(await violations(page), "anomaly mode").toEqual([]);
    // Left panel with each way of choosing the area open (coordinates form, drawing panel).
    await page.getByTestId("area-coords").click();
    await expect(page.getByTestId("coords-form")).toBeVisible();
    expect(await violations(page), "coordinates form").toEqual([]);
    await page.getByTestId("area-draw").click();
    await expect(page.getByTestId("draw-panel")).toBeVisible();
    expect(await violations(page), "draw panel").toEqual([]);
  });

  test(`Dashboard tab: no axe violations (${theme})`, async ({ page }) => {
    await ready(page, theme);
    await page.getByRole("tab", { name: "Tablero" }).click();
    await expect(page.getByTestId("chart-season")).toBeVisible();
    expect(await violations(page)).toEqual([]);
  });

  test(`phone width 360x740: no axe violations and no horizontal scroll (${theme})`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await ready(page, theme);
    await noHorizontalScroll(page);
    expect(await violations(page), "map tab").toEqual([]);
    // The left panel is a drawer at this width: open it and scan it too.
    await page.getByTestId("drawer-toggle").click();
    await expect(page.getByTestId("area-coords")).toBeVisible();
    await page.getByTestId("area-coords").click();
    await expect(page.getByTestId("coords-form")).toBeVisible();
    await noHorizontalScroll(page);
    expect(await violations(page), "open drawer with the coordinates form").toEqual([]);
    await page.getByTestId("drawer-toggle").click();
    await page.getByTestId("calendar-mode-anomaly").click();
    expect(await violations(page), "anomaly mode").toEqual([]);
    await page.getByRole("tab", { name: "Tablero" }).click();
    await expect(page.getByTestId("chart-season")).toBeVisible();
    await noHorizontalScroll(page);
    expect(await violations(page), "dashboard tab").toEqual([]);
  });
}

/** Region (nearest landmark test id) and a readable name of the element that has focus, with its focus ring. */
async function focused(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    const region = ["topbar", "left-panel", "center", "inspector", "strip-resizer", "calendar-strip"].find((id) => el.closest(`[data-testid="${id}"]`));
    const cs = getComputedStyle(el);
    return {
      region: region ?? "none",
      role: el.getAttribute("role") ?? el.tagName.toLowerCase(),
      id: el.getAttribute("data-testid") ?? el.id ?? "",
      ring: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2 ? cs.outlineColor : null,
    };
  });
}

test("keyboard: tab order topbar > left panel > tabs > inspector > resizer > calendar, every stop with a visible ring", async ({ page }) => {
  await ready(page, "light");
  const stops: Awaited<ReturnType<typeof focused>>[] = [];
  // Start from the first stop of the page.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press("Tab");
    const f = await focused(page);
    stops.push(f);
    if (f.region === "none") break; // left the app (browser chrome / body)
  }
  const first = (region: string) => stops.findIndex((s) => s.region === region);
  const order = ["topbar", "left-panel", "center", "inspector", "strip-resizer", "calendar-strip"].map(first);
  expect(order.every((i) => i >= 0), `regions reached: ${JSON.stringify(stops.map((s) => s.region))}`).toBe(true);
  expect(order, "regions in order").toEqual([...order].sort((a, b) => a - b));
  const bad = stops.filter((s) => s.region !== "none" && s.ring === null);
  expect(bad, "stops without a visible 2 px ring").toEqual([]);
  // Roving tabindex: the tab list and the calendar grid are one stop each.
  expect(stops.filter((s) => s.role === "tab")).toHaveLength(1);
  expect(stops.filter((s) => s.role === "gridcell")).toHaveLength(1);
  // The inspector has keyboard-reachable buttons (series selector, downloads).
  expect(stops.filter((s) => s.region === "inspector" && s.role === "button").length).toBeGreaterThan(0);
});

test("keyboard: the dashboard has a month stepper reachable after the tabs; charts follow the chosen month", async ({ page, api }) => {
  await ready(page, "light");
  await page.getByRole("tab", { name: "Tablero" }).click();
  await expect(page.getByTestId("chart-season")).toBeVisible();
  const latest = await page.getByTestId("month-current").innerText(); // YYYY-MM, the end of the period
  const [y, m] = latest.split("-").map(Number);
  const prev = m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
  await page.getByRole("tab", { name: "Tablero" }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("month-prev")).toBeFocused();
  expect((await focused(page)).ring, "visible focus ring").not.toBeNull();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("month-current")).toHaveText(prev);
  // The linked charts read the same month: /stats is asked for it, /calendar is not asked again.
  await expect.poll(() => api.to("/stats").at(-1)?.body.ref).toBe(prev);
  expect(api.to("/calendar")).toHaveLength(1);
  await expect(page.getByTestId("chart-monthly")).toContainText(prev);
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("month-next")).toBeFocused();
});

test("focus ring is the accent ring with a casing, in both themes", async ({ page }) => {
  for (const theme of ["light", "dark"] as const) {
    await ready(page, theme);
    await page.getByTestId("lang-en").focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    const css = await page.evaluate(() => {
      const cs = getComputedStyle(document.activeElement as HTMLElement);
      const root = getComputedStyle(document.documentElement);
      return { width: cs.outlineWidth, offset: cs.outlineOffset, color: cs.outlineColor, shadow: cs.boxShadow, accent: root.getPropertyValue("--accent").trim(), casing: root.getPropertyValue("--casing").trim() };
    });
    expect(css.width).toBe("2px");
    expect(css.offset).toBe("2px");
    const rgb = (hex: string) => `rgb(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(", ")})`;
    expect(css.color).toBe(rgb(css.accent));
    expect(css.shadow).toContain(rgb(css.casing));
  }
});
