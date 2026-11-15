"""`firecal series ...` commands: freeze a calibration, publish the harmonized series layer (SA2.11)."""

import resource
import time
from typing import Annotated

import typer

from firecal.paths import processed_dir

series_app = typer.Typer(no_args_is_help=True, help="Harmonized MODIS-eq / VIIRS-eq series layer (SA2.11).")


def _peak_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


@series_app.command("calibrate")
def calibrate_cmd(
    version: Annotated[str, typer.Option(help="Calibration version label.")] = "sf-2026.11.1",
    method: Annotated[str, typer.Option(help="Only 'scale_factor' is implemented.")] = "scale_factor",
) -> None:
    """Fit and freeze the SA2.2 factors and conformal calibration on the full overlap."""
    from firecal.stages.harmonize.regions import build_cube, build_monthly_region_table
    from firecal.stages.harmonize.series import LAYER_ID, fit_calibration, save_calibration

    t0 = time.time()
    cal = fit_calibration(build_cube(build_monthly_region_table()), version, method)
    path = save_calibration(cal, processed_dir() / LAYER_ID)
    typer.echo(str(path))
    for name, pc in cal.pairs.items():
        typer.echo(f"{name}: k={pc.k} months={pc.n_months} {pc.start}..{pc.end}")
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {_peak_mb():.0f} MB")


@series_app.command("build")
def build_cmd(
    version: Annotated[str, typer.Option(help="Frozen calibration to apply.")] = "sf-2026.11.1",
    year: Annotated[list[int] | None, typer.Option(help="Only these years (repeatable).")] = None,
) -> None:
    """Apply a frozen calibration to the 0.1 degree grid and publish the layer (series, bands, manifest)."""
    from firecal.stages.harmonize.series import (
        LAYER_ID,
        load_calibration,
        national_summary,
        publish,
    )

    t0 = time.time()
    root = processed_dir() / LAYER_ID
    manifest = publish(load_calibration(version, root), years=year)
    typer.echo(f"{root / 'manifest.json'}  period {manifest.period}  files {len(manifest.files)}")
    typer.echo(national_summary(root).round(0).to_string(index=False))
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {_peak_mb():.0f} MB")
