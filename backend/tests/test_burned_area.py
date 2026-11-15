"""SA2.9 MCD64A1 burned area: sinusoidal geometry, aggregation, download, optional feature (no network)."""

import json
import math

import httpx
import numpy as np
import pandas as pd
import pytest
from test_harmonize_ml import SMALL, YEARS, setup, synth_grid

from firecal.io import burned_area as ba
from firecal.stages.grid.grid import cell_center, cell_ids, grid_shape
from firecal.stages.harmonize.ml import prepare, run_ml_cv
from firecal.stages.harmonize.ml_features import (
    BASE_FEATURES,
    BURNED_FEATURES,
    build_cell_rows,
    monthly_cell_table,
)


def test_pixel_area_is_the_modis_500m_pixel():
    assert pytest.approx(463.3127, abs=1e-4) == ba.PIX_M
    assert pytest.approx(0.2146, abs=1e-4) == ba.PIXEL_AREA_KM2


def test_tile_corners_on_the_sinusoidal_grid():
    # Tile v=9 starts at the equator and h=18 at the prime meridian.
    lat, lon = ba.pixel_centers(18, 9, np.array([0]), np.array([0]))
    assert lat[0] == pytest.approx(-(0.5 * ba.PIX_M) / ba.EARTH_R * 180 / math.pi)
    assert lat[0] < 0 and lat[0] > -0.01
    assert lon[0] == pytest.approx(0.5 * ba.PIX_M / ba.EARTH_R * 180 / math.pi, rel=1e-6)
    # Top row of v=0 sits just under the pole; bottom row of v=17 just above the south pole.
    top, _ = ba.pixel_centers(18, 0, np.array([0]), np.array([0]))
    bottom, _ = ba.pixel_centers(18, 17, np.array([ba.N_PIX - 1]), np.array([0]))
    assert 89.99 < top[0] < 90 and -90 < bottom[0] < -89.99


def test_tile_h12v12_covers_cordoba():
    rows, cols = np.meshgrid([0, ba.N_PIX - 1], [0, ba.N_PIX - 1], indexing="ij")
    lat, lon = ba.pixel_centers(12, 12, rows.ravel(), cols.ravel())
    # v=12 spans -30..-40 degrees of latitude (10 degrees = one tile on the meridian).
    assert lat.min() == pytest.approx(-40, abs=0.01) and lat.max() == pytest.approx(-30, abs=0.01)
    assert lon.min() < -64.2 < lon.max()  # Cordoba city (-31.4, -64.2) is in this tile


