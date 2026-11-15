import json
from datetime import UTC, date, datetime

import httpx
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from firecal.io import firms_area as fa
from firecal.io.firms import read_firms_csv

KEY = "SECRETKEY123"
BBOX = (-74.0, -56.0, -52.0, -21.0)
VIIRS_HEADER = fa.VIIRS_COLS
MODIS_HEADER = fa.MODIS_COLS


def viirs_csv(rows, type_col=False, sat="N21", version="2.0NRT"):
    head = VIIRS_HEADER + (",type" if type_col else "")
    lines = [head]
    for lat, lon, d, t in rows:
        line = f"{lat},{lon},300.1,0.4,0.4,{d},{t},{sat},VIIRS,n,{version},280.0,2.5,D"
        lines.append(line + (",0" if type_col else ""))
    return ("\n".join(lines) + "\n").encode()


def make_client(handler):
    calls = []

    def wrapped(request):
        calls.append(str(request.url))
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped)), calls


def clock(day=(2026, 11, 15)):
    return lambda: datetime(*day, 12, 0, 0, tzinfo=UTC)


def download(tmp_path, client, plan, **kw):
    return fa.download_area(
        plan, BBOX, KEY, dest=tmp_path, client=client, sleep=lambda s: None, workers=1, **kw
    )


def plan_for(source, start, end):
    return [fa.PlanItem(source, date.fromisoformat(start), date.fromisoformat(end))]


# ---------------------------------------------------------------- chunking


def test_chunk_ranges_cover_every_day_once():
    ch = fa.chunk_ranges(date(2026, 1, 1), date(2026, 1, 12))
    assert ch == [(date(2026, 1, 1), 5), (date(2026, 1, 6), 5), (date(2026, 1, 11), 2)]
    assert sum(n for _, n in ch) == 12
    year = fa.chunk_ranges(*fa.CLIP_CHECK_RANGE)
    assert len(year) == 73 and all(n == 5 for _, n in year)
    assert fa.chunk_ranges(date(2026, 1, 3), date(2026, 1, 3)) == [(date(2026, 1, 3), 1)]


def test_url_format_and_bbox_padding():
    url = fa.area_url("K", "MODIS_SP", (-73.6166, -55.1135, -53.5874, -21.7311), date(2025, 6, 10), 5)
    assert url == f"{fa.API}/area/csv/K/MODIS_SP/-73.6166,-55.1135,-53.5874,-21.7311/5/2025-06-10"
    g = box(-70, -40, -60, -30)
    assert fa.bbox_from_geometry(g) == (-70.05, -40.05, -59.95, -29.95)


AVAIL = {
    "MODIS_SP": (date(2000, 11, 1), date(2026, 8, 31)),
    "MODIS_NRT": (date(2026, 9, 1), date(2026, 11, 15)),
    "VIIRS_SNPP_SP": (date(2012, 1, 20), date(2026, 7, 31)),
    "VIIRS_SNPP_NRT": (date(2026, 8, 1), date(2026, 11, 2)),
    "VIIRS_NOAA20_SP": (date(2018, 4, 1), date(2026, 7, 31)),
    "VIIRS_NOAA20_NRT": (date(2026, 8, 1), date(2026, 11, 15)),
    "VIIRS_NOAA21_SP": (date(2023, 3, 1), date(2026, 7, 31)),
    "VIIRS_NOAA21_NRT": (date(2024, 1, 17), date(2026, 11, 15)),
}


def test_default_plan_bounds():
    plan = {p.source: (p.start, p.end) for p in fa.build_plan(AVAIL, date(2026, 11, 15))}
    assert plan["MODIS_SP"] == (date(2026, 1, 1), date(2026, 8, 31))
    assert plan["MODIS_NRT"] == (date(2026, 9, 1), date(2026, 11, 15))
    assert plan["VIIRS_SNPP_NRT"] == (date(2026, 8, 1), date(2026, 11, 2))
    assert plan["VIIRS_NOAA21_SP"] == (date(2023, 3, 1), date(2026, 7, 31))
    assert plan["VIIRS_NOAA21_NRT"] == (date(2026, 8, 1), date(2026, 11, 15))


def test_clip_check_plan_and_source_selection():
    plan = fa.build_plan(AVAIL, date(2026, 11, 15), clip_check_only=True)
    assert {(p.source, p.start, p.end) for p in plan} == {
        (f"{f}_SP", date(2025, 1, 1), date(2025, 12, 31)) for f in fa.CLIP_CHECK_FAMILIES
    }
    only = fa.build_plan(AVAIL, date(2026, 11, 15), sources=["VIIRS_NOAA21"])
    assert {p.source for p in only} == {"VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"}
    with pytest.raises(ValueError):
        fa.select_sources(["NOPE"])


