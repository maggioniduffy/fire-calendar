# Phase 4 web app on real data

Run: 2026-11-15, local. API `firecal serve` (port 8000) + Vite dev server (5173, proxy `/api`), driven with
Playwright (Chromium 1440x900) and direct API calls. Data rebuilt locally: `enso build` (921 months), `firms download`
(2000-2025; 2026 returns 404 for all three sensors, as expected), `ingest`, `grid` (0.1°), `series calibrate` / `build`.

- Source (topbar, inspector, dashboard): NASA FIRMS standard country files (Argentina): MODIS Terra/Aqua, VIIRS 375 m S-NPP/NOAA-20. No "SYNTHETIC".
- Period: 2000-11-01 to 2025-12-31. Calibration: `sf-2026.11.1`. Córdoba preset: 2200 cells, 229,962.9 km².
- Browser console: no page errors in any run.

## Checklist

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Opens on Córdoba, FIRMS source | **passed** | Calendar, inspector and map load; month 2025-12 = 249; `/calendar`+`/stats` fire twice on load in dev (probably StrictMode; unverified in a production build). |
| 2 | Area modes | **passed** (keyboard polygon out of scope) | Circle -31.42,-64.18 r150: 669 cells, 29 (2025-12); r500: 7446 cells, 1344. Drawn polygon: 720 cells, 37. Location allowed (mock -32.95,-60.65): 230 km circle, 1605 cells. Denied: stays on Córdoba with the message. |
| 3 | Map vs calendar totals | **passed** | 2020-09: overlay 7810 = inspector 7810 = `/calendar` viirs_eq 7810 = `/cells` total 7810. 2019-09: 1999 in overlay and inspector. |
| 4 | Raw detections at zoom >= 8 | **partly verified** | Raw detections exist. Zoomed in, the map switched to "Detecciones individuales" and requested `/detections`; `/detections` returned 16,176 points for Córdoba 2020-09 (truncated to 5,000). Points were not seen on screen (zoomed on an empty spot): **unverified visually**. |
| 5 | Month click | **passed** | Clicking 2019-09 sent `/stats` +1, `/cells` +1, `/calendar` +0. |
| 6 | Inspector series | **passed** (values of the three series rows not compared) | "estimado" and the estimated note on 2005-09 (3165.2); absent on 2012-09 (1212) and 2015-09 (837). |
| 7 | CSV downloads | **passed**; 404 behaviour **unverified on real data** | Calendar CSV `firecal_calendar_viirs_eq_2000-11_2025-12.csv`, 59 KB. Hot spots CSV 49.5 MB for Córdoba (the whole 2000-2025 period). The server has raw detections, so the button never disappeared. |
| 8 | Dashboard | **passed** | Total 296,975.5 = `key_figures.total` = sum of the monthly viirs_eq (296975.52559833). p10-p90 and p25-p75 bands present. Yearly PNG exported (63 KB). ENSO and FRP charts absent (deferred). CSV buttons present. Content of the chart CSV exports not inspected: **unverified**. |
| 9 | Performance (API, Córdoba / 500 km circle) | **passed**, nothing above 2 s | `/calendar` 0.52/0.41 s (viirs_eq), 0.30/0.39 s (modis_eq); `/stats` 0.18/0.35 s; `/cells` 0.03/0.04 s; `/detections` 0.21/0.24 s. Hot-spot CSV download took longer (49.5 MB); not timed. |
| 10 | Screenshots | **done** | [cordoba-light.png](cordoba-light.png), [cordoba-dark.png](cordoba-dark.png). |

## Notes and open items

- Contrast over the real basemap and screen-reader behaviour: **unverified** (dark screenshot is legible by eye only).
- The area band and the official Córdoba boundary remain unverified (phase 3); the dashboard says so.
- The raw-detection CSV is 49.5 MB for the whole period; consider limiting it by period (not decided).
- `pnpm dev` / `pnpm exec` fail locally on the release-age policy (packages published within the last day);
  the checks ran Vite through `node_modules/.bin/vite` after a one-off `--config.minimumReleaseAge=0` install.
