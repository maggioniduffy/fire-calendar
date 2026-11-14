import json

import pytest
from fastapi.testclient import TestClient

from firecal.api.app import create_app


def manifest(layer_id: str, files: list[str]) -> dict:
    return {
        "id": layer_id,
        "title": "Test",
        "kind": "points",
        "source": "synthetic",
        "period": "2020-01-01/2020-12-31",
        "license": "CC0",
        "updated_at": "2026-01-01T00:00:00Z",
        "files": files,
    }


@pytest.fixture
def client(tmp_path):
    good = tmp_path / "good"
    good.mkdir()
    (good / "manifest.json").write_text(json.dumps(manifest("good", ["a.bin", "b.bin"])))
    (good / "a.bin").write_bytes(b"AAA")
    (good / "b.bin").write_bytes(b"BBB")
    (good / "unlisted.bin").write_bytes(b"SECRET")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps({"id": "bad"}))
    (tmp_path / "outside.bin").write_bytes(b"OUT")
    return TestClient(create_app(tmp_path))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_skips_invalid(client):
    r = client.get("/layers")
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == ["good"]


def test_get_and_404(client):
    assert client.get("/layers/good").json()["source"] == "synthetic"
    assert client.get("/layers/missing").status_code == 404
    assert client.get("/layers/bad").status_code == 404


def test_data_default_and_named(client):
    assert client.get("/layers/good/data").content == b"AAA"
    assert client.get("/layers/good/data", params={"file": "b.bin"}).content == b"BBB"


@pytest.mark.parametrize("name", ["unlisted.bin", "../outside.bin", "/etc/passwd", "manifest.json"])
def test_data_refuses_unlisted(client, name):
    assert client.get("/layers/good/data", params={"file": name}).status_code == 404
