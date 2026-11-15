"""`firecal harmonize ...` commands."""

import datetime as dt
import resource
import time
from pathlib import Path
from typing import Annotated

import typer

from firecal.paths import REPO_ROOT

harmonize_app = typer.Typer(no_args_is_help=True, help="Harmonization baselines and validation (phase 2).")


@harmonize_app.command("evaluate")
def evaluate_cmd(
    out: Annotated[Path, typer.Option(help="Markdown report path.")] = REPO_ROOT
    / "reports"
    / "02"
    / "baselines.md",
    ml: Annotated[bool, typer.Option("--ml/--no-ml", help="Also run SA2.4 / SA2.7 LightGBM (long).")] = False,
    ml_prev: Annotated[
        Path | None,
        typer.Option(help="Pickle of an earlier MLResult, to report the shift of SA2.4 cell WAPE."),
    ] = None,
    ml_jobs: Annotated[int, typer.Option(help="Processes for --ml (2 = one per direction).")] = 2,
    ml_cache: Annotated[
        Path | None,
        typer.Option(
            help="Pickle of the MLResult: loaded if it exists (skips the long run), else saved after --ml."
        ),
    ] = None,
) -> None:
    """Run SA2.2 / SA2.3 with leave-one-year-out and rolling origin; write the report and a per-block CSV."""
    import pickle

    from firecal.stages.grid.filters import FilterConfig
    from firecal.stages.harmonize.evaluate import (
        MAIN_PAIRS,
        PAIRS,
        block_detail,
        national_factors,
        run_cv,
    )
    from firecal.stages.harmonize.regions import build_cube, build_monthly_region_table
    from firecal.stages.harmonize.report import ReportInput, build_report
    from firecal.stages.harmonize.stability import detections_tables, grid_tables

    t0 = time.time()
    cube = build_cube(build_monthly_region_table())
    folds = {}
    for pair in PAIRS:
        folds[pair, "loyo"] = run_cv(
            cube,
            pair,
            "loyo",
            with_intervals=pair == "modis_to_viirs",
            with_conformal=pair in MAIN_PAIRS,
        )
        if pair in MAIN_PAIRS:
            folds[pair, "rolling"] = run_cv(cube, pair, "rolling")
    all_folds = [f for fs in folds.values() for f in fs]
    ml_result = None
    if ml_cache is not None and ml_cache.exists():
        ml_result = pickle.loads(ml_cache.read_bytes())
    elif ml:
        from firecal.stages.harmonize.ml import run_ml
        from firecal.stages.harmonize.ml_features import build_monthly_cell_table

        ml_result = run_ml(cube, build_monthly_cell_table(), n_jobs=ml_jobs, log=typer.echo)
        if ml_cache is not None:
            ml_cache.write_bytes(pickle.dumps(ml_result))
    inp = ReportInput(
        cube=cube,
        folds=folds,
        factors=national_factors(cube),
        grid_tables=grid_tables(cube),
        det_tables=detections_tables(),
        cfg=FilterConfig(),
        run_date=dt.date.today(),
        ml=ml_result,
        ml_prev=pickle.loads(ml_prev.read_bytes()) if ml_prev else None,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(inp))
    csv = out.with_name("baselines_by_block.csv")
    block_detail(all_folds, cube).to_csv(csv, index=False)
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    typer.echo(str(out))
    typer.echo(str(csv))
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS (main process) {peak_mb:.0f} MB")
    if ml_result is not None:
        typer.echo(f"ML: {ml_result.seconds / 60:.1f} min, peak summed PSS {ml_result.peak_mb:.0f} MB")


def _reports_dir(name: str) -> Path:
    return REPO_ROOT / "reports" / "02" / name


@harmonize_app.command("drift")
def drift_cmd(
    out: Annotated[Path, typer.Option(help="Markdown report path.")] = REPO_ROOT
    / "reports"
    / "02"
    / "SA2.6.md",
) -> None:
    """SA2.6: Terra/Aqua drift diagnostics (P3 epochs, ratios, placebo, factors with/without, P8)."""
    from firecal.stages.harmonize.drift import run_drift
    from firecal.stages.harmonize.drift_report import build_sa26_report

    t0 = time.time()
    res = run_drift()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_sa26_report(run_date=dt.date.today(), **res["report_args"]))
    res["blocks_csv"].to_csv(out.with_name("SA2.6_by_block.csv"), index=False)
    typer.echo(str(out))
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {peak_mb:.0f} MB")
    for sat, e in res["epochs"].items():
        typer.echo(f"drift epoch {sat}: {e.start}")


@harmonize_app.command("backward")
def backward_cmd(
    out: Annotated[Path, typer.Option(help="Markdown report path.")] = REPO_ROOT
    / "reports"
    / "02"
    / "SA2.8.md",
) -> None:
    """SA2.8: train 2016+, test 2012-2015, with and without the drift years; P4 condition 2 gate."""
    from firecal.stages.harmonize.backward import run_backward
    from firecal.stages.harmonize.backward_report import build_sa28_report

    t0 = time.time()
    results, windows, blocks = run_backward()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_sa28_report(results, windows, dt.date.today()))
    blocks.to_csv(out.with_name("SA2.8_by_block.csv"), index=False)
    typer.echo(str(out))
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {peak_mb:.0f} MB")
    for k, r in results.items():
        typer.echo(f"{k}: {r['verdict']}")
