"""MCD64A1 C6.1 monthly burned area (SA2.9): download from LP DAAC and grid to the 0.1 degree cells.

Download: granules are found through NASA CMR (no login) and fetched from LP DAAC, which needs an Earthdata
login; the session or network layer supplies it and this module never reads, stores or prints credentials. A
manifest (`data/raw/mcd64a1/manifest.json`) keeps the sha256 and size of every file; downloads are idempotent.

Grid: the `Burn Date` layer (int16; 0 unburned land, 1..366 day of burn, -1 unmapped, -2 water) of a tile is
put on the MODIS sinusoidal grid (pixel centres from the grid formula) and counted per 0.1 degree cell of
`stages/grid/grid.py` and month, clipped to the union of the geoBoundaries ADM2 polygons.
"""

import hashlib
import json
import math
import os
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import typer

from firecal.paths import interim_dir, raw_dir
from firecal.stages.grid.grid import cell_ids

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
SHORT_NAME, VERSION = "MCD64A1", "061"
FIRST_YM = (2000, 11)  # first MCD64A1 month
LAST_YM = (2025, 12)

# MODIS sinusoidal grid (spherical, R in m) and the 500 m product layout (2400 x 2400 pixels per tile).
EARTH_R = 6371007.181
TILE_M = 1111950.5196666666
N_PIX = 2400
PIX_M = TILE_M / N_PIX  # 463.3127 m: the "500 m" of the product
X_MIN, Y_MAX = -20015109.354, 10007554.677
# The sinusoidal projection is equal-area, so every pixel has the same area: (463.3127 m)^2 = 0.21460 km2.
PIXEL_AREA_KM2 = (PIX_M / 1000) ** 2

BURN_LAYER = "Burn Date"
UNMAPPED, WATER = -1, -2

OUT_SCHEMA = pa.schema(
    [
        ("cell_id", pa.int64()),
        ("ym", pa.int32()),
        ("burned_px", pa.int32()),
        ("burned_km2", pa.float64()),
        ("unmapped_px", pa.int32()),
    ]
)


# ---------------------------------------------------------------- geometry


