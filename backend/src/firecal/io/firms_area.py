"""FIRMS area API: recent data (SA1.6 part a), clip to Argentina and the P7 clip check.

Source: `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/{SOURCE}/{w,s,e,n}/{DAYS 1..5}/{YYYY-MM-DD}`.
The key comes from the environment variable `FIRMS_MAP_KEY` and is never printed, logged or stored: every URL
written to a manifest or an error message has it replaced by `***`.

Date coverage (verified 2026-11-15 with MODIS_SP, DAYS=5, DATE=2025-06-10): the response holds acq_date values
2025-06-10 .. 2025-06-14, i.e. a request covers `DATE .. DATE + DAYS - 1` (forward, DATE included).

Layout:
- raw chunks: `data/raw/firms_area/{SOURCE}/{start}_{days}.csv` (+ `.sha256`); manifest
  `data/raw/firms_area/manifest.json` (status per chunk: downloaded | skipped | error).
- NRT rolls off the API, so every NRT fetch is also archived, never deleted, at
  `data/raw/firms_area/archive/{SOURCE}/{fetched_at}/{start}_{days}.csv`. NRT chunks whose end is within 7
  days of the fetch day are re-fetched on each run (the data of those days is still being completed).
- ingest: `data/interim/firms/detections/product={p}/level={api-sp|nrt}/year={y}/part-0.parquet`. The country
  files stay at `product={p}/year={y}` (level country-sp).

Clip: rows are kept when they fall inside the union of the geoBoundaries ADM2 polygons (shapely 2 vectorized
`contains_xy` on a prepared geometry). The union is a simplified geometry: a row exactly on the boundary or in
a sliver between polygons is dropped (counted in the parquet metadata `clip_rows_dropped`).

Distance to the boundary (P7): points are compared with the boundary segments of the union in a local
equirectangular approximation (dx = R cos(lat) dlon, dy = R dlat, R = 6371.0088 km); the error is well under
1 % for distances below 20 km. Segments are searched in a window of 0.2 deg around the point, then the nearest
segment in degrees if the window is empty.
"""

import csv
import hashlib
import io
import json
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from shapely.geometry import shape

from firecal.io.firms import DETECTION_SCHEMA, read_firms_csv, sha256_file
from firecal.paths import REPO_ROOT, interim_dir, raw_dir

API = "https://firms.modaps.eosdis.nasa.gov/api"
KEY_ENV = "FIRMS_MAP_KEY"
MAX_DAYS = 5
BBOX_PAD = 0.05
NRT_REFRESH_DAYS = 7
LIMIT_WAIT_S = 60.0
LIMIT_WAITS = 20
EARTH_RADIUS_KM = 6371.0088
LEVELS = ("api-sp", "nrt")

MODIS_COLS = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
    "bright_t31,frp,daynight"
)
VIIRS_COLS = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
    "bright_ti5,frp,daynight"
)


@dataclass(frozen=True)
class Source:
    id: str  # FIRMS data_id, also the API source name
    family: str
    product: str
    level: str  # api-sp | nrt
    header: str
    satellites: tuple[str, ...]  # expected values of the `satellite` column


def _sources() -> dict[str, Source]:
    fams = {
        "MODIS": ("modis", MODIS_COLS, ("Terra", "Aqua")),
        "VIIRS_SNPP": ("viirs-snpp", VIIRS_COLS, ("N",)),
        "VIIRS_NOAA20": ("viirs-jpss1", VIIRS_COLS, ("N20",)),
        "VIIRS_NOAA21": ("viirs-jpss2", VIIRS_COLS, ("N21",)),
    }
    out = {}
    for fam, (product, header, sats) in fams.items():
        for suffix, level in (("SP", "api-sp"), ("NRT", "nrt")):
            sid = f"{fam}_{suffix}"
            out[sid] = Source(sid, fam, product, level, header, sats)
    return out