def test_known_point_round_trip():
    """Forward projection of (-31.4, -64.2) lands in tile h12v12, within half a pixel of a pixel centre."""
    lat0, lon0 = -31.4, -64.2
    x = ba.EARTH_R * math.radians(lon0) * math.cos(math.radians(lat0))
    y = ba.EARTH_R * math.radians(lat0)
    h = int((x - ba.X_MIN) // ba.TILE_M)
    v = int((ba.Y_MAX - y) // ba.TILE_M)
    col = int((x - ba.X_MIN - h * ba.TILE_M) // ba.PIX_M)
    row = int((ba.Y_MAX - y - v * ba.TILE_M) // ba.PIX_M)
    assert (h, v) == (12, 12)
    lat, lon = ba.pixel_centers(h, v, np.array([row]), np.array([col]))
    assert (
        abs(lat[0] - lat0) < 0.005 and abs(lon[0] - lon0) < 0.006
    )  # half a pixel: 0.0021 deg lat, wider in lon


def test_parse_title():
    assert ba.parse_title("MCD64A1.A2020245.h12v12.061.2021309112048") == (2020, 9, 245, 12, 12)
    assert ba.parse_title("MCD64A1.A2000306.h11v11.061.2021307220158")[:2] == (2000, 11)
    assert ba.parse_title("MCD64A1.A2024061.h12v12.061.x")[:2] == (2024, 3)  # leap year: DOY 61 = 1 March


def test_aggregate_counts_pixels_per_cell_and_month():
    lat = np.array([-31.42, -31.43, -31.44, -31.52, -31.42])
    lon = np.array([-64.18, -64.17, -64.19, -64.18, -64.18])
    burned = np.array([True, True, False, True, False])
    unm = np.array([False, False, True, False, False])
    out = ba.aggregate_cells(lat, lon, burned, unm, ym=2020 * 12 + 8)
    cid = cell_ids(lat, lon, 0.1)
    assert cid[0] == cid[1] == cid[2] != cid[3]
    a = out[out["cell_id"] == cid[0]].iloc[0]
    assert (a["burned_px"], a["unmapped_px"]) == (2, 1)
    assert a["burned_km2"] == pytest.approx(2 * ba.PIXEL_AREA_KM2)
    assert out[out["cell_id"] == cid[3]].iloc[0]["burned_px"] == 1
    assert (out["ym"] == 2020 * 12 + 8).all() and cid[4] == cid[0]
    assert out["burned_px"].sum() == 3  # the unburned, mapped pixel is not in the output


def test_aggregate_empty():
    out = ba.aggregate_cells(np.empty(0), np.empty(0), np.empty(0, bool), np.empty(0, bool), 24000)
    assert len(out) == 0 and list(out.columns) == [f.name for f in ba.OUT_SCHEMA]


def test_grid_tile_clips_and_counts(tmp_path, monkeypatch):
    import shapely

    burn = np.zeros((ba.N_PIX, ba.N_PIX), dtype=np.int16)
    burn[100, 100:110] = 250  # ten burned pixels
    burn[200, 200] = ba.UNMAPPED
    burn[300, 300] = ba.WATER
    monkeypatch.setattr(ba, "read_burn_date", lambda p: burn)
    name = "MCD64A1.A2020245.h12v12.061.2021309112048.hdf"
    everywhere = shapely.box(-180, -90, 180, 90)
    out = ba.grid_tile(tmp_path / name, everywhere)
    assert out["burned_px"].sum() == 10 and out["unmapped_px"].sum() == 1
    assert (out["ym"] == 2020 * 12 + 8).all()
    nowhere = shapely.box(0, 0, 1, 1)
    assert len(ba.grid_tile(tmp_path / name, nowhere)) == 0
    # The cell of every output row contains the pixel centres it counted (same cell_ids as the FIRMS grid).
    lat, lon = ba.pixel_centers(12, 12, np.array([100]), np.array([100]))
    assert cell_ids(lat, lon, 0.1)[0] in set(out["cell_id"])


def _transport(files: dict[str, bytes], calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        body = files.get(request.url.path.rsplit("/", 1)[-1])
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler)


def test_download_is_idempotent_and_writes_manifest(tmp_path):
    g1 = ba.Granule("MCD64A1.A2020245.h12v12.061.1", "https://x.test/p/a.hdf", 2020, 9, 12, 12)
    g2 = ba.Granule("MCD64A1.A2020245.h12v13.061.2", "https://x.test/p/b.hdf", 2020, 9, 12, 13)
    calls: list = []
    tr = _transport({"a.hdf": b"AAAA", "b.hdf": b"BBBBBB"}, calls)

    def factory():
        return httpx.Client(transport=tr, follow_redirects=True)

    c = ba.download_granules([g1, g2], tmp_path, workers=2, client_factory=factory, sleep=lambda s: None)
    assert c == {"downloaded": 2, "skipped": 0, "error": 0}
    man = json.loads((tmp_path / "manifest.json").read_text())
    rec = man["granules"][g1.title]
    assert rec["bytes"] == 4 and rec["sha256"] == ba.sha256_file(tmp_path / rec["file"])
    n = len(calls)
    c2 = ba.download_granules([g1, g2], tmp_path, workers=2, client_factory=factory, sleep=lambda s: None)
    assert c2 == {"downloaded": 0, "skipped": 2, "error": 0} and len(calls) == n
    # A corrupted file is caught with verify and fetched again.
    (tmp_path / rec["file"]).write_bytes(b"ZZZZ")
    c3 = ba.download_granules([g1], tmp_path, client_factory=factory, verify=True, sleep=lambda s: None)
    assert c3["downloaded"] == 1 and (tmp_path / rec["file"]).read_bytes() == b"AAAA"


def test_download_retries_server_errors_then_reports_error(tmp_path):
    g = ba.Granule("MCD64A1.A2020245.h12v12.061.1", "https://x.test/p/a.hdf", 2020, 9, 12, 12)
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        return httpx.Response(503) if state["n"] < 3 else httpx.Response(200, content=b"OK")

    def factory():
        return httpx.Client(transport=httpx.MockTransport(handler))

    c = ba.download_granules([g], tmp_path, client_factory=factory, sleep=lambda s: None)
    assert c["downloaded"] == 1 and state["n"] == 3

    def always_missing(request):
        return httpx.Response(404)

    def factory404():
        return httpx.Client(transport=httpx.MockTransport(always_missing))

    g2 = ba.Granule("MCD64A1.A2020245.h12v13.061.2", "https://x.test/p/b.hdf", 2020, 9, 12, 13)
    c2 = ba.download_granules([g2], tmp_path, client_factory=factory404, sleep=lambda s: None)
    assert c2["error"] == 1
    assert json.loads((tmp_path / "manifest.json").read_text())["granules"][g2.title]["status"] == "error"


# ---- optional burned-area feature of the SA2.7 cell model --------------------------------------------------


@pytest.fixture(scope="module")
def world():
    grid = synth_grid()
    cube, prep = setup(grid, "modis_to_viirs")
    return grid, cube, prep


def _burned_for(prep, grid):
    """One burned cell per month somewhere inside the synthetic area, plus its 3x3 neighbour test."""
    ym = prep.d.ym
    cid = np.unique(grid["cell_id"].to_numpy())
    rng = np.random.default_rng(1)
    rows = [(int(rng.choice(cid)), int(m), float(rng.uniform(1, 5))) for m in ym]
    return pd.DataFrame(rows, columns=["cell_id", "ym", "burned_km2"])


def test_default_off_leaves_features_untouched(world):
    grid, cube, prep = world
    burned = _burned_for(prep, grid)
    pair_cells = prep.cells
    assert not set(BURNED_FEATURES) & set(pair_cells.names)
    from firecal.stages.harmonize.evaluate import PAIRS

    pair = PAIRS["modis_to_viirs"]
    with_b = build_cell_rows(
        monthly_cell_table(grid), prep.d.ym, cube.blocks, pair.src, pair.tgt, prep.d.src, burned=burned
    )
    assert with_b.names[: len(pair_cells.names)] == pair_cells.names
    assert with_b.names[-2:] == BURNED_FEATURES
    n = len(pair_cells.names)
    np.testing.assert_array_equal(with_b.X[:, :n], pair_cells.X)  # same rows, same columns as before
    np.testing.assert_array_equal(with_b.y, pair_cells.y)
    np.testing.assert_array_equal(with_b.s_off, pair_cells.s_off)


def test_burned_columns_cell_and_3x3(world):
    grid, cube, _ = world
    cid = int(grid["cell_id"].iloc[0])
    lat, lon = cell_center(np.array([cid]), 0.1)
    _, ncols = grid_shape(0.1)
    ym0 = int(
        pd.to_datetime(grid["acq_date"].iloc[0]).year * 12
        + pd.to_datetime(grid["acq_date"].iloc[0]).month
        - 1
    )
    pos_of = {ym0: 0, ym0 + 1: 1}
    burned = pd.DataFrame(
        {
            "cell_id": [cid, cid + 1, cid + ncols, cid + 5 * ncols],  # own, east, north, far away
            "ym": [ym0, ym0, ym0, ym0],
            "burned_km2": [2.0, 3.0, 5.0, 100.0],
        }
    )
    r, c = divmod(cid, ncols)
    from firecal.stages.harmonize.ml_features import _burned_columns

    cols = _burned_columns(
        burned, pos_of, np.array([0, 1]), np.array([r, r]), np.array([c, c]), *grid_shape(0.1)
    )
    assert cols["ba_cell"].tolist() == [2.0, 0.0]  # month 1 has none
    assert cols["ba_n3"].tolist() == [10.0, 0.0]  # 2 + 3 + 5; the far cell is outside the 3x3
    assert lat.shape == lon.shape


def test_cv_runs_with_burned_and_cell_only(world):
    grid, cube, prep = world
    burned = _burned_for(prep, grid)
    prep_b = prepare(cube, monthly_cell_table(grid), "modis_to_viirs", burned=burned)
    folds, diags = run_ml_cv(
        prep_b, "loyo", SMALL, SMALL, ablations=False, with_intervals=False, burned=True, cell_only=True
    )
    methods = {f.method for f in folds}
    assert methods == {"lgb_cell", "zero_cell"}
    assert len({f.test_year for f in folds}) == len(YEARS)
    assert diags[0].importance.keys() == set(BASE_FEATURES) | set(BURNED_FEATURES)
    base, _ = run_ml_cv(prep, "loyo", SMALL, SMALL, ablations=False, with_intervals=False, cell_only=True)
    zero_b = [f for f in folds if f.method == "zero_cell"]
    zero_0 = [f for f in base if f.method == "zero_cell"]
    for a, b in zip(zero_b, zero_0, strict=True):
        np.testing.assert_allclose(a.pred, b.pred)  # the offset (and row set) do not depend on the variable
