import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./api";

// SA5.4: ENSO phase strip under the calendar. SYNTHETIC fixture (backend/scripts/web_fixtures.py).
const DIR = join(import.meta.dirname, "fixtures/api");
interface Enso {
  source: string;
  period: { start: string; end: string };
  note_es: string;
  months: { ym: string; oni: number | null; phase: string }[];
  by_phase: { month: number; phase: string; n_years: number }[];
}
const fixture = JSON.parse(readFileSync(join(DIR, "calendar-cordoba-viirs_eq.json"), "utf8")) as { enso: Enso } & Record<string, unknown>;
const enso = fixture.enso;
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
});

/** Answer /calendar with the fixture after `edit` (route interception; the fixture files stay untouched). */
async function overrideCalendar(page: Page, edit: (body: typeof fixture) => void) {
  await page.route(
    (url) => url.pathname === "/api/calendar",
    (route) => {
      const body = structuredClone(fixture);
      edit(body);
      return route.fulfill({ json: body });
    },
  );
}

test("the strip renders with source and period, 12 segments per year column", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("enso-strip")).toBeVisible();
  const years = new Set(enso.months.map((m) => m.ym.slice(0, 4))).size;
  await expect(page.locator(".enso-year")).toHaveCount(years);
  await expect(page.locator(".enso-seg")).toHaveCount(years * 12);
  await expect(page.getByTestId("enso-source")).toContainText(enso.source);
  await expect(page.getByTestId("enso-source")).toContainText(`${enso.period.start}–${enso.period.end}`);
  await expect(page.getByTestId("enso-strip")).toHaveAttribute("aria-label", /ENSO/);
});

test("a segment names month, ONI, phase, source and period", async ({ page }) => {
  await page.goto("/");
  const m = enso.months.find((x) => x.phase === "nino")!;
  const seg = page.locator(`.enso-seg[data-enso-ym="${m.ym}"]`);
  await expect(seg).toHaveAttribute("data-phase", "nino");
  const label = (await seg.getAttribute("aria-label"))!;
  expect(label).toContain("El Niño");
  expect(label).toContain(m.ym.slice(0, 4));
  expect(label).toContain(String(m.oni!.toFixed(1)).replace(".", ","));
  expect(label).toContain(`Fuente: ${enso.source} · período ${enso.period.start}–${enso.period.end}`);
  await expect(seg).toHaveAttribute("title", label);
  const n = enso.months.find((x) => x.phase === "nina")!;
  await expect(page.locator(`.enso-seg[data-enso-ym="${n.ym}"]`)).toHaveAttribute("aria-label", /La Niña/);
});

test("segments are not focusable: the grid keeps its single roving stop", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("enso-strip")).toBeVisible();
  expect(await page.locator(".enso-strip [tabindex], .enso-strip a, .enso-strip button").count()).toBe(0);
  await expect(page.locator("[role=gridcell][tabindex='0']")).toHaveCount(1);
});

test("the legend shows three phases, source, period and the association note", async ({ page }) => {
  await page.goto("/");
  const legend = page.getByTestId("enso-legend");
  await expect(legend).toBeVisible();
  await expect(legend.locator("[data-phase]")).toHaveCount(3);
  await expect(legend).toContainText("Fuente: NOAA CPC ONI");
  await expect(page.getByTestId("enso-note")).toHaveText(enso.note_es);
  await page.getByTestId("lang-en").click();
  await expect(page.getByTestId("enso-note")).toContainText("Association, not cause");
  await expect(page.getByTestId("enso-source")).toContainText("Source: NOAA CPC ONI");
});

test("months without ONI are hatched", async ({ page }) => {
  await overrideCalendar(page, (b) => {
    b.enso.months = b.enso.months.filter((m) => !m.ym.startsWith("2010-"));
  });
  await page.goto("/");
  const seg = page.locator('.enso-seg[data-enso-ym="2010-03"]');
  await expect(seg).toHaveAttribute("data-phase", "none");
  await expect(seg).toHaveAttribute("aria-label", /sin dato de ONI/);
  expect(await seg.evaluate((el) => getComputedStyle(el).backgroundImage)).toContain("repeating-linear-gradient");
});

test("enso null hides the strip and shows the note", async ({ page }) => {
  await overrideCalendar(page, (b) => {
    (b as unknown as { enso: null }).enso = null;
  });
  await page.goto("/");
  await expect(page.getByTestId("calendar-grid")).toBeVisible();
  await expect(page.getByTestId("enso-strip")).toHaveCount(0);
  await expect(page.getByTestId("enso-missing")).toHaveText("ENSO no disponible");
  await page.getByTestId("lang-en").click();
  await expect(page.getByTestId("enso-missing")).toHaveText("ENSO unavailable");
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await expect(page.getByTestId("season-enso-toggle")).toHaveCount(0);
});

test("dashboard: the ENSO toggle draws three phase medians and marks few years", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Tablero" }).click();
  const toggle = page.getByTestId("season-enso-toggle");
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  for (const ph of ["nino", "nina", "neutral"]) await expect(page.getByTestId(`season-phase-${ph}`)).toBeVisible();
  const few = enso.by_phase.filter((r) => r.n_years < 3).length;
  expect(few).toBeGreaterThan(0);
  await expect(page.locator('.d-phase-dot[data-few="true"]')).toHaveCount(few);
  await expect(page.locator('.d-phase-dot[data-few="true"] title').first()).toHaveText(/pocos años/);
  await toggle.click();
  await expect(page.getByTestId("season-phase-nino")).toHaveCount(0);
});

for (const theme of ["light", "dark"] as const) {
  test(`axe: no violations with the strip visible (${theme})`, async ({ page }) => {
    await page.goto("/");
    await page.getByTestId(`theme-${theme}`).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.getByTestId("enso-strip")).toBeVisible();
    const run = async () => (await new AxeBuilder({ page }).withTags(TAGS).analyze()).violations.map((v) => ({ id: v.id, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) }));
    expect(await run(), "map tab").toEqual([]);
    await page.getByRole("tab", { name: "Tablero" }).click();
    await page.getByTestId("season-enso-toggle").click();
    await expect(page.getByTestId("season-phase-nina")).toBeVisible();
    expect(await run(), "dashboard by phase").toEqual([]);
  });
}