SOURCES = _sources()
# SP start of the default plan (NOAA-21 has no country files: its overlap fit needs its history from 2023-03).
DEFAULT_SP_START = {"VIIRS_NOAA21": date(2023, 3, 1)}
DEFAULT_SP_FROM = date(2026, 1, 1)
CLIP_CHECK_FAMILIES = ("MODIS", "VIIRS_SNPP", "VIIRS_NOAA20")
CLIP_CHECK_RANGE = (date(2025, 1, 1), date(2025, 12, 31))


# ---------------------------------------------------------------- helpers


def mask(text: str, key: str | None) -> str:
    """Replace the MAP key in any text (URL, exception message)."""
    return text.replace(key, "***") if key else text


def get_key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(f"{KEY_ENV} is not set in the environment")
    return key


def chunk_ranges(start: date, end: date, max_days: int = MAX_DAYS) -> list[tuple[date, int]]:
    """Cover start..end (inclusive) with (chunk_start, days) pieces of at most max_days, from `start`."""
    out = []
    d = start
    while d <= end:
        n = min(max_days, (end - d).days + 1)
        out.append((d, n))
        d += timedelta(days=n)
    return out


def chunk_name(start: date, days: int) -> str:
    return f"{start.isoformat()}_{days}.csv"


_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d)\.csv$")


def parse_chunk_name(name: str) -> tuple[date, int] | None:
    m = _NAME_RE.match(name)
    return (date.fromisoformat(m.group(1)), int(m.group(2))) if m else None


def bbox_from_geometry(geom, pad: float = BBOX_PAD) -> tuple[float, float, float, float]:
    w, s, e, n = geom.bounds
    return (round(w - pad, 4), round(s - pad, 4), round(e + pad, 4), round(n + pad, 4))


def area_url(key: str, source: str, bbox: tuple[float, float, float, float], start: date, days: int) -> str:
    box = ",".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in bbox)
    return f"{API}/area/csv/{key}/{source}/{box}/{days}/{start.isoformat()}"


class ChunkError(Exception):
    """A failed request or an invalid body; the message never contains the key."""


