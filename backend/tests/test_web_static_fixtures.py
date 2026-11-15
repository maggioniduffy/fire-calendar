import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "web_static_fixtures.py"
COMMITTED = Path(__file__).resolve().parents[2] / "web" / "e2e" / "fixtures" / "static"


def load_script():
    spec = importlib.util.spec_from_file_location("web_static_fixtures", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_committed_static_fixtures_equal_a_fresh_run(tmp_path):
    names = load_script().generate(tmp_path)
    committed = sorted(str(p.relative_to(COMMITTED)) for p in COMMITTED.rglob("*") if p.is_file())
    assert committed == names
    for name in names:
        assert (tmp_path / name).read_bytes() == (COMMITTED / name).read_bytes(), (
            f"{name} drifted; run `uv run python scripts/web_static_fixtures.py`"
        )


def test_static_fixtures_are_small_labelled_synthetic_and_follow_the_contract():
    total = sum(p.stat().st_size for p in COMMITTED.rglob("*") if p.is_file())
    assert total < 1_000_000
    m = json.loads((COMMITTED / "manifest.json").read_text())
    assert m["synthetic"] is True and "SYNTHETIC" in m["boundaries"]["source"]
    assert m["version"] == 1 and m["default_area"] == "p-cordoba"
    areas = json.loads((COMMITTED / "areas.json").read_text())["areas"]
    assert [(a["id"], a["kind"], a["province_id"]) for a in areas] == [
        ("p-cordoba", "province", None),
        ("d-cordoba-norte", "department", "p-cordoba"),
        ("d-cordoba-sur", "department", "p-cordoba"),
    ]
    cal = json.loads((COMMITTED / "calendar" / "p-cordoba" / "viirs_eq.json").read_text())
    assert "SYNTHETIC" in cal["meta"]["source"] and cal["enso"] is not None
    for a in areas:
        for scale in m["scales"]:
            for kind, ext in (("calendar", "json"), ("stats", "json"), ("export", "csv")):
                assert (COMMITTED / kind / a["id"] / f"{scale}.{ext}").is_file()
        assert (COMMITTED / "areas" / f"{a['id']}.json").is_file()
    assert (COMMITTED / "cells" / "viirs_eq" / "2014-12.json").is_file()
