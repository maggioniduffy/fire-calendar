# Phase 7 — Publication

Status: active · Depends on: 4 · Refs: `docs/architecture.md` (Static publishing)

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA7.1 | README in English: problem, harmonization method with its error table, sources and licenses, how to run | Sonnet | Reviewed by Opus. Done ✅ (2026-11-15; error tables copied from `reports/02/baselines.md`; FIRMS/CPC terms and CARTO attribution text marked unverified; no code license yet) |
| SA7.2 | Deployed demo: static web + JSON precomputed per province and department on R2 | Sonnet | Public URL responds and shows Córdoba |
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
