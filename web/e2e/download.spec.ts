import { readFileSync } from "node:fs";
import type { Download } from "@playwright/test";
import { expect, fixtureResponse, test } from "./api";

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
});

// Header rows of backend/src/firecal/stages/calendar/export.py: the matrix columns (matrix.py) and, for the
// calendar and cells kinds, the provenance columns; DETECTION_COLUMNS + source for raw detections.
// backend/tests/test_web_export_fixtures.py ties these lists to export.py.
const CALENDAR_HEADER = [
  "year", "month", "modis_reported", "viirs_reported", "modis_eq", "viirs_eq", "cells", "modis_eq_status",
  "viirs_eq_status", "source", "period", "method", "calibration_version",
]; // prettier-ignore
const DETECTIONS_HEADER = [
  "acq_datetime", "acq_date", "sensor", "satellite", "product", "daynight", "latitude", "longitude",
  "confidence_pct", "confidence_class", "frp", "type", "version", "source",
]; // prettier-ignore

async function header(download: Download): Promise<string[]> {
  const text = readFileSync((await download.path())!, "utf8");
  return text.split("\n")[0].split(",");
}

test("calendar CSV: downloads with the file name of the server and the export.py columns", async ({ page, api }) => {
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("download-calendar").click()]);
  expect(download.suggestedFilename()).toBe("firecal_calendar_viirs_eq_2005-01_2016-12.csv");
  expect(await header(download)).toEqual(CALENDAR_HEADER);
  const text = readFileSync((await download.path())!, "utf8");
  expect(text).toBe(fixtureResponse("export-calendar-cordoba-viirs_eq.csv").body);
  expect(text).toContain("SYNTHETIC");
  expect(api.to("/export.csv").at(-1)!.body).toEqual({ preset: "cordoba", scale: "viirs_eq", kind: "calendar" });
});

test("hot-spot CSV: the server has no raw detections (404), so the button goes away with a message", async ({ page, api }) => {
  const button = page.getByTestId("download-detections");
  await expect(button).toBeVisible();
  let downloaded = false;
  page.on("download", () => (downloaded = true));
  await button.click();
  await expect(page.getByTestId("download-message")).toContainText("Los focos individuales no están disponibles");
  await expect(button).toHaveCount(0);
  await expect(page.getByTestId("download-calendar")).toBeEnabled();
  expect(api.to("/export.csv").at(-1)!.body.kind).toBe("detections");
  expect(downloaded).toBe(false);
});

test("hot-spot CSV: a server with raw detections downloads the DETECTION_COLUMNS file", async ({ page }) => {
  const available = fixtureResponse("export-detections-available.csv");
  await page.route(
    (url) => url.pathname === "/api/export.csv",
    (route) => route.fulfill(available),
  );
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("download-detections").click()]);
  expect(download.suggestedFilename()).toBe("firecal_detections_viirs_eq_2005-01_2016-12.csv");
  expect(await header(download)).toEqual(DETECTIONS_HEADER);
  await expect(page.getByTestId("download-detections")).toBeVisible();
});

test("a failed export shows an error and keeps both buttons", async ({ page }) => {
  await page.route(
    (url) => url.pathname === "/api/export.csv",
    (route) => route.fulfill({ status: 500, json: { detail: "boom" } }),
  );
  await page.getByTestId("download-calendar").click();
  await expect(page.getByTestId("download-message")).toHaveText("No se pudo descargar el archivo.");
  await expect(page.getByTestId("download-detections")).toBeVisible();
});
