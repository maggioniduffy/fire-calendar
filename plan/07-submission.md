# Phase 7 — Publication

Status: active · Depends on: 4 · Refs: `docs/architecture.md` (Static publishing)

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA7.1 | README in English: problem, harmonization method with its error table, sources and licenses, how to run | Sonnet | Reviewed by Opus. Done ✅ (2026-11-15; error tables copied from `reports/02/baselines.md`; FIRMS/CPC terms and CARTO attribution text marked unverified; no code license yet) |
| SA7.2 | Deployed demo: static web + JSON precomputed per province and department on Cloudflare Pages (R2 dropped: one Pages project serves web and data) | Sonnet | Public URL responds and shows Córdoba. Built and tested locally; deploy pending (`deploy-demo` workflow) |
| SA7.3 | (deferred) Video and slides | user, with Opus draft | — |
| SA7.4 | (deferred) Project page on the Space Apps site: not competing | user | — |

## SA7.2 design (static export)

Online there is no API (`docs/architecture.md`, Static publishing). The static build reads precomputed JSON
under `VITE_DATA_URL`; without it the app keeps using `/api` exactly as today.

- **Areas.** Provinces (ADM1) and departments (ADM2) from an open boundary source (source and license recorded in
  `docs/research/data-sources.md` and in the export manifest). Each area is a `PolygonArea` (multipolygon allowed),
  simplified once at export; the same simplified geometry is used to compute the series and to draw the outline,
  so the published cells and totals match the outline. Membership is the backend rule: 0.1° cell centers inside.
- **Layout** (paths under the data root, gzip-friendly JSON):
  - `static/manifest.json`: export version, calibration, layer period, boundary source + license, generated at.
  - `static/areas.json`: list of `{id, kind: province|department, name, province_id, bbox, area_km2}`.
  - `static/areas/{id}.json`: outline (exterior rings) and the cell ids of the area.
  - `static/calendar/{id}/{scale}.json`: the `/calendar` payload.
  - `static/stats/{id}/{scale}.json`: `/stats` for every reference month, as shared fields + `by_ref[YYYY-MM]`
    (climatology, anomaly, key figures); the client rebuilds the `StatsPayload`.
  - `static/cells/{scale}/{YYYY-MM}.json`: national cells of one month; the client keeps those of the area.
  - `static/export/{id}/{scale}.csv`: the calendar CSV (`kind=calendar`); cells and detections CSV are local only.
- **Web, static mode** (`VITE_DATA_URL` set): area picker = province select + department select; circle, radius
  and polygon drawing hidden with a note (ES/EN) that custom areas need the local app; "Use my location" picks the
  province that contains the point (no point leaves the browser); raw detections are not requested. Default area:
  Córdoba province (official boundary, replacing the approximate preset in static mode only).
- **Hosting.** Cloudflare R2 public bucket (or another static host) for data, and the built `web/dist` on a static
  host. Credentials come from the environment (`R2_*`), never from the repo. Nothing is published before the user
  approves; the export and the static build are tested locally first (served from disk with a static server, e2e
  against it).

### SA7.2 contract (v1)

Boundaries: geoBoundaries gbOpen ARG ADM2 simplified (source "Instituto Geografico Nacional and UNHCR, OCHA
ROLAC", CC BY 3.0 IGO; attribution "Administrative boundaries courtesy of geoBoundaries.org"), download pinned to
a commit and recorded with its sha256. ADM2 has no province field: each department is assigned to a province by
point-on-surface inside the geoBoundaries ADM1 polygons (used for that lookup only, never published; its
"La Roja" is La Rioja, and Entre Ríos is missing, so unassigned departments inside Entre Ríos' bbox go to it;
anything else unassigned is a build error). Province geometry = dissolve of its departments. Areas whose
representative point is outside the data domain (`ARG_BBOX`) are dropped and geometries are clipped to it.
Areas the calendar rejects (too small for the 0.1° grid) are skipped and listed in the manifest.

IDs: provinces `p-<slug>`, departments `d-<province slug>-<slug>` (ASCII slug, `-2` suffix on clashes). Córdoba
province is `p-cordoba` and is the default area. Scales: `viirs_eq`, `modis_eq` ("reported" uses `viirs_eq`).

- `manifest.json`: `{version: 1, generated_at, layer, calibration_version, period: {start, end}, scales,
  default_area, boundaries: {source, license, attribution, url, sha256}, skipped: [{name, reason}]}`
- `areas.json`: `{areas: [{id, kind: "province"|"department", name, province_id|null, bbox, area_km2,
  n_cells}]}` (`bbox` = `[lat_min, lat_max, lon_min, lon_max]`, as the API).
- `areas/{id}.json`: `{id, name, kind, outline, cells}`; `outline` as `CellsPayload.outline` (exterior rings,
  `[lon, lat]`), `cells` = `[[cell_lat, cell_lon], ...]` of the cells whose centers are inside.
- `calendar/{id}/{scale}.json`: exactly the `POST /calendar` payload for `{area: <geometry>, scale}`.
- `stats/{id}/{scale}.json`: `{meta, area, n_cells, period, scale, default_ref, climatology_by_year: {YYYY:
  climatology}, by_ref: {YYYY-MM: {anomaly, key_figures}}}`; `POST /stats` with `ref` = `{...shared,
  climatology: climatology_by_year[ref year], anomaly, key_figures}` (the climatology excludes the reference
  year, so it depends only on that year). Without `ref` the API answers `default_ref` (labels unchosen).
- `cells/{scale}/{YYYY-MM}.json`: `{month, scale, cells: [[cell_lat, cell_lon, value, estimated 0|1], ...]}` for
  all of Argentina, value > 0; the client keeps the area's cells and applies the view window.
- `detections/{YYYY-MM}/{lat0}_{lon0}.json`: raw filtered NASA FIRMS detections in 5° tiles by default, keyed
  by `floor(latitude / tile_deg) * tile_deg` and `floor(longitude / tile_deg) * tile_deg`; rows are `[lat, lon,
  acq_date, acq_time, sensor, frp, daynight, confidence]`. `detections/{YYYY-MM}/index.json` is
  `{month, tile_deg, tiles: {"<lat0>_<lon0>": n_points}}`; months without raw detections have no directory.
  The default 5° size reduces the estimated 2000–2026 deployment from about 73,000 files at 1° to below
  Cloudflare Pages' 20,000-file per-deployment limit (limit unverified).
- `manifest.json` adds `detections: {available, fields, tile_deg: 5, months, source, note}`. This is additive
  within version 1; static clients return 404 for detections when `available` is false.
- `export/{id}/{scale}.csv`: the `POST /export.csv` body with `kind=calendar`.
