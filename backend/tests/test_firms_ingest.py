import os
from datetime import UTC, date, datetime

import pyarrow.parquet as pq
import pytest

from firecal.io.firms import DETECTION_SCHEMA, ingest, read_firms_csv
from firecal.stages.grid.filters import FilterConfig, apply_filters

_COMMON = "scan,track,acq_date,acq_time,satellite,instrument,confidence,version"
MODIS_HDR = f"latitude,longitude,brightness,{_COMMON},bright_t31,frp,daynight,type"
VIIRS_HDR = f"latitude,longitude,bright_ti4,{_COMMON},bright_ti5,frp,daynight,type"


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n")
    return path


def test_modis(tmp_path):
    p = write(
        tmp_path / "m.csv",
        MODIS_HDR,
        [
            "-31.5,-64.2,330.5,1,1,2020-08-01,5,Terra,MODIS,10,6.1NRT,300,12.5,D,0",
            "-31.6,-64.3,340.0,1,1,2020-08-02,1830,Aqua,MODIS,30,6.1,300,20.0,N,2",
            "-31.7,-64.4,340.0,1,1,2020-08-02,1830,A,MODIS,80,6.1,300,1.0,N,0",
        ],
    )
    df = read_firms_csv(p, "modis")
    assert list(df.columns) == DETECTION_SCHEMA.names
    assert list(df["satellite"]) == ["terra", "aqua", "aqua"]
    assert set(df["sensor"]) == {"modis"}
    assert df["acq_datetime"].iloc[0] == datetime(2020, 8, 1, 0, 5, tzinfo=UTC)
    assert df["acq_datetime"].iloc[1] == datetime(2020, 8, 2, 18, 30, tzinfo=UTC)
    assert df["acq_date"].iloc[0] == date(2020, 8, 1)
    assert list(df["confidence_class"]) == ["low", "nominal", "high"]
    assert list(df["confidence_pct"]) == [10, 30, 80]
    assert list(df["confidence_raw"]) == ["10", "30", "80"]
    assert list(df["daynight"]) == ["D", "N", "N"]
    assert df["brightness"].dtype == "float32" and df["frp"].dtype == "float32"
    assert list(df["type"]) == [0, 2, 0]


def test_modis_confidence_boundaries(tmp_path):
    rows = [f"0,0,300,1,1,2020-01-01,100,Terra,MODIS,{c},6.1,300,1,D,0" for c in (0, 29, 30, 79, 80, 100)]
    df = read_firms_csv(write(tmp_path / "m.csv", MODIS_HDR, rows), "modis")
    assert list(df["confidence_class"]) == ["low", "low", "nominal", "nominal", "high", "high"]


def test_modis_unknown_satellite_raises(tmp_path):
    p = write(tmp_path / "m.csv", MODIS_HDR, ["0,0,300,1,1,2020-01-01,100,X,MODIS,50,6.1,300,1,D,0"])
    with pytest.raises(ValueError, match="satellite"):
        read_firms_csv(p, "modis")


@pytest.mark.parametrize(
    ("product", "satellite", "sat_col"),
    [("viirs-snpp", "snpp", "N"), ("viirs-jpss1", "noaa20", "1")],
)
def test_viirs(tmp_path, product, satellite, sat_col):
    rows = [
        f"-31.5,-64.2,345.1,0.4,0.4,2020-08-01,1,{sat_col},VIIRS,l,2.0NRT,290,1.5,D,0",
        f"-31.6,-64.3,350.1,0.4,0.4,2020-08-01,59,{sat_col},VIIRS,Nominal,2.0NRT,290,2.5,N,0",
        f"-31.7,-64.4,360.1,0.4,0.4,2020-08-01,2359,{sat_col},VIIRS,H,2.0NRT,290,3.5,N,3",
    ]
    df = read_firms_csv(write(tmp_path / "v.csv", VIIRS_HDR, rows), product)
    assert set(df["satellite"]) == {satellite} and set(df["sensor"]) == {"viirs"}
    assert set(df["product"]) == {product}
    assert list(df["confidence_class"]) == ["low", "nominal", "high"]
    assert df["confidence_pct"].isna().all()
    assert list(df["acq_datetime"].dt.strftime("%H:%M")) == ["00:01", "00:59", "23:59"]
    assert list(df["brightness"].round(1).astype("float64")) == pytest.approx([345.1, 350.1, 360.1], abs=0.01)


