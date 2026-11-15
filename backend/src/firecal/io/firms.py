"""NASA FIRMS country archives: idempotent download (SA1.1) and ingest to one schema (SA1.2)."""

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import typer

from firecal.paths import REPO_ROOT, interim_dir, raw_dir

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/data/country"
# product -> first year with data; the file prefix equals the product name.
PRODUCTS = {"modis": 2000, "viirs-snpp": 2012, "viirs-jpss1": 2018}

DETECTION_SCHEMA = pa.schema(
    [
        ("sensor", pa.string()),
        ("satellite", pa.string()),
        ("product", pa.string()),
        ("acq_datetime", pa.timestamp("us", tz="UTC")),
        ("acq_date", pa.date32()),
        ("year", pa.int16()),
        ("daynight", pa.string()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("confidence_raw", pa.string()),
        ("confidence_pct", pa.int16()),
        ("confidence_class", pa.string()),
        ("frp", pa.float32()),
        ("brightness", pa.float32()),
        ("type", pa.int8()),
        ("version", pa.string()),
    ]
)


# ---------------------------------------------------------------- SA1.1 download


@dataclass
class DownloadResult:
    product: str
    year: int
    status: str  # downloaded | skipped | missing | error
    path: str | None = None
    sha256: str | None = None
    bytes: int | None = None
    detail: str | None = None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _fetch(client: httpx.Client, url: str, target: Path, retries: int, backoff: float, sleep) -> int | str:
    """Stream url to target atomically. Returns the HTTP status for 404/4xx, or "ok"."""
    tmp = target.with_name(target.name + ".part")
    last = ""
    for attempt in range(retries + 1):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        try:
            with client.stream("GET", url) as r:
                if r.status_code >= 500:
                    last = f"HTTP {r.status_code}"
                    continue
                if r.status_code != 200:
                    return r.status_code
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            os.replace(tmp, target)
            return "ok"
        except httpx.TransportError as e:
            last = f"{type(e).__name__}: {e}"
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError(last)


def download(
    products: Iterable[str] = tuple(PRODUCTS),
    years: Iterable[int] | None = None,
    country: str = "Argentina",
    dest: Path | None = None,
    client: httpx.Client | None = None,
    force: bool = False,
    refresh_years: Iterable[int] = (),
    retries: int = 3,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[DownloadResult]:
    dest = dest or raw_dir() / "firms"
    refresh = set(refresh_years)
    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=120)
    results: list[DownloadResult] = []
    try:
        for product in products:
            first = PRODUCTS[product]
            for year in sorted(years) if years is not None else range(first, date.today().year + 1):
                if year < first:
                    continue
                name = f"{product}_{year}_{country}.csv"
                target = dest / product / name
                sidecar = target.with_name(name + ".sha256")
                if not force and year not in refresh and target.exists() and sidecar.exists():
                    digest = sha256_file(target)
                    if digest == sidecar.read_text().strip():
                        results.append(
                            DownloadResult(
                                product, year, "skipped", str(target), digest, target.stat().st_size
                            )
                        )
                        continue
                target.parent.mkdir(parents=True, exist_ok=True)
                url = f"{BASE_URL}/{product}/{year}/{name}"
                try:
                    outcome = _fetch(client, url, target, retries, backoff, sleep)
                except RuntimeError as e:
                    results.append(DownloadResult(product, year, "error", detail=str(e)))
                    continue
                if outcome == "ok":
                    digest = sha256_file(target)
                    sidecar.write_text(digest + "\n")
                    results.append(
                        DownloadResult(
                            product, year, "downloaded", str(target), digest, target.stat().st_size
                        )
                    )
                elif outcome == 404:
                    results.append(DownloadResult(product, year, "missing", detail="HTTP 404"))
                else:
                    results.append(DownloadResult(product, year, "error", detail=f"HTTP {outcome}"))
    finally:
        if own_client:
            client.close()
    _write_manifest(dest, results)
    return results


def _write_manifest(dest: Path, results: list[DownloadResult]) -> None:
    """Merge this run into dest/downloads.json (keyed by product and year)."""
    manifest = dest / "downloads.json"
    old: list[dict] = []
    if manifest.exists():
        old = json.loads(manifest.read_text()).get("records", [])
    new = [asdict(r) for r in results]
    done = {(r["product"], r["year"]) for r in new}
    records = [r for r in old if (r["product"], r["year"]) not in done] + new
    records.sort(key=lambda r: (r["product"], r["year"]))
    dest.mkdir(parents=True, exist_ok=True)
    body = {"downloaded_at": datetime.now(UTC).isoformat(), "records": records}
    tmp = manifest.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2))
    tmp.replace(manifest)


# ---------------------------------------------------------------- SA1.2 ingest

