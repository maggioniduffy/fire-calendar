"""SA1.6 NRT static-source mask: recurrence, scoring, selection/acceptance protocol, persistence."""

import numpy as np
import pandas as pd

from firecal.stages.grid import nrt_mask as nm
from firecal.stages.grid.grid import cell_ids

SENSOR = "viirs"


def frame(parts):
    d = pd.concat(parts, ignore_index=True)
    d["sensor"] = SENSOR
    d["acq_date"] = pd.to_datetime(d["year"].astype(str) + "-06-01").dt.date
    d["confidence_pct"] = pd.array([pd.NA] * len(d), dtype="Int16")
    d["confidence_class"] = "high"
    d["level"] = "country-sp"
    return d


def block(year, lat, lon, n, typ, sat="snpp", dn="D", jitter=0.003):
    rng = np.random.default_rng(int(abs(lat * 1000)) + year)
    return pd.DataFrame(
        {
            "year": year,
            "satellite": sat,
            "daynight": dn,
            "latitude": lat + rng.uniform(0, jitter, n),
            "longitude": lon + rng.uniform(0, jitter, n),
            "type": typ,
        }
    )


def synthetic(recurrent=True):
    parts = []
    for y in range(2018, 2026):
        # vegetation fires: several blocks, 200 rows each
        for lat, lon in [(-31.0, -64.0), (-34.0, -61.0), (-27.0, -58.0)]:
            parts.append(block(y, lat, lon, 200, 0, jitter=1.0))
        # a static source: same cell every year, or a different cell each year
        lat = -31.5 if recurrent else -31.5 - 0.5 * (y - 2017)
        parts.append(block(y, lat, -64.5, 30, 2))
    return frame(parts)


def test_history_recurrence_counts_distinct_years():
    sp = synthetic()
    h = nm.History(sp)
    c2 = h.cells(0.02, 2, 2023)
    c5 = h.cells(0.02, 5, 2023)
    assert len(c2) >= 1 and set(c5) <= set(c2)
    # a cell seen in a single year never reaches k = 2
    one = frame([block(2020, -30.0, -60.0, 10, 2)])
    assert len(nm.History(one).cells(0.02, 2, 2025)) == 0
    # the cutoff year is honoured
    late = frame([block(2024, -30.0, -60.0, 10, 2), block(2025, -30.0, -60.0, 10, 2)])
    assert len(nm.History(late).cells(0.02, 2, 2024)) == 0
    assert len(nm.History(late).cells(0.02, 2, 2025)) >= 1


def test_score_cells_hand_computed():
    f = pd.DataFrame(
        {
            "satellite": ["snpp"] * 6,
            "daynight": ["D"] * 6,
            "latitude": [-31.0, -31.0, -31.0, -32.0, -32.0, -33.0],
            "longitude": [-64.0] * 6,
            "type": [0, 0, 2, 0, 2, 0],
        }
    )
    masked = np.sort(cell_ids(np.array([-31.0]), np.array([-64.0]), 0.02))
    s = nm.score_cells(f, masked, 0.02).iloc[0]
    # masked cell removes 3 rows (2 true fires, 1 static); proxy = 3 rows left, type==0 total = 4
    assert (s.t0, s.all_types, s.proxy) == (4, 6, 3)
    assert (s.false_removals, s.misses, s.gross_error) == (2, 1, 3)
    assert np.isclose(s.bias, (3 - 4) / 4)
    s0 = nm.score_cells(f, None, None).iloc[0]
    assert s0.proxy == 6 and np.isclose(s0.bias, 0.5)


def test_select_and_accept_recurrent_source_is_accepted():
    r = nm.select_and_accept(synthetic(recurrent=True), "viirs")
    assert r.accepted, r.checks
    assert r.chosen[1] in nm.MIN_YEARS and r.chosen[0] in nm.RESOLUTIONS
    assert len(r.deploy_cells) >= 1
    assert max(abs(r.accept_cells["bias"])) < max(abs(r.accept_nomask["bias"]))


def test_select_and_accept_non_recurrent_source_fails():
    r = nm.select_and_accept(synthetic(recurrent=False), "viirs")
    # the static sources never repeat, so the mask cannot remove them: not accepted
    assert not r.accepted
    assert not r.checks["lower_max_bias_than_no_mask"] or not r.checks["national_bias_within_3pct"]


def test_save_load_roundtrip_and_apply(tmp_path):
    cells = np.sort(cell_ids(np.array([-31.0]), np.array([-64.0]), 0.02))
    masks = {
        "modis": nm.FamilyMask("modis", True, 0.02, 2, cells),
        "viirs": nm.FamilyMask("viirs", False, 0.01, 3, np.empty(0, dtype="int64")),
    }
    nm.save_nrt_mask(masks, {"protocol": "test"}, tmp_path)
    loaded = nm.load_nrt_mask(tmp_path)
    assert loaded.families["modis"].accepted and not loaded.families["viirs"].accepted
    assert list(loaded.families["modis"].cells) == list(cells)
    nrt = pd.DataFrame(
        {
            "sensor": ["modis", "modis", "viirs"],
            "latitude": [-31.0, -35.0, -35.0],
            "longitude": [-64.0, -64.0, -64.0],
        }
    )
    out = loaded.apply(nrt)
    assert list(out["latitude"]) == [-35.0] and list(out["sensor"]) == ["modis"]
