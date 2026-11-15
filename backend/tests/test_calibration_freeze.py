"""Calibration freeze guard: no overwrite, sha-verified loading, byte-identical install on publish."""

import json
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_harmonize_series import const_cal, grid_rows

from firecal.stages.harmonize.series import (
    FROZEN_DIR,
    CalibrationIntegrityError,
    calibration_to_dict,
    freeze_calibration,
    load_frozen,
    publish,
    save_calibration,
)


def _grid(tmp_path):
    dest = tmp_path / "grid" / "year=2005" / "part-0.parquet"
    dest.parent.mkdir(parents=True)
    table = pa.Table.from_pandas(grid_rows({(2005, 3): {"terra": 5, "aqua": 7}}), preserve_index=False)
    pq.write_table(table, dest)
    return tmp_path / "grid"


def _tamper(path):
    data = bytearray(path.read_bytes())
    data[-3] ^= 0x01
    path.write_bytes(bytes(data))


def test_save_calibration_refuses_overwrite(tmp_path):
    cal = const_cal()
    save_calibration(cal, tmp_path)
    with pytest.raises(FileExistsError):
        save_calibration(cal, tmp_path)


def test_freeze_refuses_overwrite_and_writes_sidecar(tmp_path):
    cal = const_cal()
    path = freeze_calibration(cal, tmp_path)
    sidecar = tmp_path / "sf-test.json.sha256"
    assert sidecar.read_text().split() == [
        __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        "sf-test.json",
    ]
    with pytest.raises(FileExistsError):
        freeze_calibration(cal, tmp_path)
    path.unlink()  # sidecar alone also blocks
    with pytest.raises(FileExistsError):
        freeze_calibration(cal, tmp_path)


def test_load_frozen_rejects_tamper_and_missing_sidecar(tmp_path):
    path = freeze_calibration(const_cal(), tmp_path)
    assert load_frozen("sf-test", tmp_path).version == "sf-test"
    _tamper(path)
    with pytest.raises(CalibrationIntegrityError, match="checksum"):
        load_frozen("sf-test", tmp_path)
    (tmp_path / "sf-test.json.sha256").unlink()
    with pytest.raises(CalibrationIntegrityError, match="sidecar"):
        load_frozen("sf-test", tmp_path)


def test_publish_installs_byte_identical_copy(tmp_path):
    cal = const_cal()
    frozen = tmp_path / "frozen"
    src = freeze_calibration(cal, frozen)
    root = tmp_path / "out" / "harmonized"
    when = datetime(2026, 11, 15, tzinfo=UTC)
    publish(cal, _grid(tmp_path), root, now=when, frozen_dir=frozen)
    assert (root / "calibration" / "sf-test.json").read_bytes() == src.read_bytes()
    publish(cal, _grid(tmp_path / "again"), root, now=when, frozen_dir=frozen)  # same sha: left alone


def test_publish_refuses_tampered_frozen_and_divergent_target(tmp_path):
    cal = const_cal()
    frozen = tmp_path / "frozen"
    src = freeze_calibration(cal, frozen)
    root = tmp_path / "out" / "harmonized"
    grid = _grid(tmp_path)
    (root / "calibration").mkdir(parents=True)
    (root / "calibration" / "sf-test.json").write_text("{}")
    with pytest.raises(CalibrationIntegrityError, match="not overwriting"):
        publish(cal, grid, root, frozen_dir=frozen)
    _tamper(src)
    with pytest.raises(CalibrationIntegrityError, match="checksum"):
        publish(cal, grid, root, frozen_dir=frozen)


def test_publish_requires_calibration_matching_frozen_version(tmp_path):
    frozen = tmp_path / "frozen"
    freeze_calibration(const_cal(), frozen)
    other = const_cal()
    other.pairs["viirs_to_modis"].k = 21.0
    with pytest.raises(CalibrationIntegrityError, match="does not match"):
        publish(other, _grid(tmp_path), tmp_path / "out", frozen_dir=frozen)


def test_committed_calibration_passes_and_round_trips():
    cal = load_frozen("sf-2026.11.1")
    raw = json.loads((FROZEN_DIR / "sf-2026.11.1.json").read_text(encoding="utf-8"))
    assert calibration_to_dict(cal) == raw
