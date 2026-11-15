import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "web_fixtures.py"
COMMITTED = Path(__file__).resolve().parents[2] / "web" / "e2e" / "fixtures" / "api"


def load_script():
    spec = importlib.util.spec_from_file_location("web_fixtures", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_committed_fixtures_equal_a_fresh_run(tmp_path):
    names = load_script().generate(tmp_path)
    assert sorted(p.name for p in COMMITTED.iterdir()) == names
    for name in names:
        assert (tmp_path / name).read_text() == (COMMITTED / name).read_text(), (
            f"{name} drifted; run `uv run python scripts/web_fixtures.py`"
        )


def test_fixtures_are_labelled_synthetic_and_cover_the_cases():
    index = json.loads((COMMITTED / "index.json").read_text())
    assert index["synthetic"] is True
    keys = index["requests"]
    assert len(keys) == 12 + 24  # /calendar + /stats, then /cells + /detections for 2 months
    assert index["statuses"] and set(index["statuses"].values()) == {404}
    assert all(k.startswith("POST /detections") for k in index["statuses"])
    cells_key = "POST /cells area=preset:cordoba scale=viirs_eq month=2016-12"
    cells = json.loads((COMMITTED / keys[cells_key]).read_text())
    assert cells["month"] == "2016-12" and cells["cells"] and "SYNTHETIC" in cells["meta"]["source"]
    assert "POST /calendar area=preset:cordoba scale=viirs_eq" in keys
    assert "POST /stats area=circle:-31.42,-64.18,230 scale=modis_eq" in keys
    assert "POST /calendar area=polygon scale=viirs_eq" in keys
    cal = json.loads((COMMITTED / keys["POST /calendar area=preset:cordoba scale=viirs_eq"]).read_text())
    assert "SYNTHETIC" in cal["meta"]["source"]
    by_year = {y["year"]: y for y in cal["years"]}
    assert by_year[2005]["viirs_eq_estimated_months"] == 12
    assert by_year[2015]["viirs_eq_estimated_months"] == 0
    assert cal["band"]["month"], "estimated months carry a band"


def test_fixtures_are_deterministic(tmp_path):
    mod = load_script()
    mod.generate(tmp_path / "a")
    mod.generate(tmp_path / "b")
    for p in (tmp_path / "a").iterdir():
        assert p.read_text() == (tmp_path / "b" / p.name).read_text()
