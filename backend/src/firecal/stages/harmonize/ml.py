"""SA2.4 / SA2.7 LightGBM on top of the SA2.2 scale factor (design in plan/02-harmonization.md).

Two candidates per direction, both with the SA2.2 factor as a log offset (`log(f * source + eps)`):

- cell model: 0.1 degree cell x month x day/night rows (`ml_features.build_cell_rows`), predictions summed to
  block-month;
- block model: block-month x day/night rows, heavily regularised.

Nesting (docs/validation.md): inside one outer training set `train`, the hyperparameters are chosen by inner
leave-one-year-out (same gap) on block-month WAPE. In every inner fold the training rows carry offset factors
fitted *out of fold* (a leave-one-year-out inside the inner training set) and the inner test rows the factors
of the inner training set; the outer test year and its gap are never read. Final model: same, one level up.
The out-of-fold block-month predictions of the chosen configuration calibrate the conformal intervals of
`intervals.py` (shared code).
"""

import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

from firecal.stages.harmonize.evaluate import (
    GAP_MONTHS,
    MAIN_PAIRS,
    PAIRS,
    FoldOut,
    PairData,
    _folds,
    pair_data,
)
from firecal.stages.harmonize.intervals import collect_residuals, conformal_from_residuals
from firecal.stages.harmonize.ml_features import (
    BASE_FEATURES,
    BLOCK_FEATURES,
    LATLON_FEATURES,
    TA_FEATURES,
    RowSet,
    build_block_rows,
    build_cell_rows,
)
from firecal.stages.harmonize.regions import Cube
from firecal.stages.harmonize.scale_factor import K_GRID, fit_factors, inner_folds, select_k

EPS = 0.001  # offset floor: log(f * source + EPS)
THREADS = 2
SEED = 20261114


@dataclass(frozen=True)
class GBMConfig:
    """One LightGBM structure; `iters` are the numbers of trees evaluated (the last one is trained)."""

    name: str
    objective: str = "poisson"
    num_leaves: int = 15
    min_data: int = 200
    lr: float = 0.05
    l2: float = 10.0
    tweedie_p: float = 1.2
    iters: tuple[int, ...] = (50, 100, 200)


# Complexity ascending: ties go to the first (simplest) entry.
CELL_GRID = (GBMConfig("poisson-31", num_leaves=31, min_data=200, lr=0.1, iters=(25, 50, 100)),)
BLOCK_GRID = (
    GBMConfig("poisson-3", num_leaves=3, min_data=200, l2=50.0, iters=(30, 100, 250)),
    GBMConfig("poisson-7", num_leaves=7, min_data=100, l2=20.0, iters=(30, 100, 250)),
    GBMConfig("tweedie-3", objective="tweedie", num_leaves=3, min_data=200, l2=50.0, iters=(30, 100, 250)),
    GBMConfig("tweedie-7", objective="tweedie", num_leaves=7, min_data=100, l2=20.0, iters=(30, 100, 250)),
)

ML_METHODS = {
    "lgb_cell": "LightGBM celda",
    "lgb_block": "LightGBM bloque-mes",
    "lgb_cell_ta": "LightGBM celda + proporción Terra/Aqua",
    "lgb_cell_ll": "LightGBM celda + lat/lon",
    "zero_cell": "Cero árboles (celda)",
    "zero_block": "Cero árboles (bloque-mes)",
}


def lgb_params(cfg: GBMConfig, seed: int = SEED, threads: int = THREADS) -> dict:
    p = {
        "objective": cfg.objective,
        "learning_rate": cfg.lr,
        "num_leaves": cfg.num_leaves,
        "min_data_in_leaf": cfg.min_data,
        "lambda_l2": cfg.l2,
        # Caps the leaf output at lr * max_delta_step. Rows whose offset sits at the eps floor (no source in
        # the row) but with target detections otherwise get Newton steps of tens in log space (first real
        # run: SA2.7 cell predictions of ~1e18).
        "max_delta_step": 1.0,
        "max_bin": 63,
        "num_threads": threads,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "feature_pre_filter": False,
        "verbosity": -1,
    }
    if cfg.objective == "tweedie":
        p["tweedie_variance_power"] = cfg.tweedie_p
    return p


# --- offset factors -------------------------------------------------------------------------------------


def oof_factors(
    d: PairData, mask: np.ndarray, k: float, gap: int = GAP_MONTHS
) -> tuple[np.ndarray, np.ndarray]:
    """Out-of-fold SA2.2 factors for the months in `mask`: each month gets the factor fitted on `mask` without
    its year (and gap). Returns (F with shape (months, blocks, 2), ok = months that got one)."""
    f = np.zeros(d.src.shape)
    ok = np.zeros(len(mask), dtype=bool)
    for tr, te in inner_folds(d.dates, mask, gap):
        fac = fit_factors(d.src, d.tgt, d.month_idx, tr, k)
        f[te] = fac.f[d.month_idx[te]]
        ok |= te
    return f, ok


