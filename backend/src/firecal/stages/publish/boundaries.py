"""geoBoundaries gbOpen ARG ADM1 and ADM2 (simplified GeoJSON), pinned to a commit (SA7.2).

`raw.githubusercontent.com` serves Git LFS pointers for these files; `media.githubusercontent.com/media/...`
serves the real bytes. Both GeoJSON files and their metadata are stored under `data/raw/boundaries/` with
sha256 sidecars and a `boundaries.json` that records source, license and attribution read from the
geoBoundaries metadata JSON. Re-running only downloads what is missing or whose hash no longer matches.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer

from firecal.paths import raw_dir

REPO = "wmgeolab/geoBoundaries"
# Commit of the repository (`main` on 2026-11-15). The data files of ARG were last built on 2023-12-12.
COMMIT = "8ce2700661a28ee944350e2b329bbabb58d2ff83"
MEDIA_BASE = f"https://media.githubusercontent.com/media/{REPO}/{COMMIT}/releaseData/gbOpen/ARG"
LEVELS = ("ADM1", "ADM2")
ATTRIBUTION = "Administrative boundaries courtesy of geoBoundaries.org"
HOME_URL = "https://www.geoboundaries.org"
# sha256 of the simplified GeoJSON at COMMIT (measured on 2026-11-15): a download that differs is rejected.
EXPECTED_SHA256 = {
    "ADM1": "7cc9b00ba139e57f59611993d96d07eb84d955ed5bd6bd6f1dcb864e1baf549c",
    "ADM2": "cedee8710e49d9017327fc1d4b2dc536e95a82317dc94c3bac8d9404af6bf771",
}
MANIFEST = "boundaries.json"


def geojson_name(level: str) -> str:
    return f"geoBoundaries-ARG-{level}_simplified.geojson"


def meta_name(level: str) -> str:
    return f"geoBoundaries-ARG-{level}-metaData.json"


CITATION_NAME = "CITATION-AND-USE-geoBoundaries.txt"


def boundaries_dir() -> Path:
    return raw_dir() / "boundaries"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def url_for(level: str, name: str) -> str:
    return f"{MEDIA_BASE}/{level}/{name}"


@dataclass
class FetchResult:
    level: str
    name: str
    status: str  # downloaded | skipped
    sha256: str
    bytes: int


def _download(client: httpx.Client, url: str, target: Path) -> None:
    tmp = target.with_name(target.name + ".part")
    try:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _ensure(client: httpx.Client, level: str, name: str, dest: Path, expected: str | None) -> FetchResult:
    target = dest / level / name
    sidecar = target.with_name(name + ".sha256")
    if target.exists() and sidecar.exists():
        digest = sha256_file(target)
        if digest == sidecar.read_text().strip() and (expected is None or digest == expected):
            return FetchResult(level, name, "skipped", digest, target.stat().st_size)
    target.parent.mkdir(parents=True, exist_ok=True)
    _download(client, url_for(level, name), target)
    digest = sha256_file(target)
    if expected is not None and digest != expected:
        target.unlink()
        raise RuntimeError(
            f"{level}/{name}: sha256 {digest} differs from the pinned {expected}; "
            "the file served at the pinned commit changed or an LFS pointer was returned"
        )
    sidecar.write_text(digest + "\n")
    return FetchResult(level, name, "downloaded", digest, target.stat().st_size)


def fetch(dest: Path | None = None, client: httpx.Client | None = None) -> list[FetchResult]:
    """Download the pinned files (idempotent) and write `boundaries.json`."""
    dest = dest or boundaries_dir()
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=120)
    results: list[FetchResult] = []
    try:
        for level in LEVELS:
            results.append(_ensure(client, level, geojson_name(level), dest, EXPECTED_SHA256[level]))
            results.append(_ensure(client, level, meta_name(level), dest, None))
        results.append(_ensure(client, "ADM2", CITATION_NAME, dest, None))
    finally:
        if own:
            client.close()
    _write_manifest(dest, results)
    return results


def _url(text: str | None) -> str | None:
    """The geoBoundaries metadata writes "https//host" (the colon is lost): restore it."""
    return text.replace("https//", "https://", 1) if text and text.startswith("https//") else text


def _write_manifest(dest: Path, results: list[FetchResult]) -> None:
    path = dest / MANIFEST
    old = json.loads(path.read_text()) if path.exists() else {}
    levels = {}
    for level in LEVELS:
        meta = json.loads((dest / level / meta_name(level)).read_text())
        res = next(r for r in results if r.name == geojson_name(level))
        levels[level] = {
            "file": f"{level}/{geojson_name(level)}",
            "url": url_for(level, geojson_name(level)),
            "sha256": res.sha256,
            "bytes": res.bytes,
            "source": meta.get("boundarySource"),
            "license": meta.get("boundaryLicense"),
            "license_source": _url(meta.get("licenseSource")),
            "source_url": _url(meta.get("boundarySourceURL")),
            "boundary_year": meta.get("boundaryYear"),
            "source_data_update_date": meta.get("sourceDataUpdateDate"),
            "build_date": meta.get("buildDate"),
            "boundary_id": meta.get("boundaryID"),
            "adm_unit_count_declared": meta.get("admUnitCount"),
        }
    changed = any(r.status == "downloaded" for r in results)
    out = {
        "repository": f"https://github.com/{REPO}",
        "commit": COMMIT,
        "attribution": ATTRIBUTION,
        "home": HOME_URL,
        "citation_file": f"ADM2/{CITATION_NAME}",
        "levels": levels,
        "downloaded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if changed or "downloaded_at" not in old
        else old["downloaded_at"],
    }
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")


def read_manifest(dest: Path | None = None) -> dict:
    path = (dest or boundaries_dir()) / MANIFEST
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `firecal boundaries fetch`")
    return json.loads(path.read_text())


boundaries_app = typer.Typer(no_args_is_help=True, help="Administrative boundaries (geoBoundaries).")


@boundaries_app.command("fetch")
def fetch_cmd(
    dest: Annotated[Path | None, typer.Option(help="Default: data/raw/boundaries")] = None,
) -> None:
    """Download geoBoundaries gbOpen ARG ADM1 and ADM2 (simplified) pinned to a commit."""
    for r in fetch(dest):
        typer.echo(f"{r.status:10s} {r.level}/{r.name} {r.bytes} B sha256={r.sha256[:12]}")
