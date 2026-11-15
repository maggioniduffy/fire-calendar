from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from firecal.layers.manifest import LayerManifest
from firecal.stages.calendar.store import SeriesStore


def row(year, month, lat, lon, mr=np.nan, vr=np.nan, me=0.0, ve=0.0, mest=False, vest=False):
    return {
        "year": year, "month": month, "cell_id": int(abs(lat) * 1000 + abs(lon) * 10),
        "cell_lat": lat, "cell_lon": lon, "modis_reported": mr, "viirs_reported": vr,
        "modis_eq": me, "viirs_eq": ve, "modis_eq_estimated": mest, "viirs_eq_estimated": vest,
        "modis_sats": "terra", "viirs_source": "snpp", "method": "scale_factor",
        "calibration_version": "t1",
    }  # fmt: skip


def make_layer(root: Path, rows: list[dict], period="2011-11-01/2012-02-29") -> Path:
    df = pd.DataFrame(rows)
    (root / "series").mkdir(parents=True)
    for y, g in df.groupby("year"):
        g.to_parquet(root / "series" / f"{y}.parquet")
    (root / "manifest.json").write_text(
        LayerManifest(
            id="harmonized", title="t", kind="series", source="src", period=period, license="x",
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            files=[f"series/{y}.parquet" for y in sorted(df["year"].unique())],
            method="scale_factor", calibration_version="t1", notes={"es": ["a"], "en": ["b"]},
        ).model_dump_json()
    )  # fmt: skip
    return root


ROWS = [
    row(2011, 11, -31.0, -64.0, mr=2, me=2, ve=1.0, vest=True),
    row(2011, 12, -31.0, -64.0, mr=3, me=3, ve=1.5, vest=True),
    row(2011, 12, -40.0, -60.0, mr=5, me=5, ve=2.5, vest=True),
    row(2012, 1, -31.0, -64.0, mr=1, vr=2, me=1, ve=2),
    row(2012, 1, -31.2, -64.2, mr=4, vr=1, me=4, ve=1),
    # 2012-02 absent: no rows at all
]


def test_load_area_bbox_mask_and_months(tmp_path):
    store = SeriesStore(make_layer(tmp_path / "h", ROWS))
    bbox = (-35.0, -30.0, -70.0, -60.0)
    df = store.load_area(bbox, None, (2011, 11), (2012, 1))
    assert len(df) == 4  # -40/-60 outside bbox
    df = store.load_area(bbox, None, (2011, 12), (2012, 1))
    assert len(df) == 3
    mask = lambda lat, lon: lat > -31.1  # noqa: E731
    df = store.load_area(bbox, mask, (2011, 11), (2012, 1))
    assert len(df) == 3 and (df["cell_lat"] > -31.1).all()
    assert store.load_area(bbox, None, (2015, 1), (2015, 2)).empty


def test_coverage_flags(tmp_path):
    store = SeriesStore(make_layer(tmp_path / "h", ROWS))
    cov = store.coverage().set_index(["year", "month"])
    assert len(cov) == 4
    assert bool(cov.loc[(2011, 11), "modis_available"]) and not cov.loc[(2011, 11), "viirs_available"]
    assert cov.loc[(2011, 11), "viirs_eq_estimated"] and not cov.loc[(2011, 11), "modis_eq_estimated"]
    assert cov.loc[(2012, 1), "viirs_available"] and not cov.loc[(2012, 1), "viirs_eq_estimated"]
    assert not cov.loc[(2012, 2)].any()
    assert store.coverage() is store.coverage()


def test_meta_and_bands(tmp_path):
    root = make_layer(tmp_path / "h", ROWS)
    bm = pd.DataFrame(
        {"year": [2011, 2011], "month": [12, 12], "block": [1, 2], "target": "viirs_eq",
         "estimate": [1.0, 2.0], "lo": [0.5, 1.0], "hi": [2.0, 3.0]}
    )  # fmt: skip
    (root / "band_block_month").mkdir()
    bm.to_parquet(root / "band_block_month" / "2011.parquet")
    store = SeriesStore(root)
    meta = store.meta()
    assert meta["source"] == "src" and meta["notes"]["es"] == ["a"] and meta["layer"] == "harmonized"
    assert meta["method"] == "scale_factor" and meta["calibration_version"] == "t1"
    assert len(store.load_bands([1], (2011, 1), (2012, 1), "month")) == 1
    assert store.load_bands([1], (2011, 1), (2012, 1), "year").empty
