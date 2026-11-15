import { expect, setPreference, test } from "./api";

const OUT = "/tmp/claude-1000/-home-faustino-Desktop-Documents-code-fire-calendar/27e795f8-01c5-4621-8ca1-6ed0eb635308/scratchpad/shots";

test("SA4.14 period visual snapshots", async ({ page, api }) => {
  await page.setViewportSize({ width: 1440, height: 720 });
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
  await expect(page.getByTestId("map-month")).toHaveText("2016-12");

  await page.locator('[data-ym="2016-10"]').click({ modifiers: ["Shift"] });
  await expect(page.getByTestId("map-month")).toContainText("2016-10 – 2016-12 · 3 meses");
  await expect.poll(() => api.to("/cells").some((r) => r.body.start === "2016-10")).toBe(true);
  await page.mouse.move(1090, 350);
  await page.screenshot({ path: `${OUT}/T5-map-range-light.png` });
  await setPreference(page, "theme-dark");
  await page.screenshot({ path: `${OUT}/T5-map-range-dark.png` });

  await page.getByRole("button", { name: "Temporada" }).click();
  await expect(page.getByTestId("map-month")).toContainText("ago–oct");
  await expect.poll(() => api.to("/cells").some((r) => Array.isArray(r.body.months))).toBe(true);
  await page.screenshot({ path: `${OUT}/T5-map-season-dark.png` });
  await setPreference(page, "theme-light");
  await page.screenshot({ path: `${OUT}/T5-map-season-light.png` });

  const controls = page.getByTestId("map-period-controls");
  await controls.scrollIntoViewIfNeeded();
  await expect(controls).toBeVisible();
  await page.screenshot({ path: `${OUT}/T5-left-panel-light.png` });
  await setPreference(page, "theme-dark");
  await page.screenshot({ path: `${OUT}/T5-left-panel-dark.png` });
});
