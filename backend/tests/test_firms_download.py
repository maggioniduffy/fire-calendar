import hashlib
import json

import httpx
import pytest

from firecal.io.firms import download

BODY = b"latitude,longitude\n1,2\n"


def make_client(handler):
    calls = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped)), calls


def ok(request):
    return httpx.Response(200, content=BODY)


def run(tmp_path, client, **kw):
    return download(
        products=["viirs-snpp"], years=[2020], dest=tmp_path, client=client, sleep=lambda s: None, **kw
    )


def test_download_writes_file_sidecar_manifest(tmp_path):
    client, calls = make_client(ok)
    (r,) = run(tmp_path, client)
    assert r.status == "downloaded"
    assert calls == [
        "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/2020/viirs-snpp_2020_Argentina.csv"
    ]
    csv = tmp_path / "viirs-snpp" / "viirs-snpp_2020_Argentina.csv"
    digest = hashlib.sha256(BODY).hexdigest()
    assert csv.read_bytes() == BODY
    assert (tmp_path / "viirs-snpp" / (csv.name + ".sha256")).read_text().strip() == digest
    assert r.sha256 == digest and r.bytes == len(BODY)
    manifest = json.loads((tmp_path / "downloads.json").read_text())
    assert manifest["records"][0]["status"] == "downloaded" and "downloaded_at" in manifest


def test_second_run_makes_no_requests(tmp_path):
    client, calls = make_client(ok)
    run(tmp_path, client)
    calls.clear()
    (r,) = run(tmp_path, client)
    assert r.status == "skipped" and calls == []


def test_corrupted_file_redownloaded(tmp_path):
    client, calls = make_client(ok)
    run(tmp_path, client)
    csv = tmp_path / "viirs-snpp" / "viirs-snpp_2020_Argentina.csv"
    csv.write_bytes(b"garbage")
    (r,) = run(tmp_path, client)
    assert r.status == "downloaded" and csv.read_bytes() == BODY


def test_404_is_missing_and_writes_nothing(tmp_path):
    client, _ = make_client(lambda r: httpx.Response(404))
    (r,) = run(tmp_path, client)
    assert r.status == "missing"
    assert not list(tmp_path.glob("viirs-snpp/*"))


def test_refresh_years_and_force(tmp_path):
    client, calls = make_client(ok)
    run(tmp_path, client)
    calls.clear()
    (r,) = run(tmp_path, client, refresh_years=[2020])
    assert r.status == "downloaded" and len(calls) == 1
    run(tmp_path, client, force=True)
    assert len(calls) == 2


def test_default_years_start_at_first_year(tmp_path):
    client, calls = make_client(lambda r: httpx.Response(404))
    res = download(products=["viirs-jpss1"], years=[2010, 2018], dest=tmp_path, client=client)
    assert [r.year for r in res] == [2018]


def test_5xx_retried_then_succeeds(tmp_path):
    state = {"n": 0}

    def flaky(request):
        state["n"] += 1
        return httpx.Response(503) if state["n"] < 3 else httpx.Response(200, content=BODY)

    client, _ = make_client(flaky)
    (r,) = run(tmp_path, client)
    assert r.status == "downloaded" and state["n"] == 3


@pytest.mark.parametrize("failure", ["transport", "5xx"])
def test_error_leaves_no_files(tmp_path, failure):
    def bad(request):
        if failure == "5xx":
            return httpx.Response(500)
        raise httpx.ConnectError("boom")

    client, calls = make_client(bad)
    (r,) = run(tmp_path, client)
    assert r.status == "error" and len(calls) == 4
    assert not [p for p in tmp_path.rglob("*") if p.is_file() and p.name != "downloads.json"]


def test_interrupted_stream_leaves_no_partial(tmp_path):
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield b"abc"
            raise httpx.ReadError("cut")

    client, _ = make_client(lambda r: httpx.Response(200, stream=Broken()))
    (r,) = run(tmp_path, client)
    assert r.status == "error"
    assert not [p for p in tmp_path.rglob("*") if p.is_file() and p.name != "downloads.json"]
