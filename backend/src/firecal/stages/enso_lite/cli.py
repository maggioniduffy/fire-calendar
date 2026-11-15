"""`firecal enso lite`: run SA5.5 and write reports/05/SA5.5.{md,json}."""

import json
from pathlib import Path
from typing import Annotated

import typer

from firecal.stages.enso_lite.report import render_markdown, to_json
from firecal.stages.enso_lite.run import N_BOOT, N_PERM, SEED, run_analysis


def lite_command(
    out_dir: Annotated[Path, typer.Option(help="Output directory.")] = Path("reports/05"),
    seed: Annotated[int, typer.Option(help="Random seed (printed in the report).")] = SEED,
    n_perm: Annotated[int, typer.Option(help="Whole-year permutations.")] = N_PERM,
    n_boot: Annotated[int, typer.Option(help="Bootstrap resamples.")] = N_BOOT,
    oni_path: Annotated[Path | None, typer.Option(help="ONI parquet (default: data/interim/enso).")] = None,
) -> None:
    """ENSO-lite (SA5.5): fire-season totals vs lagged ONI. Association only, retrospective."""
    result = run_analysis(oni_path=oni_path, seed=seed, n_perm=n_perm, n_boot=n_boot)
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / "SA5.5.md", out_dir / "SA5.5.json"
    md.write_text(render_markdown(result), encoding="utf-8")
    js.write_text(json.dumps(to_json(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    p = result["primary"]
    typer.echo(f"seed={seed} primary n={p['n']} family-wise p={p['p_fw']:.4f}")
    typer.echo(f"{md}\n{js}")
