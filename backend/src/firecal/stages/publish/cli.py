"""`firecal publish export` and `firecal boundaries fetch` (SA7.2)."""

from pathlib import Path
from typing import Annotated

import typer

from firecal import paths
from firecal.io import enso as enso_io
from firecal.stages.publish import boundaries as bnd
from firecal.stages.publish.areas import build_areas
from firecal.stages.publish.export import PreloadedStore, export_static

publish_app = typer.Typer(no_args_is_help=True, help="Static export for the online demo (SA7.2).")
boundaries_app = bnd.boundaries_app


def default_out() -> Path:
    return paths.data_dir() / "publish" / "static"


def boundaries_info(manifest: dict) -> dict:
    """The `boundaries` block of the export manifest, from `data/raw/boundaries/boundaries.json`."""
    adm2, adm1 = manifest["levels"]["ADM2"], manifest["levels"]["ADM1"]
    return {
        "source": adm2["source"],
        "license": adm2["license"],
        "attribution": manifest["attribution"],
        "url": adm2["url"],
        "sha256": adm2["sha256"],
        "commit": manifest["commit"],
        "repository": manifest["repository"],
        "boundary_year": adm2["boundary_year"],
        "adm1_lookup_only": {
            "source": adm1["source"],
            "license": adm1["license"],
            "sha256": adm1["sha256"],
            "note": "Province lookup only; never published.",
        },
    }


@publish_app.command("export")
def export_cmd(
    out: Annotated[Path | None, typer.Option(help="Default: data/publish/static")] = None,
    only: Annotated[list[str] | None, typer.Option("--only", help="Area id(s), e.g. p-cordoba")] = None,
    workers: Annotated[int, typer.Option(min=1, help="Processes")] = 2,
    no_detections: Annotated[bool, typer.Option("--no-detections", help="Skip raw FIRMS detections")] = False,
    detections_tile_deg: Annotated[
        float, typer.Option("--detections-tile-deg", min=0.000001, help="Detection tile size in degrees")
    ] = 5,
) -> None:
    """Write the static tree (JSON and CSV per province and department) from the harmonized layer."""
    root = bnd.boundaries_dir()
    info = bnd.read_manifest(root)
    built = build_areas(root / info["levels"]["ADM1"]["file"], root / info["levels"]["ADM2"]["file"])
    store = PreloadedStore()
    store.manifest  # noqa: B018  (fail early when the harmonized layer is not built)
    enso_path = enso_io.default_path()
    enso = enso_io.read_enso(enso_path) if enso_path.exists() else None
    notes = {
        "assignment": {
            "entre_rios_by_bbox": built.assigned_by_fallback,
            "by_neighbour": built.assigned_by_neighbour,
            "corrections": built.corrected,
        }
    }
    summary = export_static(
        out or default_out(), store, built.areas, enso, boundaries_info(info), only=only,
        workers=workers, pre_skipped=built.skipped, notes=notes, include_detections=not no_detections,
        detections_tile_deg=detections_tile_deg,
    )  # fmt: skip
    typer.echo(
        f"areas={summary.n_areas} skipped={len(summary.skipped)} files={summary.n_files} "
        f"bytes={summary.total_bytes} seconds={summary.seconds:.1f}"
    )
    for s in summary.skipped:
        typer.echo(f"skipped: {s['name']}: {s['reason']}")
