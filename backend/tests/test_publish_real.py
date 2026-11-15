"""Real boundaries (needs `firecal boundaries fetch`); outside CI."""

import pytest

from firecal.stages.publish import boundaries as bnd
from firecal.stages.publish.areas import build_areas

pytestmark = pytest.mark.slow


def test_cordoba_has_26_departments_and_the_ids_of_the_contract():
    root = bnd.boundaries_dir()
    if not (root / bnd.MANIFEST).exists():
        pytest.skip("boundaries not fetched")
    info = bnd.read_manifest(root)
    built = build_areas(root / info["levels"]["ADM1"]["file"], root / info["levels"]["ADM2"]["file"])
    ids = {a.id for a in built.areas}
    assert "p-cordoba" in ids and "p-entre-rios" in ids and "p-la-rioja" in ids
    assert not any("la-roja" in i for i in ids)
    assert sum(a.province_id == "p-cordoba" for a in built.areas) == 26
    assert len(ids) == len(built.areas)