# Verified 2026-11-14 on the Argentina files: MODIS `Terra`/`Aqua`; VIIRS `N` (S-NPP), `N20` (NOAA-20).
# VIIRS satellite is still taken from the product, which is unambiguous.
_MODIS_SATELLITE = {"terra": "terra", "t": "terra", "aqua": "aqua", "a": "aqua"}
# viirs-jpss2 (NOAA-21, `N21`) only comes from the area API (SA1.6), not from country files.
_VIIRS_SATELLITE = {"viirs-snpp": "snpp", "viirs-jpss1": "noaa20", "viirs-jpss2": "noaa21"}
_VIIRS_CLASS = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal", "h": "high", "high": "high"}


def _modis_class(pct: pd.Series) -> pd.Series:
    cls = pd.Series("nominal", index=pct.index, dtype="object")
    cls[pct < 30] = "low"
    cls[pct >= 80] = "high"
    return cls


def read_firms_csv(path: Path, product: str) -> pd.DataFrame:
    """Read one FIRMS country CSV into DETECTION_SCHEMA."""
    raw = pd.read_csv(path, dtype={"confidence": str, "satellite": str, "version": str, "daynight": str})
    modis = product == "modis"
    out = pd.DataFrame(index=raw.index)
    out["sensor"] = "modis" if modis else "viirs"
    if modis:
        sat = raw["satellite"].astype(str).str.strip().str.lower().map(_MODIS_SATELLITE)
        if sat.isna().any():
            bad = sorted(raw.loc[sat.isna(), "satellite"].astype(str).unique())
            raise ValueError(f"unknown MODIS satellite values: {bad}")
        out["satellite"] = sat
    else:
        out["satellite"] = _VIIRS_SATELLITE[product]
    out["product"] = product
    t = raw["acq_time"].astype(int)
    day = pd.to_datetime(raw["acq_date"], utc=True)
    out["acq_datetime"] = day + pd.to_timedelta(t // 100, unit="h") + pd.to_timedelta(t % 100, unit="m")
    out["acq_date"] = day.dt.date
    out["year"] = day.dt.year.astype("int16")
    out["daynight"] = raw["daynight"].str.strip().str.upper()
    out["latitude"] = raw["latitude"].astype("float64")
    out["longitude"] = raw["longitude"].astype("float64")
    out["confidence_raw"] = raw["confidence"].astype(str).str.strip()
    if modis:
        pct = pd.to_numeric(raw["confidence"]).astype("int16")
        out["confidence_pct"] = pct
        out["confidence_class"] = _modis_class(pct)
    else:
        out["confidence_pct"] = pd.array([pd.NA] * len(raw), dtype="Int16")
        out["confidence_class"] = out["confidence_raw"].str.lower().map(_VIIRS_CLASS)
        if out["confidence_class"].isna().any():
            raise ValueError("unknown VIIRS confidence values")
    out["frp"] = raw["frp"].astype("float32")
    out["brightness"] = raw["brightness" if modis else "bright_ti4"].astype("float32")
    out["type"] = raw["type"].astype("Int8") if "type" in raw else pd.array([pd.NA] * len(raw), dtype="Int8")
    out["version"] = raw["version"].astype(str)
    return out


def _source_sha(path: Path) -> str | None:
    meta = pq.read_schema(path).metadata or {}
    v = meta.get(b"source_sha256")
    return v.decode() if v else None


def ingest(
    raw: Path | None = None,
    out: Path | None = None,
    products: Iterable[str] = tuple(PRODUCTS),
) -> list[tuple[str, int, str]]:
    """CSV -> parquet, one file at a time. Returns (product, year, "written"|"skipped")."""
    raw = raw or raw_dir() / "firms"
    out = out or interim_dir() / "firms" / "detections"
    done = []
    for product in products:
        for csv in sorted((raw / product).glob(f"{product}_*_*.csv")):
            year = int(csv.stem.split("_")[1])
            dest = out / f"product={product}" / f"year={year}" / "part-0.parquet"
            digest = sha256_file(csv)
            if dest.exists() and dest.stat().st_mtime >= csv.stat().st_mtime and _source_sha(dest) == digest:
                done.append((product, year, "skipped"))
                continue
            table = pa.Table.from_pandas(
                read_firms_csv(csv, product), schema=DETECTION_SCHEMA, preserve_index=False
            )
            table = table.replace_schema_metadata(
                {**(table.schema.metadata or {}), b"source_sha256": digest.encode()}
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            pq.write_table(table, tmp)
            tmp.replace(dest)
            done.append((product, year, "written"))
    return done


# ---------------------------------------------------------------- CLI

firms_app = typer.Typer(no_args_is_help=True, help="NASA FIRMS: download, ingest, grid, profile.")


@firms_app.command("download")
def download_cmd(
    product: Annotated[list[str] | None, typer.Option("--product", help="Repeatable; default all.")] = None,
    year_from: int | None = None,
    year_to: int | None = None,
    force: bool = False,
    refresh_year: Annotated[list[int] | None, typer.Option("--refresh-year")] = None,
    country: str = "Argentina",
) -> None:
    """Download yearly country CSVs (idempotent)."""
    lo = year_from or min(PRODUCTS.values())
    hi = year_to or date.today().year
    results = download(
        products=product or tuple(PRODUCTS),
        years=range(lo, hi + 1),
        country=country,
        force=force,
        refresh_years=refresh_year or (),
    )
    for r in results:
        typer.echo(f"{r.product} {r.year} {r.status}" + (f" ({r.detail})" if r.detail else ""))


@firms_app.command("ingest")
def ingest_cmd(product: Annotated[list[str] | None, typer.Option("--product")] = None) -> None:
    """Convert raw CSVs to parquet in the unified schema."""
    for p, y, status in ingest(products=product or tuple(PRODUCTS)):
        typer.echo(f"{p} {y} {status}")


@firms_app.command("grid")
def grid_cmd(res: float = 0.1) -> None:
    """Filter detections and aggregate to a regular grid."""
    from firecal.stages.grid import build_grid

    for p in build_grid(res=res):
        typer.echo(str(p))


@firms_app.command("profile")
def profile_cmd(out: Path = REPO_ROOT / "reports" / "01" / "SA1.7.md") -> None:
    """Write the data profile report (SA1.7)."""
    from firecal.io.firms_profile import profile

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(profile())
    typer.echo(str(out))


# ---------------------------------------------------------------- SA1.6 area API (see firms_area.py)


@firms_app.command("area")
def area_cmd(
    source: Annotated[
        list[str] | None, typer.Option("--source", help="Repeatable: MODIS_SP, VIIRS_NOAA21 (both levels)...")
    ] = None,
    date_from: Annotated[
        str | None, typer.Option("--date-from", help="YYYY-MM-DD; replaces default ranges")
    ] = None,
    date_to: Annotated[str | None, typer.Option("--date-to", help="YYYY-MM-DD")] = None,
    clip_check: Annotated[
        bool, typer.Option("--clip-check", help="Add SP 2025 for MODIS, S-NPP, NOAA-20")
    ] = False,
    clip_check_only: Annotated[bool, typer.Option("--clip-check-only")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the plan, no chunk requests")] = False,
    workers: int = 4,
) -> None:
    """Download the area API in 5-day chunks over the Argentina bbox (needs FIRMS_MAP_KEY)."""
    from firecal.io import firms_area as fa

    key = fa.get_key()
    geom, _ = fa.load_argentina()
    bbox = fa.bbox_from_geometry(geom)
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        avail = fa.fetch_availability(client, key)
        plan = fa.build_plan(
            avail,
            date.today(),
            sources=source,
            date_from=date.fromisoformat(date_from) if date_from else None,
            date_to=date.fromisoformat(date_to) if date_to else None,
            clip_check=clip_check,
            clip_check_only=clip_check_only,
        )
        n = 0
        for it in plan:
            c = len(fa.chunk_ranges(it.start, it.end))
            n += c
            typer.echo(f"plan {it.source} {it.start}..{it.end} chunks={c}")
        typer.echo(f"bbox(w,s,e,n)={bbox} chunks={n}")
        if dry_run:
            return
        results = fa.download_area(plan, bbox, key, client=client, workers=workers)
    for (src, status), cnt in sorted(fa.group_summary(results).items()):
        typer.echo(f"{src} {status} {cnt}")
    errors = [r for r in results if r.status == "error"]
    for r in errors:
        typer.echo(f"ERROR {r.source} {r.start}_{r.days}: {r.detail}")
    if errors:
        raise typer.Exit(1)


@firms_app.command("area-ingest")
def area_ingest_cmd(
    product: Annotated[list[str] | None, typer.Option("--product")] = None,
    level: Annotated[list[str] | None, typer.Option("--level", help="api-sp | nrt")] = None,
    year: Annotated[list[int] | None, typer.Option("--year")] = None,
) -> None:
    """Area API chunks -> clipped parquet per product, level and year."""
    from firecal.io import firms_area as fa

    for r in fa.area_ingest(products=product, levels=level or fa.LEVELS, years=year):
        typer.echo(
            f"{r['product']} {r['level']} {r['year']} rows={r['rows']} "
            f"(clip dropped {r['clip_rows_dropped_source']} of the source)"
        )


@firms_app.command("clip-check")
def clip_check_cmd(year: int = 2025, out: Path = REPO_ROOT / "reports" / "01" / "SA1.6_clip.md") -> None:
    """P7: API-SP clipped vs country files; writes reports/01/SA1.6_clip.md."""
    from firecal.io import firms_area as fa

    path, checks = fa.write_clip_report(out, year)
    for c in checks:
        typer.echo(
            f"{c.satellite} country={c.country_rows} api={c.api_rows} matched={c.matched} "
            f"country_only={c.country_only.unmatched} api_only={c.api_only.unmatched} "
            f"{'PASS' if c.ok else 'FAIL'}"
        )
    typer.echo(str(path))
    if not all(c.ok for c in checks):
        raise typer.Exit(1)