def pixel_centers(h: int, v: int, rows: np.ndarray, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Latitude and longitude (degrees) of the centres of pixels (rows, cols) of MODIS tile (h, v)."""
    x = X_MIN + h * TILE_M + (np.asarray(cols, dtype=np.float64) + 0.5) * PIX_M
    y = Y_MAX - v * TILE_M - (np.asarray(rows, dtype=np.float64) + 0.5) * PIX_M
    lat = y / EARTH_R
    with np.errstate(divide="ignore", invalid="ignore"):
        lon = x / (EARTH_R * np.cos(lat))
    return np.degrees(lat), np.degrees(lon)


def tile_bounds_valid(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Pixels whose centre lies on the globe (tiles on the sinusoidal edge have fill outside it)."""
    return np.isfinite(lat) & np.isfinite(lon) & (np.abs(lon) <= 180.0)


def aggregate_cells(
    lat: np.ndarray, lon: np.ndarray, burned: np.ndarray, unmapped: np.ndarray, ym: int, res: float = 0.1
) -> pd.DataFrame:
    """Burned and unmapped pixel counts per cell for one month (`burned`, `unmapped`: boolean per pixel)."""
    sel = burned | unmapped
    if not sel.any():
        return pd.DataFrame({c.name: pd.Series(dtype=c.type.to_pandas_dtype()) for c in OUT_SCHEMA})
    cid = cell_ids(lat[sel], lon[sel], res)
    d = pd.DataFrame({"cell_id": cid, "b": burned[sel].astype(np.int32), "u": unmapped[sel].astype(np.int32)})
    g = d.groupby("cell_id", sort=True, as_index=False).sum()
    out = pd.DataFrame(
        {
            "cell_id": g["cell_id"].to_numpy().astype(np.int64),
            "ym": np.int32(ym),
            "burned_px": g["b"].to_numpy().astype(np.int32),
            "burned_km2": g["b"].to_numpy() * PIXEL_AREA_KM2,
            "unmapped_px": g["u"].to_numpy().astype(np.int32),
        }
    )
    return out


def parse_title(title: str) -> tuple[int, int, int, int, int]:
    """`MCD64A1.A2020245.h12v12.061.<processing>` -> (year, month, day of year, h, v)."""
    parts = title.split(".")
    year, doy = int(parts[1][1:5]), int(parts[1][5:8])
    month = (datetime(year, 1, 1) + pd.Timedelta(days=doy - 1)).month
    return year, month, doy, int(parts[2][1:3]), int(parts[2][4:6])


def read_burn_date(path: Path) -> np.ndarray:
    """The `Burn Date` layer of an HDF4 granule as int16 (2400, 2400)."""
    from pyhdf.SD import SD, SDC

    sd = SD(str(path), SDC.READ)
    try:
        return np.asarray(sd.select(BURN_LAYER)[:], dtype=np.int16)
    finally:
        sd.end()


def grid_tile(path: Path, geom=None, res: float = 0.1) -> pd.DataFrame:
    """One tile-month granule -> per-cell counts (clipped to `geom` when given)."""
    import shapely

    year, month, _, h, v = parse_title(path.name)
    burn = read_burn_date(path)
    ym = year * 12 + month - 1
    mask = (burn > 0) | (burn == UNMAPPED)
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        return aggregate_cells(np.empty(0), np.empty(0), np.empty(0, bool), np.empty(0, bool), ym, res)
    lat, lon = pixel_centers(h, v, rows, cols)
    ok = tile_bounds_valid(lat, lon)
    if geom is not None:
        # Bounding box first (cheap), then the polygon test on what is left.
        minx, miny, maxx, maxy = geom.bounds
        near = ok & (lon >= minx) & (lon <= maxx) & (lat >= miny) & (lat <= maxy)
        inside = np.zeros(len(rows), dtype=bool)
        if near.any():
            inside[near] = shapely.contains_xy(geom, lon[near], lat[near])
        ok = inside
    vals = burn[rows, cols]
    return aggregate_cells(lat[ok], lon[ok], vals[ok] > 0, vals[ok] == UNMAPPED, ym, res)


# ---------------------------------------------------------------- download


@dataclass
class Granule:
    title: str
    url: str
    year: int
    month: int
    h: int
    v: int

    @property
    def ym(self) -> int:
        return self.year * 12 + self.month - 1


def cmr_granules(
    bbox: tuple[float, float, float, float],
    start: tuple[int, int] = FIRST_YM,
    end: tuple[int, int] = LAST_YM,
    client: httpx.Client | None = None,
    retries: int = 4,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Granule]:
    """Every MCD64A1 C6.1 tile-month intersecting `bbox` (w, s, e, n) between two (year, month), via CMR."""
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=60)
    found: dict[str, Granule] = {}
    try:
        for year in range(start[0], end[0] + 1):
            m0 = start[1] if year == start[0] else 1
            m1 = end[1] if year == end[0] else 12
            t0 = f"{year}-{m0:02d}-01T00:00:00Z"
            t1 = f"{year}-{m1:02d}-28T00:00:00Z" if m1 == 2 else f"{year}-{m1:02d}-30T23:59:59Z"
            page = 1
            while True:
                params = {
                    "short_name": SHORT_NAME,
                    "version": VERSION,
                    "temporal": f"{t0},{t1}",
                    "bounding_box": ",".join(str(x) for x in bbox),
                    "page_size": 2000,
                    "page_num": page,
                }
                for attempt in range(retries + 1):
                    try:
                        r = client.get(CMR_URL, params=params)
                        if r.status_code >= 500:
                            raise httpx.TransportError(f"HTTP {r.status_code}")
                        r.raise_for_status()
                        break
                    except httpx.HTTPError:
                        if attempt == retries:
                            raise
                        sleep(2**attempt)
                entries = r.json()["feed"]["entry"]
                for e in entries:
                    url = next(
                        (
                            lk["href"]
                            for lk in e.get("links", [])
                            if lk["href"].endswith(".hdf") and lk["href"].startswith("https://")
                        ),
                        None,
                    )
                    if url is None:
                        continue
                    y, m, _, h, v = parse_title(e["title"])
                    found[e["title"]] = Granule(e["title"], url, y, m, h, v)
                if len(entries) < 2000:
                    break
                page += 1
    finally:
        if own:
            client.close()
    return sorted(found.values(), key=lambda g: (g.ym, g.h, g.v))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _fetch(client: httpx.Client, url: str, target: Path, retries: int, backoff: float, sleep) -> str:
    """Stream to `target` atomically; returns "ok" or raises RuntimeError (messages carry no URL)."""
    tmp = target.with_name(target.name + ".part")
    last = ""
    for attempt in range(retries + 1):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        try:
            with client.stream("GET", url) as r:
                if r.status_code in (429,) or r.status_code >= 500:
                    last = f"HTTP {r.status_code}"
                    continue
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                expected = r.headers.get("content-length")
                n = 0
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
                        n += len(chunk)
                if expected is not None and int(expected) != n:
                    last = f"short read {n} of {expected} bytes"
                    continue
            os.replace(tmp, target)
            return "ok"
        except httpx.TransportError as e:
            last = type(e).__name__
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError(last)


