# fire-calendar

Harmonized MODIS + VIIRS fire calendar for Argentina. Built around the CONAE challenge of NASA Space Apps 2026,
"Harmonization of MODIS and VIIRS Hot Spots": one fire-activity series from 2000 to today in two scales
(MODIS-equivalent and VIIRS-equivalent), a year × month calendar, anomalies against the climatology, ENSO phase
context and CSV export.

Status: planning done, implementation starting. See [plan.md](plan.md) (in Spanish).

- Data: NASA FIRMS per-country archives (MODIS C6.1, VIIRS 375 m S-NPP and NOAA-20) and the FIRMS area API for
  recent months. Sources: [docs/research/data-sources.md](docs/research/data-sources.md).
- Not an alert system: everything is retrospective.
- Author: Faustino Maggioni Duffy. Architecture borrowed from
  [clima-ideas](https://github.com/maggioniduffy/clima-ideas).