# ---------------------------------------------------------------- download


def test_idempotent_sp_and_manifest(tmp_path):
    body = viirs_csv([(-30.0, -60.0, "2026-03-01", 130)], type_col=True, version="2.0")
    client, calls = make_client(lambda r: httpx.Response(200, content=body))
    plan = plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-10")
    r1 = download(tmp_path, client, plan, now=clock())
    assert [r.status for r in r1] == ["downloaded", "downloaded"] and len(calls) == 2
    assert (tmp_path / "VIIRS_NOAA21_SP" / "2026-03-01_5.csv.sha256").exists()
    r2 = download(tmp_path, client, plan, now=clock())
    assert [r.status for r in r2] == ["skipped", "skipped"] and len(calls) == 2
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert {(r["start"], r["status"], r["rows"]) for r in m["records"]} == {
        ("2026-03-01", "skipped", 1),
        ("2026-03-06", "skipped", 1),
    }
    # a corrupted chunk is fetched again
    (tmp_path / "VIIRS_NOAA21_SP" / "2026-03-01_5.csv").write_bytes(b"junk")
    r3 = download(tmp_path, client, plan, now=clock())
    assert [r.status for r in r3] == ["downloaded", "skipped"]


def test_request_covers_forward_5_days(tmp_path):
    client, calls = make_client(lambda r: httpx.Response(200, content=viirs_csv([])))
    download(tmp_path, client, plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-03"))
    assert calls[0].endswith("/VIIRS_NOAA21_SP/-74,-56,-52,-21/3/2026-03-01")


def test_nrt_archive_and_refresh(tmp_path):
    body1 = viirs_csv([(-30.0, -60.0, "2026-11-10", 130)])
    body2 = viirs_csv([(-30.0, -60.0, "2026-11-10", 130), (-31.0, -61.0, "2026-11-11", 200)])
    bodies = [body1, body2]
    client, calls = make_client(lambda r: httpx.Response(200, content=bodies[min(len(calls), 2) - 1]))
    plan = plan_for("VIIRS_NOAA21_NRT", "2026-11-10", "2026-11-14")
    download(tmp_path, client, plan, now=clock((2026, 11, 15)))
    assert len(calls) == 1
    # end is within 7 days of the fetch: fetched again, and both fetches stay archived
    download(tmp_path, client, plan, now=lambda: datetime(2026, 11, 16, 8, tzinfo=UTC))
    assert len(calls) == 2
    arch = sorted((tmp_path / "archive" / "VIIRS_NOAA21_NRT").glob("*/2026-11-10_5.csv"))
    assert [p.read_bytes() for p in arch] == [body1, body2]
    # ingest reads the latest archive
    ((_, _, path),) = fa._chunks_for(fa.SOURCES["VIIRS_NOAA21_NRT"], tmp_path)
    assert path == arch[-1]
    # a chunk fetched long after its end is not fetched again
    old = plan_for("VIIRS_NOAA21_NRT", "2026-10-01", "2026-10-05")
    download(tmp_path, client, old, now=clock((2026, 11, 15)))
    n = len(calls)
    download(tmp_path, client, old, now=clock((2026, 11, 15)))
    assert len(calls) == n


# ---------------------------------------------------------------- invalid bodies and key


@pytest.mark.parametrize(
    "body",
    [b"Invalid MAP_KEY.", b"<html>error</html>", b"", b"latitude,longitude\n1,2\n"],
)
def test_non_csv_body_is_error_not_data(tmp_path, body):
    client, _ = make_client(lambda r: httpx.Response(200, content=body))
    (res,) = download(tmp_path, client, plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-05"))
    assert res.status == "error" and res.rows is None
    assert not (tmp_path / "VIIRS_NOAA21_SP" / "2026-03-01_5.csv").exists()


def test_header_only_body_is_valid_zero_rows(tmp_path):
    client, _ = make_client(lambda r: httpx.Response(200, content=viirs_csv([])))
    (res,) = download(tmp_path, client, plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-05"))
    assert res.status == "downloaded" and res.rows == 0


def test_key_never_stored_or_in_errors(tmp_path):
    def boom(request):
        raise httpx.ConnectError(f"reset while calling {request.url}")

    client, _ = make_client(boom)
    (res,) = download(tmp_path, client, plan_for("MODIS_SP", "2026-03-01", "2026-03-05"), retries=2)
    assert res.status == "error"
    assert KEY not in (res.detail or "") and KEY not in (res.url or "")
    assert "***" in res.url
    ok_client, _ = make_client(lambda r: httpx.Response(200, content=viirs_csv([])))
    download(tmp_path, ok_client, plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-05"))
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert KEY.encode() not in f.read_bytes()


def test_retries_then_succeeds(tmp_path):
    n = {"i": 0}

    def flaky(request):
        n["i"] += 1
        if n["i"] < 3:
            raise httpx.ReadError("connection reset")
        return httpx.Response(200, content=viirs_csv([]))

    client, _ = make_client(flaky)
    (res,) = download(tmp_path, client, plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-05"))
    assert res.status == "downloaded" and n["i"] == 3


def test_http_error_is_error(tmp_path):
    client, _ = make_client(lambda r: httpx.Response(403, content=b"nope"))
    (res,) = download(tmp_path, client, plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-05"))
    assert res.status == "error" and res.detail.startswith("HTTP 403")


def test_transaction_limit_waits_then_succeeds(tmp_path):
    n = {"i": 0}
    waits = []

    def limited(request):
        n["i"] += 1
        if n["i"] <= 2:
            return httpx.Response(400, content=b"Exceeding allowed transaction limit.")
        return httpx.Response(200, content=viirs_csv([]))

    client, _ = make_client(limited)
    (res,) = fa.download_area(
        plan_for("VIIRS_NOAA21_SP", "2026-03-01", "2026-03-05"),
        BBOX,
        KEY,
        dest=tmp_path,
        client=client,
        sleep=waits.append,
        workers=1,
    )
    assert res.status == "downloaded" and waits == [fa.LIMIT_WAIT_S] * 2


def test_availability_parse():
    body = b"data_id,min_date,max_date\nMODIS_SP,2000-11-01,2026-08-31\n"
    client, calls = make_client(lambda r: httpx.Response(200, content=body))
    av = fa.fetch_availability(client, KEY, sleep=lambda s: None)
    assert av == {"MODIS_SP": (date(2000, 11, 1), date(2026, 8, 31))}
    assert calls[0].endswith(f"/api/data_availability/csv/{KEY}/ALL")


# ---------------------------------------------------------------- parsing


def test_nrt_parse_without_type_and_n21_mapping(tmp_path):
    p = tmp_path / "c.csv"
    p.write_bytes(viirs_csv([(-30.0, -60.0, "2026-11-10", 351)], version="2.0NRT"))
    df = read_firms_csv(p, "viirs-jpss2")
    assert df["satellite"].tolist() == ["noaa21"]
    assert df["type"].isna().all() and str(df["type"].dtype) == "Int8"
    assert df["version"].tolist() == ["2.0NRT"]
    assert df["acq_datetime"].iloc[0] == pd.Timestamp("2026-11-10 03:51", tz="UTC")


def test_modis_nrt_parse_version(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(
        MODIS_HEADER + "\n-30.1,-60.2,330.1,1.0,1.0,2026-09-02,1830,Aqua,MODIS,75,6.1NRT,300.0,12.5,D\n"
    )
    df = read_firms_csv(p, "modis")
    assert df["satellite"].tolist() == ["aqua"] and df["type"].isna().all()
    assert df["confidence_pct"].tolist() == [75]


def test_satellite_column_checked(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(viirs_csv([(-30.0, -60.0, "2026-11-10", 351)], sat="N20"))
    with pytest.raises(ValueError):
        fa._check_satellites(p, fa.SOURCES["VIIRS_NOAA21_NRT"])


# ---------------------------------------------------------------- clip, dedupe, ingest


def test_clip_on_toy_polygon():
    geom = box(-60, -35, -58, -33)
    df = pd.DataFrame(
        {"latitude": [-34, -34, -40, -33.5], "longitude": [-59, -50, -59, -58.5], "x": [1, 2, 3, 4]}
    )
    out = fa.clip_inside(df, geom)
    assert out["x"].tolist() == [1, 4]


def test_ingest_dedupes_across_chunks_keeps_within_chunk_duplicates(tmp_path):
    row = (-30.0, -60.0, "2026-03-02", 130)
    other = (-31.0, -61.0, "2026-03-02", 140)
    d = tmp_path / "VIIRS_NOAA21_SP"
    d.mkdir()
    # two copies of `row` inside one chunk (legit duplicate key) and an overlapping chunk repeating them
    (d / "2026-03-01_5.csv").write_bytes(viirs_csv([row, row, other], type_col=True, version="2.0"))
    (d / "2026-03-02_5.csv").write_bytes(
        viirs_csv([row, row, (-32.0, -62.0, "2026-03-04", 100)], True, version="2.0")
    )
    # an NRT-shaped chunk is separate source; here only SP
    df, shas = fa.read_source(fa.SOURCES["VIIRS_NOAA21_SP"], tmp_path)
    assert len(df) == 4 and len(shas) == 2
    assert df["type"].tolist() == [0, 0, 0, 0]


def test_area_ingest_writes_partitions_with_metadata(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    d = raw / "VIIRS_NOAA21_NRT"
    d.mkdir(parents=True)
    rows = [
        (-34.0, -59.0, "2026-11-10", 351),
        (-34.0, -50.0, "2026-11-10", 400),
        (-34.5, -58.5, "2026-12-31", 100),
    ]
    (d / "2026-11-10_5.csv").write_bytes(viirs_csv(rows))
    rep = fa.area_ingest(raw=raw, out=out, geom=box(-60, -35, -58, -33), geom_sha="abc", levels=["nrt"])
    assert [(r["product"], r["level"], r["year"], r["rows"]) for r in rep] == [
        ("viirs-jpss2", "nrt", 2026, 2)
    ]
    import pyarrow.parquet as pq

    f = out / "product=viirs-jpss2" / "level=nrt" / "year=2026" / "part-0.parquet"
    meta = pq.read_schema(f).metadata
    assert meta[b"clip_rows_dropped"] == b"1"
    assert json.loads(meta[b"source_ids"]) == ["VIIRS_NOAA21_NRT"]
    assert list(json.loads(meta[b"chunk_sha256"])) == ["VIIRS_NOAA21_NRT/2026-11-10_5.csv"]
    t = pq.read_table(f).to_pandas()
    assert t["satellite"].tolist() == ["noaa21", "noaa21"] and t["type"].isna().all()


# ---------------------------------------------------------------- P7 matching


def frame(rows):
    return pd.DataFrame(
        {
            "satellite": "snpp",
            "acq_datetime": pd.to_datetime([r[0] for r in rows], utc=True),
            "latitude": [r[1] for r in rows],
            "longitude": [r[2] for r in rows],
        }
    )


def test_multiset_match_counts_duplicates_and_rounding():
    t = "2025-01-01 03:00"
    country = frame([(t, -30.00001, -60.0), (t, -30.00001, -60.0), (t, -31.0, -61.0), (t, -32.0, -62.0)])
    api = frame([(t, -30.00004, -60.0), (t, -31.0, -61.0), (t, -31.0, -61.0), (t, -33.0, -63.0)])
    only_c, only_a, matched = fa.multiset_diff(country, api)
    assert matched == 2  # one of the two -30 copies, one -31
    assert only_c["n"].sum() == 2 and only_a["n"].sum() == 2
    assert sorted(only_c["latitude"].round(1).tolist()) == [-32.0, -30.0]
    assert sorted(only_a["latitude"].round(1).tolist()) == [-33.0, -31.0]


def test_boundary_distance_km():
    geom = box(-60, -35, -58, -33)
    dist = fa.BoundaryDistance(geom)
    # 0.05 deg of latitude south of the southern edge is about 5.56 km
    assert dist.one(-59.0, -35.05) == pytest.approx(5.56, abs=0.05)
    # inside, 1 deg of longitude from the west edge at lat -34 is about 92 km
    assert dist.one(-59.0, -34.0) == pytest.approx(92.2, abs=1.0)
    far = dist.many(np.array([-59.0]), np.array([-30.0]))
    assert far[0] == pytest.approx(3 * 111.19, abs=1.0)  # 3 deg north of the northern edge


def test_direction_stats_verdict():
    geom = box(-60, -35, -58, -33)
    dist = fa.BoundaryDistance(geom)
    near = pd.DataFrame({"latitude": [-35.01], "longitude": [-59.0], "n": [1]})
    st = fa.direction_stats(near, 10000, dist)
    assert st.within_5km == 1 and st.ok
    far = pd.DataFrame({"latitude": [-36.0], "longitude": [-59.0], "n": [20]})
    st = fa.direction_stats(far, 10000, dist)
    assert st.far == 20 and not st.ok  # 0.2 % > 0.05 %
    many = pd.DataFrame({"latitude": [-35.01], "longitude": [-59.0], "n": [150]})
    assert not fa.direction_stats(many, 10000, dist).ok  # 1.5 % > 1 %
    assert fa.direction_stats(near.iloc[0:0], 10, dist).ok