def manifest_path(dest: Path) -> Path:
    return dest / "manifest.json"


def load_manifest(dest: Path) -> dict:
    p = manifest_path(dest)
    return json.loads(p.read_text()) if p.exists() else {"granules": {}}


def save_manifest(dest: Path, man: dict) -> None:
    p = manifest_path(dest)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(man, indent=1, sort_keys=True))
    os.replace(tmp, p)


def download_granules(
    granules: Iterable[Granule],
    dest: Path | None = None,
    workers: int = 6,
    retries: int = 4,
    backoff: float = 2.0,
    verify: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
    client_factory: Callable[[], httpx.Client] | None = None,
) -> dict[str, int]:
    """Download missing granules in parallel (one cookie-keeping client per thread). Returns status counts.

    Skips a file already in the manifest with the recorded size (and sha256 with `verify`).
    """
    dest = dest or raw_dir() / "mcd64a1"
    man = load_manifest(dest)
    entries = man["granules"]
    lock = threading.Lock()
    local = threading.local()
    counts = {"downloaded": 0, "skipped": 0, "error": 0}
    todo = []
    for g in granules:
        target = dest / str(g.year) / f"{g.title}.hdf"
        rec = entries.get(g.title)
        intact = bool(rec) and target.exists() and target.stat().st_size == rec["bytes"]
        if intact and (not verify or sha256_file(target) == rec["sha256"]):
            counts["skipped"] += 1
            continue
        todo.append((g, target))

    def client() -> httpx.Client:
        if not hasattr(local, "c"):
            local.c = (client_factory or (lambda: httpx.Client(follow_redirects=True, timeout=180)))()
        return local.c

    def work(g: Granule, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True)
        _fetch(client(), g.url, target, retries, backoff, sleep)
        return g, target

    done = 0
    with ThreadPoolExecutor(max(1, workers)) as ex:
        futs = {ex.submit(work, g, t): g for g, t in todo}
        for fut in as_completed(futs):
            g = futs[fut]
            try:
                _, target = fut.result()
            except RuntimeError as e:
                counts["error"] += 1
                with lock:
                    entries[g.title] = {"status": "error", "detail": str(e), "ym": g.ym, "h": g.h, "v": g.v}
                if log:
                    log(f"error {g.title}: {e}")
                continue
            rec = {
                "file": str(target.relative_to(dest)),
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
                "ym": g.ym,
                "h": g.h,
                "v": g.v,
                "downloaded": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            with lock:
                entries[g.title] = rec
                counts["downloaded"] += 1
                done += 1
                if done % 200 == 0:
                    save_manifest(dest, man)
                    if log:
                        log(f"  {done} of {len(todo)} downloaded")
    man["source"] = {
        "product": f"{SHORT_NAME}.{VERSION}",
        "catalog": CMR_URL,
        "host": "data.lpdaac.earthdatacloud.nasa.gov",
        "updated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_manifest(dest, man)
    return counts


# ---------------------------------------------------------------- grid


def grid_burned(
    src: Path | None = None, out: Path | None = None, res: float = 0.1, workers: int = 4, log=None
) -> Path:
    """Grid every downloaded tile-month to `mcd64a1_<res>.parquet` (one row per cell-month)."""
    from firecal.io.firms_area import load_argentina

    src = src or raw_dir() / "mcd64a1"
    out = out or interim_dir() / "burned" / f"mcd64a1_{res}.parquet"
    man = load_manifest(src)
    files = sorted(
        (src / rec["file"]) for rec in man["granules"].values() if rec.get("file") and "sha256" in rec
    )
    geom, geom_sha = load_argentina()
    import shapely

    shapely.prepare(geom)

    def one(p: Path) -> pd.DataFrame:
        return grid_tile(p, geom, res)

    parts = []
    with ThreadPoolExecutor(max(1, workers)) as ex:
        for i, df in enumerate(ex.map(one, files), 1):
            parts.append(df)
            if log and i % 500 == 0:
                log(f"  {i} of {len(files)} tiles gridded")
    allp = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if len(allp):
        g = allp.groupby(["cell_id", "ym"], sort=True, as_index=False).agg(
            burned_px=("burned_px", "sum"),
            burned_km2=("burned_km2", "sum"),
            unmapped_px=("unmapped_px", "sum"),
        )
        g["burned_px"] = g["burned_px"].astype("int32")
        g["unmapped_px"] = g["unmapped_px"].astype("int32")
        g["ym"] = g["ym"].astype("int32")
    else:
        g = pd.DataFrame({c.name: pd.Series(dtype=c.type.to_pandas_dtype()) for c in OUT_SCHEMA})
    table = pa.Table.from_pandas(g, schema=OUT_SCHEMA, preserve_index=False).replace_schema_metadata(
        {
            "source": f"{SHORT_NAME}.{VERSION} (LP DAAC), Burn Date layer",
            "pixel_area_km2": f"{PIXEL_AREA_KM2:.6f}",
            "pixel_size_m": f"{PIX_M:.4f}",
            "clip": f"union of geoBoundaries ADM2 polygons (GeoJSON sha256 {geom_sha})",
            "tiles": str(len(files)),
            "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, out)
    return out


def read_burned(path: Path | None = None) -> pd.DataFrame:
    """Gridded monthly burned area: cell_id, ym (year * 12 + month - 1), burned_px, burned_km2, ."""
    path = path or interim_dir() / "burned" / "mcd64a1_0.1.parquet"
    return pq.read_table(path).to_pandas()


# ---------------------------------------------------------------- CLI

burned_app = typer.Typer(no_args_is_help=True, help="MCD64A1 burned area: download and grid (SA2.9).")


def argentina_bbox() -> tuple[float, float, float, float]:
    from firecal.io.firms_area import load_argentina

    geom, _ = load_argentina()
    minx, miny, maxx, maxy = geom.bounds
    return (
        math.floor(minx * 10) / 10,
        math.floor(miny * 10) / 10,
        math.ceil(maxx * 10) / 10,
        math.ceil(maxy * 10) / 10,
    )


@burned_app.command("download")
def download_cmd(
    workers: Annotated[int, typer.Option(help="Parallel downloads (4-8).")] = 6,
    start: Annotated[str, typer.Option(help="First month, YYYY-MM.")] = "2000-11",
    end: Annotated[str, typer.Option(help="Last month, YYYY-MM.")] = "2025-12",
    verify: Annotated[bool, typer.Option(help="Re-hash existing files against the manifest.")] = False,
    limit: Annotated[int | None, typer.Option(help="Only the first N granules (testing).")] = None,
) -> None:
    """Download MCD64A1 C6.1 tiles covering Argentina (bbox of the ADM2 boundaries); idempotent."""
    t0 = time.time()
    bbox = argentina_bbox()
    s = tuple(int(x) for x in start.split("-"))
    e = tuple(int(x) for x in end.split("-"))
    grans = cmr_granules(bbox, s, e)
    if limit:
        grans = grans[:limit]
    tiles = sorted({(g.h, g.v) for g in grans})
    typer.echo(f"bbox {bbox}; {len(grans)} granules, {len(tiles)} tiles; {s} to {e}")
    counts = download_granules(grans, workers=workers, verify=verify, log=typer.echo)
    typer.echo(f"{counts}; {time.time() - t0:.0f} s")


@burned_app.command("grid")
def grid_cmd(workers: Annotated[int, typer.Option(help="Threads.")] = 4) -> None:
    """Grid the downloaded tiles to 0.1 degree cells x month (data/interim/burned/mcd64a1_0.1.parquet)."""
    t0 = time.time()
    p = grid_burned(workers=workers, log=typer.echo)
    df = read_burned(p)
    typer.echo(
        f"{p}: {len(df):,} cell-months, {df['burned_km2'].sum():,.0f} km2 burned, {time.time() - t0:.0f} s"
    )