def fitted_factors(d: PairData, mask: np.ndarray, k: float) -> np.ndarray:
    """Factors fitted on `mask`, expanded to every month: (months, blocks, 2)."""
    return fit_factors(d.src, d.tgt, d.month_idx, mask, k).f[d.month_idx]


def offsets(rs: RowSet, idx: np.ndarray, f: np.ndarray) -> np.ndarray:
    return np.log(f[rs.mi[idx], rs.bi[idx], rs.dn[idx]] * rs.s_off[idx] + EPS)


def aggregate(rs: RowSet, idx: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """Sum row predictions into (months, blocks); day and night are summed."""
    flat = rs.mi[idx] * rs.n_blocks + rs.bi[idx]
    return np.bincount(flat, weights=pred, minlength=rs.n_months * rs.n_blocks).reshape(
        rs.n_months, rs.n_blocks
    )


def _rows_in(rs: RowSet, months: np.ndarray) -> np.ndarray:
    return np.flatnonzero(months[rs.mi])


# --- fitting --------------------------------------------------------------------------------------------


def fit_predict(
    rs: RowSet,
    cols: np.ndarray,
    cfg: GBMConfig,
    itr: np.ndarray,
    off_tr: np.ndarray,
    ite: np.ndarray,
    off_te: np.ndarray,
    iters: tuple[int, ...],
    seed: int = SEED,
) -> tuple[dict[int, np.ndarray], lgb.Booster]:
    """Train on rows `itr` with the offset as init score; predictions exp(raw + offset) at each `iters`."""
    ds = lgb.Dataset(
        rs.X[itr][:, cols],
        label=rs.y[itr],
        init_score=off_tr,
        params={"max_bin": 63, "feature_pre_filter": False},
        free_raw_data=True,
    )
    booster = lgb.train(lgb_params(cfg, seed), ds, num_boost_round=max(iters))
    xte = rs.X[ite][:, cols]
    out = {it: np.exp(booster.predict(xte, raw_score=True, num_iteration=it) + off_te) for it in iters}
    return out, booster


@dataclass(eq=False)
class Selection:
    cfg: GBMConfig
    iters: int
    table: list[tuple[str, int, float]]  # (config, trees, inner block-month WAPE)
    oof: list[
        tuple[np.ndarray, np.ndarray]
    ]  # (inner test months mask, block-month predictions (months, blocks))


def select_config(
    rs: RowSet,
    names: tuple[str, ...],
    grid: tuple[GBMConfig, ...],
    d: PairData,
    k: float,
    train: np.ndarray,
    seed: int = SEED,
) -> Selection | None:
    """Pick (config, trees) by pooled inner leave-one-year-out block-month WAPE inside `train`."""
    cols = rs.cols(names)
    obs = d.tgt.sum(axis=-1)
    err: dict[tuple[int, int], float] = {}
    oof: dict[tuple[int, int], list] = {}
    tot = 0.0
    n_scored = 0
    for tr, te in inner_folds(d.dates, train, GAP_MONTHS):
        f_tr, ok = oof_factors(d, tr, k)
        itr = _rows_in(rs, tr & ok)
        ite = _rows_in(rs, te)
        if len(itr) == 0 or len(ite) == 0:
            continue
        off_tr = offsets(rs, itr, f_tr)
        off_te = offsets(rs, ite, fitted_factors(d, tr, k))
        for ci, cfg in enumerate(grid):
            preds, _ = fit_predict(rs, cols, cfg, itr, off_tr, ite, off_te, cfg.iters, seed)
            for it, p in preds.items():
                dense = aggregate(rs, ite, p)[te]
                err[ci, it] = err.get((ci, it), 0.0) + float(np.abs(dense - obs[te]).sum())
                oof.setdefault((ci, it), []).append((te, dense))
        tot += float(obs[te].sum())
        n_scored += 1
    if n_scored == 0 or tot <= 0:
        return None
    best = min(err, key=lambda key: (err[key], key))  # ties: first config, fewer trees
    table = [(grid[ci].name, it, e / tot) for (ci, it), e in sorted(err.items())]
    return Selection(grid[best[0]], best[1], table, oof[best])


def fit_final(
    rs: RowSet,
    names: tuple[str, ...],
    cfg: GBMConfig,
    iters: int,
    d: PairData,
    k: float,
    train: np.ndarray,
    test: np.ndarray,
    seed: int = SEED,
) -> tuple[np.ndarray, np.ndarray, lgb.Booster]:
    """Fit on `train` (offset factors out of fold) and predict `test`: (model, zero-tree) block-month sums."""
    f_tr, ok = oof_factors(d, train, k)
    itr = _rows_in(rs, train & ok)
    ite = _rows_in(rs, test)
    off_te = offsets(rs, ite, fitted_factors(d, train, k))
    preds, booster = fit_predict(
        rs, rs.cols(names), cfg, itr, offsets(rs, itr, f_tr), ite, off_te, (iters,), seed
    )
    return aggregate(rs, ite, preds[iters])[test], aggregate(rs, ite, np.exp(off_te))[test], booster


# --- cross-validation -----------------------------------------------------------------------------------


@dataclass(eq=False)
class MLPrep:
    pair: str
    d: PairData
    cells: RowSet
    block: RowSet


def prepare(cube: Cube, long: pd.DataFrame, pair_name: str) -> MLPrep:
    pair = PAIRS[pair_name]
    d = pair_data(cube, pair)
    cells = build_cell_rows(long, d.ym, cube.blocks, pair.src, pair.tgt, d.src)
    return MLPrep(pair_name, d, cells, build_block_rows(d.src, d.tgt, d.month_idx, cells))


@dataclass(eq=False)
class FoldDiag:
    pair: str
    scheme: str
    test_year: int
    cell_cfg: str
    cell_iters: int
    block_cfg: str
    block_iters: int
    seconds: float
    importance: dict[str, float] = field(default_factory=dict)  # gain, normalised to 1


def _conformal(sel: Selection, d: PairData, test_pred: np.ndarray, test_src: np.ndarray):
    obs, src = d.tgt.sum(axis=-1), d.src.sum(axis=-1)
    parts = [(p, obs[te], src[te]) for te, p in sel.oof]
    used = np.zeros(len(d.ym), dtype=bool)
    for te, _ in sel.oof:
        used |= te
    return conformal_from_residuals(collect_residuals(parts, used), test_pred, test_src)


def _guard(method: str, pred: np.ndarray, obs: np.ndarray) -> None:
    """Fail loudly on a numerical blow-up instead of reporting it as a score."""
    if not np.isfinite(pred).all() or pred.sum() > 100 * max(obs.sum(), 1.0):
        raise FloatingPointError(
            f"{method}: diverged predictions (sum {pred.sum():.3g}, observed {obs.sum():.3g})"
        )


def run_ml_cv(
    prep: MLPrep,
    scheme: str = "loyo",
    cell_grid: tuple[GBMConfig, ...] = CELL_GRID,
    block_grid: tuple[GBMConfig, ...] = BLOCK_GRID,
    ablations: bool = True,
    with_intervals: bool = True,
    only_years: set[int] | None = None,
    log=None,
) -> tuple[list[FoldOut], list[FoldDiag]]:
    """Cell and block candidates (+ablations, + zero-tree checks) for every fold of `scheme`.

    Folds whose training set is too short for an inner leave-one-year-out are skipped (none in `loyo`).
    Ablations reuse the configuration chosen for the main cell model of the same outer fold.
    """
    d, pair = prep.d, prep.pair
    src_tot, tgt_tot = d.src.sum(axis=-1), d.tgt.sum(axis=-1)
    folds, diags = [], []
    base = BASE_FEATURES
    ta = BASE_FEATURES + TA_FEATURES
    ll = BASE_FEATURES + LATLON_FEATURES
    has_ta = bool(set(PAIRS[pair].src) & {"terra", "aqua"})
    for fold in _folds(scheme, d.dates):
        tr, te = fold.train, fold.test
        if not tr.any() or not te.any() or (only_years and fold.test_year not in only_years):
            continue
        t0 = time.time()
        k, _ = select_k(d.src, d.tgt, d.dates, d.month_idx, tr, K_GRID, GAP_MONTHS)
        common = dict(pair=pair, scheme=scheme, test_year=fold.test_year, ym=d.ym[te], obs=tgt_tot[te])
        sel_c = select_config(prep.cells, base, cell_grid, d, k, tr)
        sel_b = select_config(prep.block, BLOCK_FEATURES, block_grid, d, k, tr)
        if sel_c is None or sel_b is None:
            if log:
                log(f"  {pair} {scheme} {fold.test_year}: skipped (training too short for inner folds)")
            continue
        out = {}
        p, z, booster = fit_final(prep.cells, base, sel_c.cfg, sel_c.iters, d, k, tr, te)
        out["lgb_cell"], out["zero_cell"] = p, z
        gain = booster.feature_importance("gain")
        diag = FoldDiag(
            pair,
            scheme,
            fold.test_year,
            sel_c.cfg.name,
            sel_c.iters,
            sel_b.cfg.name,
            sel_b.iters,
            0.0,
            dict(zip(base, (gain / gain.sum()).tolist() if gain.sum() > 0 else gain.tolist(), strict=True)),
        )
        out["lgb_block"], out["zero_block"], _ = fit_final(
            prep.block, BLOCK_FEATURES, sel_b.cfg, sel_b.iters, d, k, tr, te
        )
        if ablations:
            if has_ta:
                out["lgb_cell_ta"], _, _ = fit_final(prep.cells, ta, sel_c.cfg, sel_c.iters, d, k, tr, te)
            out["lgb_cell_ll"], _, _ = fit_final(prep.cells, ll, sel_c.cfg, sel_c.iters, d, k, tr, te)
        for method, pred in out.items():
            _guard(method, pred, tgt_tot[te])
            fo = FoldOut(method=method, pred=pred, src=src_tot[te], **common)
            if with_intervals and method in ("lgb_cell", "lgb_block"):
                cf = _conformal(sel_c if method == "lgb_cell" else sel_b, d, fo.pred, src_tot[te])
                fo.intervals["conformal"] = cf.month
                fo.year_intervals["conformal"] = cf.year
            fo.k = k
            folds.append(fo)
        diag.seconds = time.time() - t0
        diags.append(diag)
        if log:
            log(
                f"  {pair} {scheme} {fold.test_year}: cell {sel_c.cfg.name}/{sel_c.iters} "
                f"block {sel_b.cfg.name}/{sel_b.iters} {diag.seconds:.0f} s"
            )
    return folds, diags


# --- orchestration --------------------------------------------------------------------------------------


@dataclass(eq=False)
class MLResult:
    folds: dict[tuple[str, str], list[FoldOut]]  # (pair, scheme) -> ML folds
    diags: list[FoldDiag]
    meta: dict[str, dict]  # pair -> row counts and unreachable share
    cell_grid: tuple[GBMConfig, ...] = CELL_GRID
    block_grid: tuple[GBMConfig, ...] = BLOCK_GRID
    seconds: float = 0.0
    peak_mb: float = float("nan")  # peak summed proportional memory of this process and its workers


_SHARED: dict = {}


def run_ml_pair(cube: Cube, long: pd.DataFrame, pair_name: str, log=None, ablations: bool = True):
    """Both schemes of one direction: (folds by scheme, diagnostics, row metadata)."""
    prep = prepare(cube, long, pair_name)
    meta = {
        "cell_rows": int(len(prep.cells.y)),
        "block_rows": int(len(prep.block.y)),
        "unreachable_share": prep.cells.unreachable / prep.cells.target_total
        if prep.cells.target_total > 0
        else float("nan"),
    }
    folds, diags = {}, []
    for scheme in ("loyo", "rolling"):
        f, dg = run_ml_cv(prep, scheme, ablations=ablations and scheme == "loyo", log=log)
        folds[pair_name, scheme] = f
        diags += dg
    return folds, diags, meta


def _worker(pair_name: str):
    cube, long = _SHARED["cube"], _SHARED["long"]
    return pair_name, *run_ml_pair(cube, long, pair_name, log=lambda m: print(m, flush=True))


def _pss_mb(pid: int) -> float:
    try:
        with open(f"/proc/{pid}/smaps_rollup") as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def run_ml(cube: Cube, long: pd.DataFrame, n_jobs: int = 2, log=print) -> MLResult:
    """Run SA2.4 (viirs_to_modis) and SA2.7 (modis_to_viirs); `n_jobs` = 2 runs one process per direction."""
    import os
    import threading

    t0 = time.time()
    peak = [0.0]
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            kids = [c.pid for c in mp.active_children() if c.pid]
            peak[0] = max(peak[0], _pss_mb(os.getpid()) + sum(_pss_mb(k) for k in kids))
            stop.wait(3.0)

    th = threading.Thread(target=sample, daemon=True)
    th.start()
    folds, diags, meta = {}, [], {}
    try:
        if n_jobs > 1:
            _SHARED.update(cube=cube, long=long)
            with ProcessPoolExecutor(len(MAIN_PAIRS), mp_context=mp.get_context("fork")) as ex:
                for pair, f, dg, m in ex.map(_worker, MAIN_PAIRS):
                    folds.update(f)
                    diags += dg
                    meta[pair] = m
        else:
            for pair in MAIN_PAIRS:
                f, dg, m = run_ml_pair(cube, long, pair, log=log)
                folds.update(f)
                diags += dg
                meta[pair] = m
    finally:
        stop.set()
        th.join()
    return MLResult(folds, diags, meta, seconds=time.time() - t0, peak_mb=peak[0])
