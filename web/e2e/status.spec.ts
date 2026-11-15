import { expect, setPreference, test } from "./api";

// SYNTHETIC fixtures (backend/scripts/web_fixtures.py): 2016-11 and 2016-12 are provisional (NRT), every month of
// 2016 is flagged MODIS drift, earlier months are standard country SP. Nothing here is real data.
const PROV = "2016-11";
const STANDARD = "2010-06";
// The last rows of the grid sit under the ENSO strip at the default viewport (pointer events are intercepted; a
// layout quirk of the calendar card, not of this feature), so provisional months are reached with the keyboard.
const choose = async (page: import("@playwright/test").Page, ym: string) => {
  await cell(page, ym).focus();
  await page.keyboard.press("Enter");
};
const cell = (page: import("@playwright/test").Page, ym: string) => page.locator(`[data-ym="${ym}"]`);

const TEXT = {
  es: {
    tip: "Provisorio (NRT, tiempo casi real): puede cambiar cuando llegue el procesamiento estándar",
    level: "tiempo casi real (NRT)",
    badge: "Provisorio",
    legend: "Mes provisorio (NRT)",
    drift: "MODIS observado durante deriva orbital (causa sin verificar)",
    chart: "Mes provisorio (punto hueco)",
    std: "procesamiento estándar (archivos por país de FIRMS)",
  },
  en: {
    tip: "Provisional (NRT, near real time): may change when standard processing arrives",
    level: "near real time (NRT)",
    badge: "Provisional",
    legend: "Provisional month (NRT)",
    drift: "MODIS observed during orbit drift (unverified cause)",
    chart: "Provisional month (hollow point)",
    std: "standard processing (FIRMS per-country files)",
  },
} as const;

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
  await expect(page.getByTestId("calendar-grid")).toBeVisible();
});

for (const lang of ["es", "en"] as const) {
  test.describe(`status badges (${lang})`, () => {
    const x = TEXT[lang];
    test.beforeEach(async ({ page }) => {
      if (lang === "en") await setPreference(page, "lang-en");
    });

    test("calendar: provisional cell is marked, its tooltip and the legend say so; a standard month does not", async ({ page }) => {
      await expect(cell(page, PROV)).toHaveAttribute("data-provisional", "true");
      await expect(cell(page, PROV)).toHaveClass(/provisional/);
      await expect(cell(page, STANDARD)).toHaveAttribute("data-provisional", "false");
      await expect(page.getByTestId("legend-provisional")).toContainText(x.legend);

      await cell(page, PROV).focus();
      const tip = page.getByTestId("calendar-tooltip");
      await expect(page.getByTestId("tip-provisional")).toContainText(x.tip);
      await expect(page.getByTestId("tip-source-level")).toHaveText(x.level);
      // VIIRS-eq view: the MODIS drift note is not shown.
      await expect(page.getByTestId("tip-drift")).toHaveCount(0);
      await expect(page.getByTestId("legend-drift")).toHaveCount(0);

      await cell(page, STANDARD).focus();
      await expect(tip).toContainText("2010");
      await expect(page.getByTestId("tip-provisional")).toHaveCount(0);
      await expect(page.getByTestId("tip-drift")).toHaveCount(0);
    });

    test("MODIS-eq view: drift is noted in the tooltip and the legend, not as a badge", async ({ page }) => {
      await page.getByTestId("series-modis_eq").click();
      await expect(page.getByTestId("legend-drift")).toContainText(x.drift);
      await cell(page, "2016-05").hover();
      await expect(page.getByTestId("tip-drift")).toHaveText(x.drift);
      await expect(page.getByTestId("tip-provisional")).toHaveCount(0);
      await page.mouse.move(0, 0);
      await cell(page, STANDARD).hover();
      await expect(page.getByTestId("calendar-tooltip")).toBeVisible();
      await expect(page.getByTestId("tip-drift")).toHaveCount(0);
    });

    test("inspector: badge, note and source level for a provisional month, none for a standard one", async ({ page }) => {
      await choose(page, PROV);
      await expect(page.getByTestId("provisional-badge")).toHaveText(x.badge);
      await expect(page.getByTestId("provisional-note")).toContainText(lang === "es" ? "Provisional: algún satélite" : "Provisional: a satellite");
      await expect(page.getByTestId("fig-source-level")).toHaveText(x.level);
      await expect(page.getByTestId("drift-note")).toHaveCount(0);

      await cell(page, STANDARD).click();
      await expect(page.getByTestId("fig-source-level")).toHaveText(x.std);
      await expect(page.getByTestId("provisional-badge")).toHaveCount(0);
      await expect(page.getByTestId("provisional-note")).toHaveCount(0);
    });

    test("dashboard monthly chart: provisional months are hollow points with a legend entry", async ({ page }) => {
      await page.getByRole("tab", { name: lang === "es" ? "Tablero" : "Dashboard" }).click();
      const chart = page.getByTestId("chart-monthly");
      await expect(chart).toBeVisible();
      await expect(chart.locator("circle.d-point-provisional")).toHaveCount(2);
      await expect(chart.locator(`circle[data-month="${PROV}"]`)).toHaveCount(1);
      await expect(chart.locator(`circle[data-month="${STANDARD}"]`)).toHaveCount(0);
      await expect(chart).toContainText(x.chart);
    });
  });
}
