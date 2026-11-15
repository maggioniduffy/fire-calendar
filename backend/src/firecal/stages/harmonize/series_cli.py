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
    version: Annotated[str, typer.Option(help="New calibration version label (required; never reused).")],
    method: Annotated[str, typer.Option(help="Only 'scale_factor' is implemented.")] = "scale_factor",
) -> None:
    """Fit and freeze the SA2.2 factors and conformal calibration on the full overlap."""
    from firecal.stages.harmonize.regions import build_cube, build_monthly_region_table
    from firecal.stages.harmonize.series import (
        LAYER_ID,
        calibration_path,
        fit_calibration,
        freeze_calibration,
        frozen_paths,
        save_calibration,
    )

    root = processed_dir() / LAYER_ID
    taken = [*frozen_paths(version), calibration_path(version, root)]
    for p in taken:
        if p.exists():
            raise typer.BadParameter(f"version {version} already exists ({p}); pick a new version")
    t0 = time.time()
    cal = fit_calibration(build_cube(build_monthly_region_table()), version, method)
    path = save_calibration(cal, root)
    frozen = freeze_calibration(cal)
    typer.echo(str(path))
    typer.echo(f"frozen {frozen}")
    for name, pc in cal.pairs.items():
        typer.echo(f"{name}: k={pc.k} months={pc.n_months} {pc.start}..{pc.end}")
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {_peak_mb():.0f} MB")


@series_app.command("build")
def build_cmd(
    version: Annotated[str, typer.Option(help="Frozen calibration to apply.")] = "sf-2026.11.2",
    year: Annotated[list[int] | None, typer.Option(help="Only these years (repeatable).")] = None,
) -> None:
    """Apply a frozen calibration to the 0.1 degree grid and publish the layer (series, bands, manifest)."""
    from firecal.stages.harmonize.series import (
        LAYER_ID,
        load_frozen,
        national_summary,
        publish,
        verified_frozen_sha,
    )

    t0 = time.time()
    root = processed_dir() / LAYER_ID
    cal = load_frozen(version)
    typer.echo(f"frozen calibration {version} sha256 {verified_frozen_sha(version)} verified")
    manifest = publish(cal, years=year)
    typer.echo(f"{root / 'manifest.json'}  period {manifest.period}  files {len(manifest.files)}")
    typer.echo(national_summary(root).round(0).to_string(index=False))
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {_peak_mb():.0f} MB")


@series_app.command("extend")
def extend_cmd(
    from_version: Annotated[str, typer.Option("--from", help="Frozen calibration to extend (untouched).")],
    to_version: Annotated[str, typer.Option("--to", help="New calibration version label (never reused).")],
    route: Annotated[
        str, typer.Option(help="Post-MODIS route: 'auto' applies the P5 decision, or 'chain' / 'direct'.")
    ] = "auto",
) -> None:
    """SA2.10: freeze `--to` = `--from` unchanged + NOAA-21 pairs + the post-MODIS route (P5), never on NRT
    rows."""
    from firecal.stages.harmonize.continuity import decide, load_inputs, run_forward
    from firecal.stages.harmonize.route import ROUTE_PAIR, ROUTES
    from firecal.stages.harmonize.series import (
        LAYER_ID,
        _pair_to_dict,
        calibration_path,
        extend_calibration,
        freeze_calibration,
        frozen_paths,
        load_frozen,
        save_calibration,
        verified_frozen_sha,
    )

    if route != "auto" and route not in ROUTES:
        raise typer.BadParameter(f"route must be auto, chain or direct, not {route!r}")
    root = processed_dir() / LAYER_ID
    for p in (*frozen_paths(to_version), calibration_path(to_version, root)):
        if p.exists():
            raise typer.BadParameter(f"version {to_version} already exists ({p}); pick a new version")
    t0 = time.time()
    base = load_frozen(from_version)
    typer.echo(f"base {from_version} sha256 {verified_frozen_sha(from_version)} verified")
    inp = load_inputs(base.blocks)
    typer.echo(
        f"cube months {inp.cube.ym[0]}..{inp.cube.ym[-1]}, detections outside base blocks "
        f"{inp.dropped_counts:.0f}"
    )
    if route == "auto":
        decision = decide(run_forward(inp.cube))
        route = decision.route
        typer.echo(f"P5 decision: {route} ({decision.reason})")
    cal = extend_calibration(base, inp.cube, to_version, route)
    for name, pc in base.pairs.items():
        if _pair_to_dict(name, cal.pairs[name]) != _pair_to_dict(name, pc):
            raise typer.BadParameter(f"pair {name} changed in the extension; refusing to freeze")
    path = save_calibration(cal, root)
    frozen = freeze_calibration(cal)
    typer.echo(str(path))
    typer.echo(f"frozen {frozen} sha256 {verified_frozen_sha(to_version)}")
    for name, pc in cal.pairs.items():
        extra = f" route={pc.route} legs={list(pc.legs)}" if pc.route else ""
        typer.echo(f"{name}: k={pc.k} months={pc.n_months} {pc.start}..{pc.end}{extra}")
    typer.echo(
        f"{ROUTE_PAIR} route {cal.pairs[ROUTE_PAIR].route}; fitted {cal.fitted_start}..{cal.fitted_end}"
    )
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {_peak_mb():.0f} MB")
