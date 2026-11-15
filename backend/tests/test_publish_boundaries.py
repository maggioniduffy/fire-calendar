import hashlib
import json

import httpx
import pytest

from firecal.stages.publish import boundaries as bnd

ADM1 = b'{"type":"FeatureCollection","features":[]}'
ADM2 = b'{"type":"FeatureCollection","features":[{"x":1}]}'
META = json.dumps(
    {
        "boundarySource": "Source S",
        "boundaryLicense": "CC BY 3.0 IGO",
        "licenseSource": "https//example.org/license",
        "boundarySourceURL": "https//example.org/data",
        "boundaryYear": "2020",
        "buildDate": "Dec 12, 2023",
        "boundaryID": "ARG-ADM2-1",
        "admUnitCount": "526",
    }
).encode()


def sha(b):
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def served(monkeypatch):
    monkeypatch.setitem(bnd.EXPECTED_SHA256, "ADM1", sha(ADM1))
    monkeypatch.setitem(bnd.EXPECTED_SHA256, "ADM2", sha(ADM2))
    hits: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hits.append(req.url.path)
        assert req.url.host == "media.githubusercontent.com" and bnd.COMMIT in req.url.path
        name = req.url.path.rsplit("/", 1)[1]
        body = {
            bnd.geojson_name("ADM1"): ADM1,
            bnd.geojson_name("ADM2"): ADM2,
            bnd.meta_name("ADM1"): META,
            bnd.meta_name("ADM2"): META,
            bnd.CITATION_NAME: b"cite",
        }.get(name)
        return httpx.Response(200 if body is not None else 404, content=body or b"")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return client, hits


def test_fetch_downloads_records_hashes_and_is_idempotent(tmp_path, served):
    client, hits = served
    first = bnd.fetch(tmp_path, client)
    assert {r.status for r in first} == {"downloaded"} and len(hits) == 5
    adm2 = tmp_path / "ADM2" / bnd.geojson_name("ADM2")
    assert adm2.read_bytes() == ADM2
    assert (tmp_path / "ADM2" / (bnd.geojson_name("ADM2") + ".sha256")).read_text().strip() == sha(ADM2)
    m = bnd.read_manifest(tmp_path)
    assert m["commit"] == bnd.COMMIT and m["attribution"] == bnd.ATTRIBUTION
    lv = m["levels"]["ADM2"]
    assert lv["sha256"] == sha(ADM2) and lv["license"] == "CC BY 3.0 IGO" and lv["source"] == "Source S"
    assert lv["source_url"] == "https://example.org/data"  # the lost colon is restored
    before = (tmp_path / bnd.MANIFEST).read_text()
    second = bnd.fetch(tmp_path, client)
    assert {r.status for r in second} == {"skipped"} and len(hits) == 5
    assert (tmp_path / bnd.MANIFEST).read_text() == before


def test_a_corrupted_file_is_downloaded_again(tmp_path, served):
    client, hits = served
    bnd.fetch(tmp_path, client)
    (tmp_path / "ADM1" / bnd.geojson_name("ADM1")).write_bytes(b"broken")
    statuses = {r.name: r.status for r in bnd.fetch(tmp_path, client)}
    assert statuses[bnd.geojson_name("ADM1")] == "downloaded"
    assert statuses[bnd.geojson_name("ADM2")] == "skipped"


def test_a_file_that_differs_from_the_pin_is_rejected_and_not_kept(tmp_path, monkeypatch):
    monkeypatch.setitem(bnd.EXPECTED_SHA256, "ADM1", sha(ADM1))
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"version https://git-lfs..."))
    )
    with pytest.raises(RuntimeError, match="differs from the pinned"):
        bnd.fetch(tmp_path, client)
    assert not (tmp_path / "ADM1" / bnd.geojson_name("ADM1")).exists()