def validate_body(body: bytes, header: str) -> int:
    """Return the data rows of a valid FIRMS CSV body; raise ChunkError if it is anything else."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ChunkError("body is not UTF-8 text") from e
    lines = text.splitlines()
    if not lines or lines[0].strip() not in (header, header + ",type"):
        first = lines[0][:80] if lines else "<empty>"
        raise ChunkError(f"body is not a FIRMS CSV with the expected header (starts with: {first!r})")
    width = len(lines[0].split(","))
    rows = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        if len(line.split(",")) != width:
            raise ChunkError(f"row {rows + 1} has a different number of fields than the header")
        rows += 1
    return rows


def _get(
    client: httpx.Client, url: str, key: str, retries: int, backoff: float, sleep: Callable[[float], None]
) -> bytes:
    """GET with retries on transport errors, 5xx and 429. Raises ChunkError (key masked)."""
    last = ""
    limit_waits = 0
    attempt = 0
    while attempt <= retries:
        if attempt:
            sleep(min(backoff * 2 ** (attempt - 1), 60.0))
        attempt += 1
        try:
            r = client.get(url)
        except httpx.TransportError as e:
            last = mask(f"{type(e).__name__}: {e}", key)
            continue
        if r.status_code >= 500 or r.status_code == 429:
            last = f"HTTP {r.status_code}"
            continue
        if r.status_code == 400 and b"transaction limit" in r.content[:200].lower():
            # 5000 transactions per 10 minutes per key (a request costs several): wait for the window to roll.
            if limit_waits >= LIMIT_WAITS:
                raise ChunkError("HTTP 400 transaction limit still exceeded after waiting")
            limit_waits += 1
            attempt -= 1
            sleep(LIMIT_WAIT_S)
            attempt = max(attempt, 0)
            continue
        if r.status_code != 200:
            raise ChunkError(mask(f"HTTP {r.status_code}: {r.text[:100]!r}", key))
        return r.content
    raise ChunkError(f"gave up after {retries + 1} attempts: {last}")


def fetch_availability(
    client: httpx.Client, key: str, retries: int = 5, backoff: float = 2.0, sleep=time.sleep
) -> dict[str, tuple[date, date]]:
    body = _get(client, f"{API}/data_availability/csv/{key}/ALL", key, retries, backoff, sleep)
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    if not rows or "data_id" not in rows[0]:
        raise ChunkError("data_availability did not return the expected CSV")
    return {
        r["data_id"]: (date.fromisoformat(r["min_date"]), date.fromisoformat(r["max_date"])) for r in rows
    }


# ---------------------------------------------------------------- plan


@dataclass(frozen=True)
class PlanItem:
    source: str
    start: date
    end: date


def select_sources(names: Iterable[str] | None) -> list[str]:
    """Names are source ids (MODIS_SP) or families (MODIS: both levels). Default: all."""
    if not names:
        return list(SOURCES)
    out = []
    for n in names:
        hit = [s for s in SOURCES if s == n or SOURCES[s].family == n]
        if not hit:
            raise ValueError(f"unknown source {n!r}; known: {sorted(SOURCES)} or families")
        out += [s for s in hit if s not in out]
    return out


def build_plan(
    avail: dict[str, tuple[date, date]],
    today: date,
    sources: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    clip_check: bool = False,
    clip_check_only: bool = False,
) -> list[PlanItem]:
    """Ranges per source bounded by data_availability.

    Default: SP from 2026-01-01 (NOAA-21: 2023-03-01) to the SP end; NRT from the day after the SP end to
    min(NRT end, today). `date_from`/`date_to` replace those ranges for the selected sources.
    `clip_check` adds SP 2025-01-01..2025-12-31 for MODIS, S-NPP and NOAA-20 (P7).
    """
    chosen = select_sources(sources)
    items: list[PlanItem] = []

    def add(src: str, lo: date, hi: date) -> None:
        if src not in avail:
            raise ValueError(f"{src} is not in data_availability")
        amin, amax = avail[src]
        lo, hi = max(lo, amin), min(hi, amax, today)
        if lo <= hi:
            items.append(PlanItem(src, lo, hi))

    if not clip_check_only:
        for src in chosen:
            s = SOURCES[src]
            sp_end = avail[f"{s.family}_SP"][1]
            if date_from or date_to:
                lo = date_from or avail[src][0]
                hi = date_to or today
            elif s.level == "api-sp":
                lo, hi = DEFAULT_SP_START.get(s.family, DEFAULT_SP_FROM), sp_end
            else:
                lo, hi = sp_end + timedelta(days=1), today
            add(src, lo, hi)
    if clip_check or clip_check_only:
        for fam in CLIP_CHECK_FAMILIES:
            src = f"{fam}_SP"
            if src in chosen or clip_check_only and not sources:
                add(src, *CLIP_CHECK_RANGE)
    return items


# ---------------------------------------------------------------- download


@dataclass
class ChunkResult:
    source: str
    start: str
    days: int
    status: str  # downloaded | skipped | error
    rows: int | None = None
    sha256: str | None = None
    fetched_at: str | None = None
    path: str | None = None
    url: str | None = None  # key masked
    detail: str | None = None


def area_dir() -> Path:
    return raw_dir() / "firms_area"


def _count_rows(path: Path) -> int:
    with path.open("rb") as f:
        n = sum(1 for line in f if line.strip())
    return max(n - 1, 0)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _load_manifest(dest: Path) -> dict:
    path = dest / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {"records": []}


def _save_manifest(dest: Path, manifest: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=1) + "\n")
    tmp.replace(dest / "manifest.json")


def _needs_nrt_refresh(prev: dict | None, start: date, days: int) -> bool:
    """NRT chunk is fetched again while the fetch happened within 7 days after the chunk end."""
    if not prev or not prev.get("fetched_at"):
        return True
    end = start + timedelta(days=days - 1)
    fetched = datetime.fromisoformat(prev["fetched_at"]).date()
    return fetched <= end + timedelta(days=NRT_REFRESH_DAYS)


def download_area(
    plan: list[PlanItem],
    bbox: tuple[float, float, float, float],
    key: str,
    dest: Path | None = None,
    client: httpx.Client | None = None,
    retries: int = 5,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    workers: int = 4,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[ChunkResult]:
    dest = dest or area_dir()
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=120)
    manifest = _load_manifest(dest)
    prev = {(r["source"], r["start"], r["days"]): r for r in manifest["records"]}

    jobs: list[tuple[str, date, int]] = [
        (it.source, s, n) for it in plan for s, n in chunk_ranges(it.start, it.end)
    ]

    def run(job: tuple[str, date, int]) -> ChunkResult:
        src, start, days = job
        source = SOURCES[src]
        name = chunk_name(start, days)
        target = dest / src / name
        sidecar = target.with_name(name + ".sha256")
        old = prev.get((src, start.isoformat(), days))
        url = area_url(key, src, bbox, start, days)
        res = ChunkResult(src, start.isoformat(), days, "error", url=mask(url, key))
        if target.exists() and sidecar.exists():
            digest = sha256_file(target)
            fresh = source.level == "api-sp" or not _needs_nrt_refresh(old, start, days)
            if digest == sidecar.read_text().strip() and fresh:
                res.status, res.rows, res.sha256, res.path = (
                    "skipped",
                    _count_rows(target),
                    digest,
                    str(target),
                )
                res.fetched_at = old.get("fetched_at") if old else None
                return res
        try:
            body = _get(client, url, key, retries, backoff, sleep)
            res.rows = validate_body(body, source.header)
        except ChunkError as e:
            res.detail = mask(str(e), key)
            return res
        stamp = now()
        res.fetched_at = stamp.isoformat()
        digest = hashlib.sha256(body).hexdigest()
        if source.level == "nrt":
            arch = dest / "archive" / src / stamp.strftime("%Y%m%dT%H%M%SZ") / name
            _atomic_write(arch, body)
            arch.with_name(name + ".sha256").write_text(digest + "\n")
        _atomic_write(target, body)
        sidecar.write_text(digest + "\n")
        res.status, res.sha256, res.path = "downloaded", digest, str(target)
        return res

    results: list[ChunkResult] = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, res in enumerate(pool.map(run, jobs), 1):
                results.append(res)
                prev[(res.source, res.start, res.days)] = asdict(res)
                if i % 25 == 0:
                    manifest["records"] = sorted(prev.values(), key=lambda r: (r["source"], r["start"]))
                    _save_manifest(dest, manifest)
    finally:
        if own:
            client.close()
        manifest["records"] = sorted(prev.values(), key=lambda r: (r["source"], r["start"], r["days"]))
        manifest["updated_at"] = now().isoformat()
        manifest["bbox_wsen"] = list(bbox)
        _save_manifest(dest, manifest)
    return results


# ---------------------------------------------------------------- geometry


def load_argentina(dir_: Path | None = None):
    """Union of the geoBoundaries ADM2 polygons. Returns (geometry, sha256 of the GeoJSON)."""
    from firecal.stages.publish import boundaries as bnd

    path = (dir_ or bnd.boundaries_dir()) / "ADM2" / bnd.geojson_name("ADM2")
    data = json.loads(path.read_text())
    geoms = [shapely.make_valid(shape(f["geometry"])) for f in data["features"]]
    return shapely.union_all(geoms), sha256_file(path)


def clip_inside(df: pd.DataFrame, geom) -> pd.DataFrame:
    """Keep rows whose (longitude, latitude) lie inside geom (vectorized, prepared geometry)."""
    shapely.prepare(geom)
    inside = shapely.contains_xy(geom, df["longitude"].to_numpy(), df["latitude"].to_numpy())
    return df.loc[inside].reset_index(drop=True)


class BoundaryDistance:
    """Distance in km from points to the boundary segments of a geometry (see module docstring)."""

    def __init__(self, geom):
        segs = []
        for ring in shapely.get_rings(shapely.get_parts(geom)):
            c = shapely.get_coordinates(ring)
            if len(c) > 1:
                segs.append(np.hstack([c[:-1], c[1:]]))
        self.seg = np.vstack(segs)  # x1, y1, x2, y2
        self.tree = shapely.STRtree(shapely.linestrings(self.seg.reshape(-1, 2, 2)))

    def one(self, lon: float, lat: float, window: float = 0.2) -> float:
        idx = self.tree.query(shapely.box(lon - window, lat - window, lon + window, lat + window))
        if len(idx) == 0:
            idx = self.tree.query_nearest(shapely.points(lon, lat))
        s = self.seg[idx]
        kx = np.radians(1.0) * EARTH_RADIUS_KM * np.cos(np.radians(lat))
        ky = np.radians(1.0) * EARTH_RADIUS_KM
        x1, y1 = (s[:, 0] - lon) * kx, (s[:, 1] - lat) * ky
        x2, y2 = (s[:, 2] - lon) * kx, (s[:, 3] - lat) * ky
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = np.where(L2 > 0, np.clip(-(x1 * dx + y1 * dy) / np.where(L2 > 0, L2, 1), 0, 1), 0)
        return float(np.min(np.hypot(x1 + t * dx, y1 + t * dy)))

    def many(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        return np.array([self.one(x, y) for x, y in zip(lon, lat, strict=True)], dtype="float64")


# ---------------------------------------------------------------- ingest


def _chunks_for(src: Source, dest: Path) -> list[tuple[date, int, Path]]:
    """One file per chunk start (the longest request wins); NRT reads the latest archive copy."""
    best: dict[date, tuple[int, Path]] = {}
    for f in (dest / src.id).glob("*.csv"):
        parsed = parse_chunk_name(f.name)
        if parsed is None:
            continue
        start, days = parsed
        path = f
        if src.level == "nrt":
            copies = sorted((dest / "archive" / src.id).glob(f"*/{f.name}"), key=lambda p: p.parent.name)
            if copies:
                path = copies[-1]
        if start not in best or days > best[start][0]:
            best[start] = (days, path)
    return [(s, d, p) for s, (d, p) in sorted(best.items())]


def _check_satellites(path: Path, src: Source) -> None:
    sats = set(pd.read_csv(path, usecols=["satellite"], dtype=str)["satellite"].str.strip().unique())
    if not sats <= set(src.satellites):
        raise ValueError(f"{path.name}: unexpected satellite values {sorted(sats - set(src.satellites))}")


def read_source(src: Source, dest: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """All chunks of a source in DETECTION_SCHEMA, deduplicated across chunks.

    A row is dropped only when an identical row (all schema columns) already came from another chunk: copies
    within one chunk are kept (duplicate keys exist in FIRMS), copies across overlapping chunks are not.
    """
    frames, shas = [], {}
    for _start, _days, path in _chunks_for(src, dest):
        if _count_rows(path) == 0:
            continue
        _check_satellites(path, src)
        df = read_firms_csv(path, src.product)
        df["_occ"] = df.groupby(list(DETECTION_SCHEMA.names), dropna=False).cumcount()
        frames.append(df)
        shas[str(path.relative_to(dest))] = sha256_file(path)
    if not frames:
        return pd.DataFrame(columns=DETECTION_SCHEMA.names), shas
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=[*DETECTION_SCHEMA.names, "_occ"]).drop(columns="_occ")
    return df.reset_index(drop=True), shas


def area_ingest(
    products: Iterable[str] | None = None,
    levels: Iterable[str] = LEVELS,
    years: Iterable[int] | None = None,
    raw: Path | None = None,
    out: Path | None = None,
    geom=None,
    geom_sha: str | None = None,
) -> list[dict]:
    raw = raw or area_dir()
    out = out or interim_dir() / "firms" / "detections"
    if geom is None:
        geom, geom_sha = load_argentina()
    wanted = set(products) if products else None
    ywanted = set(years) if years else None
    report = []
    for src in SOURCES.values():
        if src.level not in levels or (wanted and src.product not in wanted):
            continue
        df, shas = read_source(src, raw)
        if df.empty:
            continue
        rows_in = len(df)
        kept = clip_inside(df, geom)
        dropped = rows_in - len(kept)
        for year, part in kept.groupby("year"):
            if ywanted and int(year) not in ywanted:
                continue
            table = pa.Table.from_pandas(
                part.reset_index(drop=True), schema=DETECTION_SCHEMA, preserve_index=False
            )
            meta = {
                "source_ids": json.dumps([src.id]),
                "source": "FIRMS area API",
                "level": src.level,
                "chunk_sha256": json.dumps(shas),
                "boundary_sha256": geom_sha or "",
                "rows_before_clip": str(rows_in),
                "clip_rows_dropped": str(dropped),
            }
            table = table.replace_schema_metadata(
                {**(table.schema.metadata or {}), **{k: v.encode() for k, v in meta.items()}}
            )
            dest = (
                out / f"product={src.product}" / f"level={src.level}" / f"year={int(year)}" / "part-0.parquet"
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            pq.write_table(table, tmp)
            tmp.replace(dest)
            report.append(
                {
                    "product": src.product,
                    "level": src.level,
                    "year": int(year),
                    "rows": len(part),
                    "clip_rows_dropped_source": dropped,
                }
            )
    return report


# ---------------------------------------------------------------- clip check (P7)

KEY_COLS = ["acq_datetime", "satellite", "lat4", "lon4"]
P7 = {"max_unmatched_pct": 1.0, "within_km": 5.0, "min_within_share": 0.95, "max_far_pct": 0.05}


def _keyed(df: pd.DataFrame) -> pd.DataFrame:
    k = df[["acq_datetime", "satellite", "latitude", "longitude"]].copy()
    k["lat4"] = np.round(k["latitude"].to_numpy() * 1e4).astype("int64")
    k["lon4"] = np.round(k["longitude"].to_numpy() * 1e4).astype("int64")
    return k


def multiset_diff(country: pd.DataFrame, api: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Multiset match on (acq_datetime, satellite, lat 4 dec, lon 4 dec).

    Returns (country-only, api-only, matched), the first two as one row per key with `n` excess copies and the
    latitude/longitude of the key.
    """
    a, b = _keyed(country), _keyed(api)
    ga = a.groupby(KEY_COLS, sort=False).agg(
        n_c=("latitude", "size"), latitude=("latitude", "first"), longitude=("longitude", "first")
    )
    gb = b.groupby(KEY_COLS, sort=False).agg(
        n_a=("latitude", "size"), latitude=("latitude", "first"), longitude=("longitude", "first")
    )
    m = ga.rename(columns={"latitude": "latitude_c", "longitude": "longitude_c"}).join(
        gb.rename(columns={"latitude": "latitude_a", "longitude": "longitude_a"}), how="outer"
    )
    n_c, n_a = m["n_c"].fillna(0).astype(int), m["n_a"].fillna(0).astype(int)
    lat = m["latitude_c"].fillna(m["latitude_a"])
    lon = m["longitude_c"].fillna(m["longitude_a"])
    only_c = pd.DataFrame({"latitude": lat, "longitude": lon, "n": (n_c - n_a).clip(lower=0)})
    only_a = pd.DataFrame({"latitude": lat, "longitude": lon, "n": (n_a - n_c).clip(lower=0)})
    matched = int(np.minimum(n_c, n_a).sum())
    return only_c[only_c["n"] > 0].reset_index(), only_a[only_a["n"] > 0].reset_index(), matched