def test_missing_type_column(tmp_path):
    hdr = VIIRS_HDR.removesuffix(",type")
    p = write(tmp_path / "v.csv", hdr, ["0,0,300,1,1,2020-01-01,100,N,VIIRS,high,2.0,290,1,D"])
    assert read_firms_csv(p, "viirs-snpp")["type"].isna().all()


def test_ingest_writes_schema_and_is_idempotent(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    write(
        raw / "modis" / "modis_2020_Argentina.csv",
        MODIS_HDR,
        ["0,0,300,1,1,2020-01-01,100,Terra,MODIS,50,6.1,300,1,D,0"],
    )
    assert ingest(raw, out) == [("modis", 2020, "written")]
    f = out / "product=modis" / "year=2020" / "part-0.parquet"
    assert pq.read_schema(f).remove_metadata() == DETECTION_SCHEMA
    assert ingest(raw, out) == [("modis", 2020, "skipped")]
    # changed content (even with older mtime) is detected through the sha256
    csv = raw / "modis" / "modis_2020_Argentina.csv"
    csv.write_text(csv.read_text().replace(",50,", ",60,"))
    os.utime(csv, (1, 1))
    assert ingest(raw, out) == [("modis", 2020, "written")]
    assert pq.read_table(f).to_pandas()["confidence_pct"].iloc[0] == 60


def test_filters(tmp_path):
    rows_m = [
        "0,0,300,1,1,2020-01-01,100,Terra,MODIS,29,6.1,300,1,D,0",
        "0,0,300,1,1,2020-01-01,100,Terra,MODIS,30,6.1,300,1,D,0",
        "0,0,300,1,1,2020-01-01,100,Terra,MODIS,90,6.1,300,1,D,1",
        "0,0,300,1,1,2020-01-01,100,Terra,MODIS,90,6.1,300,1,D,3",
    ]
    rows_v = [
        "0,0,300,1,1,2020-01-01,100,N,VIIRS,l,2.0,290,1,D,0",
        "0,0,300,1,1,2020-01-01,100,N,VIIRS,n,2.0,290,1,D,0",
        "0,0,300,1,1,2020-01-01,100,N,VIIRS,h,2.0,290,1,D,2",
        "0,0,300,1,1,2020-01-01,100,N,VIIRS,h,2.0,290,1,D,0",
    ]
    import pandas as pd

    m = read_firms_csv(write(tmp_path / "m.csv", MODIS_HDR, rows_m), "modis")
    v = read_firms_csv(write(tmp_path / "v.csv", VIIRS_HDR, rows_v), "viirs-snpp")
    df = pd.concat([m, v], ignore_index=True)
    kept, drops = apply_filters(df, FilterConfig())
    assert drops == {"type": 3, "modis_confidence": 1, "viirs_confidence": 1}
    assert list(kept["confidence_raw"]) == ["30", "n", "h"]
    kept50, d50 = apply_filters(df, FilterConfig(modis_min_confidence=50))
    assert d50["modis_confidence"] == 2 and list(kept50["sensor"]).count("modis") == 0
    kept_h, dh = apply_filters(df, FilterConfig(viirs_classes=("high",)))
    assert dh["viirs_confidence"] == 2
    kept_t, dt = apply_filters(df, FilterConfig(types=(0, 1)))
    assert dt["type"] == 2


def test_missing_type_flag(tmp_path):
    hdr = VIIRS_HDR.removesuffix(",type")
    p = write(tmp_path / "v.csv", hdr, ["0,0,300,1,1,2020-01-01,100,N,VIIRS,high,2.0,290,1,D"])
    df = read_firms_csv(p, "viirs-snpp")
    assert len(apply_filters(df, FilterConfig())[0]) == 0
    assert len(apply_filters(df, FilterConfig(keep_missing_type=True))[0]) == 1
