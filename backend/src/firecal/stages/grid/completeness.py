"""SA1.6 completeness per satellite x month (pre-registration P8 and Revision 1 in plan/02-harmonization.md).

A satellite-month is `complete` when its source window covers the whole month, the month is closed and the
number of days with at least one detection (before filters, clipped to Argentina) is at least 90 % of the
median for that calendar month and satellite over a reference period (VIIRS 2012-2025, MODIS 2003-2025; the
first partial month of each record is left out of the reference). A closed month that fails is `partial`;
the month in progress is `in_progress` and never complete.

Only months >= 2026-01 are gated; earlier months are a diagnostic table. The source of a month is the one the
grid uses (country-sp > api-sp > nrt, never summed).
"""

import calendar
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.paths import interim_dir
from firecal.stages.grid.grid import LEVELS, level_files

FAMILY_OF = {"terra": "modis", "aqua": "modis", "snpp": "viirs", "noaa20": "viirs", "noaa21": "viirs"}
REF_YEARS = {"modis": (2003, 2025), "viirs": (2012, 2025)}
GATE_FROM = (2026, 1)
THRESHOLD = 0.9
# First (partial) month of each record that starts mid-month, as in harmonize.regions.PARTIAL_MONTHS.
KNOWN_PARTIAL = {("aqua", 2002, 7), ("snpp", 2012, 1), ("noaa20", 2018, 4)}
COMPLETENESS_FILE = "completeness.parquet"


def presence(detections: Path) -> pd.DataFrame:
    """Rows per (product, level, satellite, acq_date), before any filter."""
    parts = []
    for _year, files in sorted(level_files(detections).items()):
        for level, f in files:
            product = (f.parent.parent if level == "country-sp" else f.parent.parent.parent).name.split("=")[
                1
            ]
            d = pq.read_table(f, columns=["satellite", "acq_date"]).to_pandas()
            g = d.groupby(["satellite", "acq_date"]).size().rename("rows").reset_index()
            g["product"], g["level"] = product, level
            parts.append(g)
    if not parts:
        return pd.DataFrame(columns=["satellite", "acq_date", "rows", "product", "level"])
    out = pd.concat(parts, ignore_index=True)
    out["acq_date"] = pd.to_datetime(out["acq_date"])
    return out


def manifest_windows(manifest: Path) -> dict[tuple[str, str], date]:
    """(product, level) -> last day covered by non-error chunks of the area API download."""
    from firecal.io.firms_area import SOURCES

    if not manifest.exists():
        return {}
    ends: dict[tuple[str, str], date] = {}
    for r in json.loads(manifest.read_text())["records"]:
        src = SOURCES.get(r["source"])
        if src is None or r["status"] == "error":
            continue
        end = date.fromisoformat(r["start"]) + timedelta(days=r["days"] - 1)
        key = (src.product, src.level)
        ends[key] = max(ends.get(key, end), end)
    return ends


def window_ends(pres: pd.DataFrame, manifest: Path | None) -> dict[tuple[str, str], date]:
    """(satellite, level) -> end of the source window.

    country-sp: 31 December of the last country file year; api-sp / nrt: last day covered by the download
    manifest, or the last detection date when there is no manifest entry.
    """
    api = manifest_windows(manifest) if manifest else {}
    out: dict[tuple[str, str], date] = {}
    for (sat, level, product), g in pres.groupby(["satellite", "level", "product"]):
        last = g["acq_date"].max().date()
        end = date(last.year, 12, 31)
        if level != "country-sp":
            end = max(api.get((product, level), last), last)
        key = (sat, level)
        out[key] = max(out.get(key, end), end)
    return out


def month_table(pres: pd.DataFrame) -> pd.DataFrame:
    """Chosen level and days with detections per satellite x month."""
    d = pres.copy()
    d["ym"] = d["acq_date"].dt.year * 12 + d["acq_date"].dt.month - 1
    d["rank"] = d["level"].map({lv: i for i, lv in enumerate(LEVELS)})
    best = d.groupby(["satellite", "ym"])["rank"].transform("min")
    d = d[d["rank"] == best]
    return (
        d.groupby(["satellite", "ym"])
        .agg(
            level=("level", "first"),
            days=("acq_date", "nunique"),
            rows=("rows", "sum"),
            first_date=("acq_date", "min"),
        )
        .reset_index()
    )