@dataclass
class DirectionStats:
    unmatched: int = 0
    pct_of_country: float = 0.0
    within_5km: int = 0
    far: int = 0
    far_pct_of_country: float = 0.0
    within_share: float = 1.0
    median_km: float | None = None
    max_km: float | None = None
    ok: bool = True


def direction_stats(only: pd.DataFrame, country_rows: int, dist: BoundaryDistance) -> DirectionStats:
    st = DirectionStats()
    st.unmatched = int(only["n"].sum()) if len(only) else 0
    st.pct_of_country = 100 * st.unmatched / country_rows if country_rows else 0.0
    if st.unmatched:
        d = dist.many(only["longitude"].to_numpy(), only["latitude"].to_numpy())
        n = only["n"].to_numpy()
        near = d <= P7["within_km"]
        st.within_5km = int(n[near].sum())
        st.far = int(n[~near].sum())
        st.within_share = st.within_5km / st.unmatched
        st.median_km = float(np.median(np.repeat(d, n.astype(int))))
        st.max_km = float(d.max())
    st.far_pct_of_country = 100 * st.far / country_rows if country_rows else 0.0
    st.ok = (
        st.pct_of_country < P7["max_unmatched_pct"]
        and st.within_share >= P7["min_within_share"]
        and st.far_pct_of_country < P7["max_far_pct"]
    )
    return st


