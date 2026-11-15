"""SA1.6 grid source precedence (country-sp > api-sp > nrt, never summed) and the NRT mask in the grid."""

from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.stages.grid import build_grid
from firecal.stages.grid.grid import choose_levels, level_files
from firecal.stages.grid.nrt_mask import FamilyMask, NrtMask


def rows(sat, sensor, d, n, level, lat=-31.42, lon=-64.32, typ=0, dn="D", conf="high"):
    out = []
    for i in range(n):
        out.append(
            {
                "sensor": sensor,
                "satellite": sat,
                "product": "modis" if sensor == "modis" else "viirs-snpp",
                "acq_date": date.fromisoformat(d),
                "year": int(d[:4]),
                "daynight": dn,
                "latitude": lat + i * 0.0001,
                "longitude": lon,
                "confidence_pct": 80 if sensor == "modis" else pd.NA,
                "confidence_class": conf,
                "frp": 1.0,
                "type": typ if typ is not None else pd.NA,
            }
        )
    return out


def write(root, product, level, year, recs):
    p = root / f"product={product}"
    if level != "country-sp":
        p = p / f"level={level}"
    p = p / f"year={year}" / "part-0.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(recs)
    df["confidence_pct"] = df["confidence_pct"].astype("Int16")
    df["type"] = df["type"].astype("Int8")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), p)


def test_level_files_finds_country_and_area(tmp_path):
    write(tmp_path, "modis", "country-sp", 2025, rows("terra", "modis", "2025-01-01", 1, "x"))
    write(tmp_path, "modis", "api-sp", 2025, rows("terra", "modis", "2025-01-01", 1, "x"))
    write(tmp_path, "modis", "nrt", 2026, rows("terra", "modis", "2026-11-01", 1, "x", typ=None))
    found = level_files(tmp_path)
    assert sorted(lv for lv, _ in found[2025]) == ["api-sp", "country-sp"]
    assert [lv for lv, _ in found[2026]] == ["nrt"]


def test_choose_levels_one_source_per_satellite_month():
    df = pd.concat(
        [
            pd.DataFrame(rows("terra", "modis", "2025-01-05", 3, "country-sp")).assign(level="country-sp"),
            pd.DataFrame(rows("terra", "modis", "2025-01-05", 3, "api-sp")).assign(level="api-sp"),
            pd.DataFrame(rows("terra", "modis", "2025-02-05", 2, "api-sp")).assign(level="api-sp"),
            pd.DataFrame(rows("terra", "modis", "2025-02-06", 5, "nrt", typ=None)).assign(level="nrt"),
            pd.DataFrame(rows("aqua", "modis", "2025-02-06", 4, "nrt", typ=None)).assign(level="nrt"),
        ],
        ignore_index=True,
    )
    out = choose_levels(df)
    got = out.groupby(["satellite", pd.to_datetime(out["acq_date"]).dt.month, "level"]).size().to_dict()
    assert got == {("terra", 1, "country-sp"): 3, ("terra", 2, "api-sp"): 2, ("aqua", 2, "nrt"): 4}


def counts(grid_dir):
    g = pq.read_table(grid_dir).to_pandas()
    return g


def test_build_grid_precedence_equivalence_and_noaa21(tmp_path):
    det_a = tmp_path / "a"  # country files only
    det_b = tmp_path / "b"  # the same plus api-sp copies of 2025 and NOAA-21
    for det in (det_a, det_b):
        write(det, "modis", "country-sp", 2025, rows("terra", "modis", "2025-03-01", 4, "x"))
        write(det, "viirs-snpp", "country-sp", 2025, rows("snpp", "viirs", "2025-03-01", 3, "x"))
    write(det_b, "modis", "api-sp", 2025, rows("terra", "modis", "2025-03-01", 4, "x"))
    write(det_b, "viirs-snpp", "api-sp", 2025, rows("snpp", "viirs", "2025-03-01", 3, "x"))
    write(det_b, "viirs-jpss2", "api-sp", 2025, rows("noaa21", "viirs", "2025-03-01", 2, "x"))
    build_grid(det_a, tmp_path / "ga", 0.1, nrt_mask=NrtMask({}))
    build_grid(det_b, tmp_path / "gb", 0.1, nrt_mask=NrtMask({}))
    a, b = counts(tmp_path / "ga"), counts(tmp_path / "gb")
    key = ["acq_date", "satellite", "daynight", "cell_id", "count", "level"]
    old = b[b["satellite"] != "noaa21"][key].reset_index(drop=True)
    assert old.equals(a[key].reset_index(drop=True))
    assert set(a["level"]) == {"country-sp"}
    assert int(a["count"].sum()) == 7  # not 14: api-sp copies are not summed
    n21 = b[b["satellite"] == "noaa21"]
    assert list(n21["level"]) == ["api-sp"] and int(n21["count"].sum()) == 2


def test_build_grid_nrt_mask_and_failed_family(tmp_path):
    det = tmp_path / "d"
    lat, lon = -31.42, -64.32
    nrt = (
        rows("terra", "modis", "2026-11-01", 2, "x", typ=None, lat=lat, lon=lon)
        + rows("terra", "modis", "2026-11-01", 3, "x", typ=None, lat=lat + 1, lon=lon)  # in masked cell
        + rows("terra", "modis", "2026-11-01", 1, "x", typ=None, lat=lat + 2, lon=lon)
        + rows("snpp", "viirs", "2026-11-01", 4, "x", typ=None, lat=lat, lon=lon, conf="low")
        + rows("snpp", "viirs", "2026-11-01", 5, "x", typ=None, lat=lat, lon=lon)
    )
    write(det, "modis", "nrt", 2026, [r for r in nrt if r["sensor"] == "modis"])
    write(det, "viirs-snpp", "nrt", 2026, [r for r in nrt if r["sensor"] == "viirs"])
    from firecal.stages.grid.grid import cell_ids

    masked = cell_ids(np.array([lat + 1]), np.array([lon]), 0.02)
    mask = NrtMask(
        {
            "modis": FamilyMask("modis", True, 0.02, 2, np.sort(masked)),
            "viirs": FamilyMask("viirs", False, 0.02, 2, np.empty(0, dtype="int64")),
        }
    )
    build_grid(det, tmp_path / "g", 0.1, nrt_mask=mask)
    g = counts(tmp_path / "g")
    assert set(g["level"]) == {"nrt"}
    assert set(g["satellite"]) == {"terra"}  # VIIRS family not accepted: its NRT rows stay out
    assert int(g["count"].sum()) == 3  # 2 + 1, the 3 rows in the masked cell are removed


def test_build_grid_without_mask_keeps_nrt_out(tmp_path):
    det = tmp_path / "d"
    write(det, "modis", "country-sp", 2025, rows("terra", "modis", "2025-03-01", 2, "x"))
    write(det, "modis", "nrt", 2026, rows("terra", "modis", "2026-11-01", 2, "x", typ=None))
    from firecal.stages.grid import nrt_mask as nm

    assert nm.load_nrt_mask(tmp_path / "nothing") is None
    build_grid(det, tmp_path / "g", 0.1, nrt_mask=NrtMask({}))
    g = counts(tmp_path / "g")
    assert set(g["level"]) == {"country-sp"}
