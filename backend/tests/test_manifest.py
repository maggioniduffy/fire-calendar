import json
import logging
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from firecal.layers.manifest import LayerManifest, discover_layers, load_manifest


def valid() -> dict:
    return {
        "id": "fire-grid",
        "title": "Focos de calor por celda",
        "kind": "grid",
        "source": "NASA FIRMS (MODIS C6.1, VIIRS 375 m)",
        "period": "2000-11-01/2026-08-31",
        "license": "NASA open data",
        "updated_at": "2026-11-14T12:00:00Z",
        "files": ["grid.parquet"],
    }


def test_valid_defaults_experimental_false():
    m = LayerManifest.model_validate(valid())
    assert m.experimental is False
    assert m.period_start == date(2000, 11, 1)
    assert m.period_end == date(2026, 8, 31)


def test_valid_with_experimental():
    assert LayerManifest.model_validate({**valid(), "experimental": True}).experimental is True


def _without(key):
    d = valid()
    del d[key]
    return d


@pytest.mark.parametrize(
    "data",
    [
        _without("source"),
        _without("period"),
        _without("license"),
        {**valid(), "kind": "raster"},
        {**valid(), "period": "2026-08-31/2000-11-01"},
        {**valid(), "period": "2000-11-01"},
        {**valid(), "period": "2000-11/2001-01"},
        {**valid(), "period": "nope/never"},
        {**valid(), "files": []},
        {**valid(), "files": ["../secret.parquet"]},
        {**valid(), "files": ["a/../b.parquet"]},
        {**valid(), "files": ["/etc/passwd"]},
        {**valid(), "files": ["a\\b.parquet"]},
        {**valid(), "files": ["a.parquet", "a.parquet"]},
        {**valid(), "extra": 1},
        {**valid(), "id": "Bad_Id"},
        {**valid(), "id": "-leading"},
    ],
)
def test_invalid(data):
    with pytest.raises(ValidationError):
        LayerManifest.model_validate(data)


def write(root: Path, folder: str, data: dict) -> None:
    (root / folder).mkdir(parents=True, exist_ok=True)
    (root / folder / "manifest.json").write_text(json.dumps(data))


def test_load_and_discover(tmp_path, caplog):
    write(tmp_path, "b-layer", {**valid(), "id": "b-layer"})
    write(tmp_path, "a-layer", {**valid(), "id": "a-layer"})
    write(tmp_path, "broken", {"id": "broken"})
    write(tmp_path, "mismatch", {**valid(), "id": "other"})
    with caplog.at_level(logging.WARNING):
        layers = discover_layers(tmp_path)
    assert [m.id for m in layers] == ["a-layer", "b-layer"]
    assert len(caplog.records) == 2
    assert load_manifest(tmp_path / "a-layer" / "manifest.json").id == "a-layer"