@dataclass
class SatelliteCheck:
    satellite: str
    product: str
    country_rows: int
    api_rows: int
    matched: int
    country_only: DirectionStats = field(default_factory=DirectionStats)
    api_only: DirectionStats = field(default_factory=DirectionStats)

    @property
    def ok(self) -> bool:
        return self.country_only.ok and self.api_only.ok


def _read_part(path: Path) -> pd.DataFrame:
    cols = ["satellite", "acq_datetime", "latitude", "longitude"]
    return pq.read_table(path, columns=cols).to_pandas()


def clip_check(det: Path | None = None, year: int = 2025, geom=None) -> list[SatelliteCheck]:
    det = det or interim_dir() / "firms" / "detections"
    if geom is None:
        geom, _ = load_argentina()
    dist = BoundaryDistance(geom)
    out = []
    for product in ("modis", "viirs-snpp", "viirs-jpss1"):
        cpath = det / f"product={product}" / f"year={year}" / "part-0.parquet"
        apath = det / f"product={product}" / "level=api-sp" / f"year={year}" / "part-0.parquet"
        if not cpath.exists() or not apath.exists():
            raise FileNotFoundError(f"missing {cpath if not cpath.exists() else apath}")
        c, a = _read_part(cpath), _read_part(apath)
        for sat in sorted(c["satellite"].unique()):
            cs, as_ = c[c["satellite"] == sat], a[a["satellite"] == sat]
            only_c, only_a, matched = multiset_diff(cs, as_)
            chk = SatelliteCheck(sat, product, len(cs), len(as_), matched)
            chk.country_only = direction_stats(only_c, len(cs), dist)
            chk.api_only = direction_stats(only_a, len(cs), dist)
            out.append(chk)
    return out


