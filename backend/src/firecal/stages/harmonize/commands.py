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
) -> None:
    """Run SA2.2 / SA2.3 with leave-one-year-out and rolling origin; write the report and a per-block CSV."""
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
        folds[pair, "loyo"] = run_cv(cube, pair, "loyo", with_intervals=pair == "modis_to_viirs")
        if pair in MAIN_PAIRS:
            folds[pair, "rolling"] = run_cv(cube, pair, "rolling")
    all_folds = [f for fs in folds.values() for f in fs]
    inp = ReportInput(
        cube=cube,
        folds=folds,
        factors=national_factors(cube),
        grid_tables=grid_tables(cube),
        det_tables=detections_tables(),
        cfg=FilterConfig(),
        run_date=dt.date.today(),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(inp))
    csv = out.with_name("baselines_by_block.csv")
    block_detail(all_folds, cube).to_csv(csv, index=False)
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    typer.echo(str(out))
    typer.echo(str(csv))
    typer.echo(f"runtime {time.time() - t0:.1f} s, peak RSS {peak_mb:.0f} MB")
