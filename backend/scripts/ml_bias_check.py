"""Split the LightGBM cell-model bias into out-of-row target share and in-row bias.

Read-only: loads the cached MLResult, rebuilds SA2.2 folds (run_cv) and the cell row sets (prepare).
See reports/02/ml_bias_check.md. Usage: uv run python scripts/ml_bias_check.py <ml-cache.pkl>
"""

import pickle
import sys
from pathlib import Path

import numpy as np

from firecal.stages.harmonize.evaluate import MAIN_PAIRS, PAIRS, pair_data, run_cv
from firecal.stages.harmonize.metrics import relative_bias
from firecal.stages.harmonize.ml import prepare
from firecal.stages.harmonize.ml_features import build_monthly_cell_table
from firecal.stages.harmonize.regions import build_cube, build_monthly_region_table

PKL = Path(sys.argv[1])  # cache from `firecal harmonize evaluate --ml --ml-cache PATH`
NAMES = {"viirs_to_modis": "SA2.4 VIIRS->MODIS", "modis_to_viirs": "SA2.7 MODIS->VIIRS"}


def pct(x):
    return f"{100 * x:+.2f}%" if np.isfinite(x) else "nan"


def main():
    cube = build_cube(build_monthly_region_table())
    long = build_monthly_cell_table()
    ml = pickle.loads(PKL.read_bytes())
    for pair in MAIN_PAIRS:
        d = pair_data(cube, PAIRS[pair])
        nm, nb = d.tgt.shape[0], d.tgt.shape[1]
        sf = {f.test_year: f for f in run_cv(cube, pair, "loyo") if f.method == "sf"}
        cell = {f.test_year: f for f in ml.folds[pair, "loyo"] if f.method == "lgb_cell"}
        prep = prepare(cube, long, pair)
        c = prep.cells
        tgt_bm = d.tgt.sum(axis=-1)
        bm = c.mi * nb + c.bi
        in_bm = np.bincount(bm, weights=c.y, minlength=nm * nb).reshape(nm, nb)
        reach_bm = np.bincount(bm, minlength=nm * nb).reshape(nm, nb) > 0  # any candidate row in block-month
        src_bm = d.src.sum(axis=-1)
        print(f"\n== {NAMES[pair]} ==")
        print(
            f"cube target total {tgt_bm.sum():,.0f} | "
            f"long target total (cells.target_total) {c.target_total:,.0f}"
        )
        print(
            f"in-row target {in_bm.sum():,.0f} | unreachable {c.unreachable:,.0f} "
            f"share {c.unreachable / c.target_total:.4%} (meta {ml.meta[pair]['unreachable_share']:.4%})"
        )
        rows = []
        years = sorted(cell)
        agg = {k: [] for k in ("obs", "inr", "cell", "sf", "sf_r", "src_zero_obs")}
        for y in years:
            fc, fs = cell[y], sf[y]
            idx = np.searchsorted(d.ym, fc.ym)
            assert np.array_equal(d.ym[idx], fc.ym) and np.array_equal(fs.ym, fc.ym)
            obs = tgt_bm[idx]
            assert np.allclose(obs, fc.obs)
            inr = in_bm[idx]
            rch = reach_bm[idx]
            sfp = fs.pred
            sfr = sfp * rch
            cp = fc.pred
            so = {
                "obs": obs,
                "inr": inr,
                "cell": cp,
                "sf": sfp,
                "sf_r": sfr,
                "src_zero_obs": obs * (src_bm[idx] == 0),
            }
            for k, v in so.items():
                agg[k].append(v.ravel())
            o_all, o_in = obs.sum(), inr.sum()
            rows.append(
                (
                    y,
                    o_all,
                    o_in,
                    1 - o_in / o_all if o_all else np.nan,
                    relative_bias(obs, cp),
                    relative_bias(inr, cp),
                    relative_bias(obs, sfp),
                    relative_bias(obs, sfr),
                )
            )
        A = {k: np.concatenate(v) for k, v in agg.items()}
        out_share = 1 - A["inr"].sum() / A["obs"].sum()
        b_all, b_in = relative_bias(A["obs"], A["cell"]), relative_bias(A["inr"], A["cell"])
        print("year  obs_all  out_share  cell_all  cell_in  sf_all  sf_restr")
        for r in rows:
            print(
                f"{r[0]}  {r[1]:8,.0f}  {r[3]:8.2%}  "
                f"{pct(r[4]):>8}  {pct(r[5]):>8}  {pct(r[6]):>8}  {pct(r[7]):>8}"
            )
        print(f"POOLED obs {A['obs'].sum():,.0f} in-row {A['inr'].sum():,.0f} out_share {out_share:.4%}")
        print(
            f"cell bias vs all {pct(b_all)} | vs in-row {pct(b_in)} | identity (1+b_in)(1-out)-1 = "
            f"{pct((1 + b_in) * (1 - out_share) - 1)}"
        )
        print(
            f"sf bias vs all {pct(relative_bias(A['obs'], A['sf']))} | sf restricted to cell reach "
            f"{pct(relative_bias(A['obs'], A['sf_r']))} | "
            f"sf vs in-row {pct(relative_bias(A['inr'], A['sf']))} | "
            f"sf zero-pred obs share {A['src_zero_obs'].sum() / A['obs'].sum():.4%}"
        )
        worst = max(rows, key=lambda r: abs(r[4]))
        print(
            f"worst year {worst[0]}: cell_all {pct(worst[4])} out_share {worst[3]:.2%} "
            f"identity {pct((1 + worst[5]) * (1 - worst[3]) - 1)} cell_in {pct(worst[5])}"
        )


if __name__ == "__main__":
    main()