def coverage_from_manifest(dest: Path | None = None, year: int = 2025) -> dict[str, dict]:
    """Per SP source: chunks and days of `year` recorded OK in the manifest vs the days of the year."""
    dest = dest or area_dir()
    recs = _load_manifest(dest)["records"]
    out = {}
    for fam in CLIP_CHECK_FAMILIES:
        src = f"{fam}_SP"
        ok = [
            r
            for r in recs
            if r["source"] == src and r["status"] != "error" and date.fromisoformat(r["start"]).year == year
        ]
        err = [
            r
            for r in recs
            if r["source"] == src and r["status"] == "error" and date.fromisoformat(r["start"]).year == year
        ]
        out[src] = {
            "chunks_ok": len(ok),
            "days_ok": sum(r["days"] for r in ok),
            "chunks_error": len(err),
            "rows": sum(r["rows"] or 0 for r in ok),
        }
    return out


def render_report(checks: list[SatelliteCheck], coverage: dict[str, dict], year: int, geom_sha: str) -> str:
    verdict = all(c.ok for c in checks)
    L = [
        "# SA1.6 clip check (P7): FIRMS area API vs country files",
        "",
        f"Generated by `firecal firms clip-check` on {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}. "
        "Do not edit by hand.",
        "",
        f"**Result: {'PASS' if verdict else 'FAIL'}** (pre-registered P7, Revision 1).",
        "",
        "## Method",
        "",
        f"- API-SP {year} (MODIS_SP, VIIRS_SNPP_SP, VIIRS_NOAA20_SP; bbox of the ADM2 union padded "
        f"{BBOX_PAD} deg; 5-day chunks) clipped to the union of the geoBoundaries ADM2 polygons "
        f"(sha256 `{geom_sha[:12]}`), against the {year} country files "
        "(`product={p}/year={y}`, FIRMS per-country files).",
        "- Match as a multiset per satellite on (acq_datetime, satellite, lat and lon rounded to 4 "
        "decimals); duplicate keys count once per copy.",
        "- Distance of every unmatched row to the boundary of the Argentina union: local equirectangular "
        f"approximation (R = {EARTH_RADIUS_KM} km), nearest boundary segment in a 0.2 deg window.",
        "- Criteria, per satellite and per direction: unmatched under "
        f"{P7['max_unmatched_pct']} % of country rows; at least {P7['min_within_share']:.0%} of the "
        "unmatched "
        f"within {P7['within_km']:g} km of the boundary; unmatched farther than {P7['within_km']:g} km under "
        f"{P7['max_far_pct']} % of country rows. A direction with no unmatched rows passes vacuously.",
        "- NOAA-21 has no country files: its clip is unverified (same code path only).",
        "",
        "## Chunk coverage (manifest)",
        "",
        "| source | chunks ok | days ok | chunks with error | rows |",
        "|---|---|---|---|---|",
    ]
    for s, v in coverage.items():
        L.append(f"| {s} | {v['chunks_ok']} | {v['days_ok']} | {v['chunks_error']} | {v['rows']} |")
    L += [
        "",
        "## Result per satellite",
        "",
        "| satellite | country rows | API rows | matched | country-only | % | API-only | % | pass |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in checks:
        L.append(
            f"| {c.satellite} | {c.country_rows} | {c.api_rows} | {c.matched} | {c.country_only.unmatched} | "
            f"{c.country_only.pct_of_country:.4f} | {c.api_only.unmatched} | "
            f"{c.api_only.pct_of_country:.4f} | "
            f"{'yes' if c.ok else 'NO'} |"
        )
    L += [
        "",
        "## Unmatched rows and distance to the boundary",
        "",
        "| satellite | direction | unmatched | within 5 km | share | farther | % of country | median km | "
        "max km | pass |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in checks:
        for name, st in (("country-only", c.country_only), ("API-only", c.api_only)):
            med = f"{st.median_km:.2f}" if st.median_km is not None else "-"
            mx = f"{st.max_km:.2f}" if st.max_km is not None else "-"
            L.append(
                f"| {c.satellite} | {name} | {st.unmatched} | {st.within_5km} | {st.within_share:.3f} | "
                f"{st.far} | {st.far_pct_of_country:.4f} | {med} | {mx} | {'yes' if st.ok else 'NO'} |"
            )
    L += ["", "Country-only: in the country file, not in the clipped API data. API-only: the reverse.", ""]
    return "\n".join(L)


def write_clip_report(out: Path | None = None, year: int = 2025) -> tuple[Path, list[SatelliteCheck]]:
    out = out or REPO_ROOT / "reports" / "01" / "SA1.6_clip.md"
    geom, sha = load_argentina()
    checks = clip_check(year=year, geom=geom)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(checks, coverage_from_manifest(year=year), year, sha))
    return out, checks


def group_summary(results: list[ChunkResult]) -> dict[tuple[str, str], int]:
    d: dict[tuple[str, str], int] = defaultdict(int)
    for r in results:
        d[(r.source, r.status)] += 1
    return dict(d)