def completeness_table(
    pres: pd.DataFrame, asof: date, manifest: Path | None = None, gate_from: tuple[int, int] = GATE_FROM
) -> pd.DataFrame:
    months = month_table(pres)
    windows = window_ends(pres, manifest)
    first_obs = pres.groupby("satellite")["acq_date"].min()
    rows = []
    for sat, g in months.groupby("satellite"):
        fam = FAMILY_OF[sat]
        y0, y1 = REF_YEARS[fam]
        first_ym = int(g["ym"].min())
        rec_start = first_obs[sat]
        # first month of the record is left out of the reference when it starts mid-month
        partial_first = {(sat, rec_start.year, rec_start.month)} if rec_start.day > 1 else set()
        by_ym = g.set_index("ym")
        ref = [
            (ym % 12, int(by_ym.loc[ym, "days"]))
            for ym in by_ym.index
            if y0 <= ym // 12 <= y1 and (sat, ym // 12, ym % 12 + 1) not in KNOWN_PARTIAL | partial_first
        ]
        refdf = pd.DataFrame(ref, columns=["m", "days"])
        med = refdf.groupby("m")["days"].agg(["median", "size"]) if len(refdf) else pd.DataFrame()
        for ym in range(first_ym, asof.year * 12 + asof.month):
            yr, m0 = divmod(ym, 12)
            month_end = date(yr, m0 + 1, calendar.monthrange(yr, m0 + 1)[1])
            hit = by_ym.loc[ym] if ym in by_ym.index else None
            level = None if hit is None else hit["level"]
            days = 0 if hit is None else int(hit["days"])
            wend = windows.get((sat, level)) if level else None
            ref_med = float(med.loc[m0, "median"]) if m0 in med.index else float("nan")
            ref_n = int(med.loc[m0, "size"]) if m0 in med.index else 0
            thr = THRESHOLD * ref_med
            if month_end > asof:
                status = "in_progress"
            elif wend is None or wend < month_end or not days >= thr:
                status = "partial"
            else:
                status = "complete"
            rows.append(
                {
                    "satellite": sat,
                    "month": f"{yr}-{m0 + 1:02d}",
                    "ym": ym,
                    "level": level,
                    "window_end": wend,
                    "days_with_detections": days,
                    "days_in_month": month_end.day,
                    "rows": 0 if hit is None else int(hit["rows"]),
                    "ref_median_days": ref_med,
                    "ref_n_years": ref_n,
                    "threshold_days": thr,
                    "status": status,
                    "gated": (yr, m0 + 1) >= gate_from,
                }
            )
    return pd.DataFrame(rows).sort_values(["satellite", "ym"], ignore_index=True)


def write_table(table: pd.DataFrame, asof: date, out: Path | None = None) -> Path:
    out = out or interim_dir() / "firms" / COMPLETENESS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    t = table.copy()
    t["window_end"] = pd.to_datetime(t["window_end"]).dt.date
    tab = pa.Table.from_pandas(t, preserve_index=False)
    tab = tab.replace_schema_metadata(
        {**(tab.schema.metadata or {}), b"asof": asof.isoformat().encode(), b"rule": b"P8 + Revision 1"}
    )
    tmp = out.with_suffix(".tmp")
    pq.write_table(tab, tmp)
    tmp.replace(out)
    return out


def render_report(table: pd.DataFrame, asof: date) -> str:
    gated = table[table["gated"]]
    old = table[~table["gated"]]
    L = [
        "# SA1.6 completeness per satellite x month (P8 + Revision 1)",
        "",
        "Generated by `firecal firms completeness` (`firecal.stages.grid.completeness`); table in "
        f"`data/interim/firms/{COMPLETENESS_FILE}`. As of {asof.isoformat()}.",
        "",
        "Source: FIRMS detections under data/interim/firms/detections (country files 2000-2025, area API SP "
        "and NRT, clipped to Argentina); source windows from the area download manifest. Days with at least "
        "one detection are counted before any filter on the rows of the source the grid uses for that month "
        "(country-sp > api-sp > nrt, never summed).",
        "",
        f"Rule: `complete` = month closed, source window end >= last day of the month and days with "
        f"detections >= {int(100 * THRESHOLD)} % of the median for that calendar month and satellite "
        "over the "
        f"reference period (VIIRS {REF_YEARS['viirs'][0]}-{REF_YEARS['viirs'][1]}, MODIS "
        f"{REF_YEARS['modis'][0]}-{REF_YEARS['modis'][1]}; the first partial month of each record excluded). "
        "A closed month failing the rule is `partial`; the month in progress is `in_progress`, never "
        f"complete. Only months >= {GATE_FROM[0]}-{GATE_FROM[1]:02d} are gated; earlier months are a "
        "diagnostic. NOAA-21 has no reference before 2023-03, so its reference is 2-3 years per calendar "
        "month (thin; see `ref_n`) and its SP comes from the area API only (no country files).",
        "",
        "## Gated months (>= 2026-01)",
        "",
        "| satellite | month | level | window end | days | threshold (90 % of median) "
        "| median (n yrs) | status |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for r in gated.itertuples():
        L.append(
            f"| {r.satellite} | {r.month} | {r.level or '-'} | {r.window_end or '-'} "
            f"| {r.days_with_detections}/{r.days_in_month} | {r.threshold_days:.1f} "
            f"| {r.ref_median_days:.1f} ({r.ref_n_years}) | {r.status} |"
        )
    L += ["", "## Diagnostic: months before 2026-01", ""]
    closed = old
    L.append(
        f"{len(closed)} satellite-months; {int((closed['status'] == 'partial').sum())} below the rule. "
        "These flags change no existing series or fit."
    )
    flagged = closed[closed["status"] == "partial"]
    if len(flagged):
        L += [
            "",
            "| satellite | month | level | days | threshold | median (n yrs) |",
            "|---|---|---|---:|---:|---:|",
        ]
        for r in flagged.itertuples():
            L.append(
                f"| {r.satellite} | {r.month} | {r.level or '-'} "
                f"| {r.days_with_detections}/{r.days_in_month} "
                f"| {r.threshold_days:.1f} | {r.ref_median_days:.1f} ({r.ref_n_years}) |"
            )
    return "\n".join(L) + "\n"


def build_completeness(
    detections: Path | None = None,
    manifest: Path | None = None,
    out: Path | None = None,
    report: Path | None = None,
    asof: date | None = None,
) -> pd.DataFrame:
    from firecal.paths import raw_dir

    detections = detections or interim_dir() / "firms" / "detections"
    manifest = manifest or raw_dir() / "firms_area" / "manifest.json"
    asof = asof or date.today()
    table = completeness_table(presence(detections), asof, manifest)
    write_table(table, asof, out)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(table, asof))
    return table
