# Phase 1 — FIRMS data

Status: active · Depends on: 0 (SA0.8) · Refs: `docs/architecture.md`, `docs/research/data-sources.md`

## Goal

MODIS and VIIRS hot spots 2000–today, filtered and in a lightweight Argentina grid so any area of the country can
be queried.

## Data

MODIS C6.1 (Terra from 11/2000, Aqua from 7/2002), VIIRS 375 m (S-NPP from 1/2012, NOAA-20, NOAA-21).
Standard per-country archive for the history (URL in `docs/research/data-sources.md`; S-NPP ends on 2026-11-02);
NRT through the area API for the months the standard archive does not cover yet, only if `FIRMS_MAP_KEY` is set.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA1.1 | Idempotent download of the yearly Argentina CSVs (MODIS, VIIRS S-NPP, VIIRS NOAA-20) | Sonnet writes, opencode runs | Files with checksum + idempotency unit. Done ✅ (run 2026-11-14: 48 files, 487 MB) |
| SA1.2 | Ingestion to Parquet with a single schema (sensor, satellite, date/time, day/night, lat, lon, confidence, FRP, type) | Sonnet | Unit on synthetic rows of each sensor. Done ✅ (`satellite` codes verified in the real files) |
| SA1.3 | Filters: only `type` vegetation (no fixed sources or offshore); MODIS confidence ≥ threshold, VIIRS nominal or high; configurable threshold | Sonnet | Unit: each filter drops what is expected. Done ✅ |
| SA1.4 | Argentina grid: count per cell (0.1° and 0.25°) × day × sensor × day/night | Sonnet writes, opencode runs | Parquet partitioned by year + aggregation unit. Done ✅ (0.1° and 0.25°, run 2026-11-14) |
| SA1.5 | Raw Argentina detections in DuckDB for queries and CSV (deferred: the CSV comes from the Parquet) | Sonnet | Polygon query < 2 s in Córdoba |
| SA1.6 | NRT ingestion of the months without standard data through the area API (only with `FIRMS_MAP_KEY`) | Sonnet | One run brings the latest available day. Done ✅ (2026-11-15; `firecal firms area` / `area-ingest` / `clip-check` / `nrt-mask` / `completeness`: SP 2026 to SP end and NRT to 2026-11-15 for MODIS, S-NPP, NOAA-20, NOAA-21 (+ NOAA-21 SP from 2023-03), clipped to the ADM2 union; clip check P7 passes (worst 0.16 % unmatched, [reports/01/SA1.6_clip.md](../reports/01/SA1.6_clip.md)); grid takes country-SP > API-SP > NRT per satellite-month, never summed; NRT static-source mask accepted for both families ([reports/01/SA1.6_nrt_mask.md](../reports/01/SA1.6_nrt_mask.md)); 2026 completeness: Terra partial May–Jul and Oct, S-NPP partial Jul ([reports/01/SA1.6_completeness.md](../reports/01/SA1.6_completeness.md)); NOAA-21 clip unverified (no country files)) |
| SA1.7 | Data profile: hot spots per year, sensor and region; gaps | opencode | `reports/01/SA1.7.md`. Done ✅ (no 2026 in standard; MODIS `version` changes in 2018 and 2023, to review in phase 2) |

## Open

- Resolved on 2026-11-14: Argentina coverage (487 MB measured). Other countries later, with the same downloader.
