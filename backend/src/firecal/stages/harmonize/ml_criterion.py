# ruff: noqa: E501
"""Publication criterion for SA2.4 / SA2.7 (fixed in plan/02-harmonization.md before any run).

A LightGBM candidate is published for a direction only if it meets every condition against SA2.2:

1. block-month WAPE (leave-one-year-out, all test years pooled) at least 1 point lower, and block-year WAPE
   not higher;
2. lower block-month WAPE in at least 10 of the 14 test years;
3. same sign of the block-month improvement under the rolling-origin control (years scored by both);
4. |total relative bias| not worse than SA2.2's + 0.5 points, and the worst test year (|bias| of the year's
   block-month totals) not worse;
5. mean Poisson deviance of block-months not worse;
6. SA2.7 only (MODIS -> VIIRS): conformal block-month coverage within 80 +/- 5 % and relative width not larger
   than SA2.2's;
7. the paired two-way bootstrap interval (test years and blocks resampled independently, 1000 resamples,
   fixed seed, percentile 95 %) of the block-month WAPE difference (candidate - SA2.2) excludes zero.

Interpretations fixed here, before the run: "year" in 2 and 4 is a leave-one-year-out test year; the coverage and
width of 6 are the block-month headline (source > 0 rows, `evaluate.coverage_table`); block-year coverage is
reported but not a condition; the bootstrap upper limit must be below zero.
"""

from dataclasses import dataclass

import numpy as np

from firecal.stages.harmonize.evaluate import FoldOut, coverage_table, score_table
from firecal.stages.harmonize.metrics import wape

MIN_POINTS = 0.01
MIN_YEARS_WON = 10
BIAS_SLACK = 0.005
COVERAGE_BAND = (0.75, 0.85)
N_BOOT = 1000
BOOT_SEED = 20261114
BOOT_LEVEL = 0.95


@dataclass(frozen=True)
class Condition:
    name: str
    passed: bool
    detail: str


@dataclass(eq=False)
class Verdict:
    pair: str
    method: str
    conditions: list[Condition]
    boot: tuple[float, float, float]  # point, low, high of the WAPE difference (candidate - SA2.2)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.conditions)

    @property
    def text(self) -> str:
        return "supera al factor" if self.passed else "no supera al factor"


def _by_year(folds: list[FoldOut], pair: str, scheme: str, method: str) -> dict[int, FoldOut]:
    return {f.test_year: f for f in folds if (f.pair, f.scheme, f.method) == (pair, scheme, method)}


def _pct_points(x: float) -> str:
    return f"{x * 100:+.2f} pts"


def bootstrap_diff(
    cand: dict[int, FoldOut], base: dict[int, FoldOut], n_boot: int = N_BOOT, seed: int = BOOT_SEED
) -> tuple[float, float, float]:
    """Paired two-way bootstrap of WAPE(candidate) - WAPE(base) over test years x blocks (block-month level)."""
    years = sorted(set(cand) & set(base))
    if not years:
        return float("nan"), float("nan"), float("nan")
    a_c = np.stack([np.abs(cand[y].pred - cand[y].obs).sum(axis=0) for y in years])  # (years, blocks)
    a_b = np.stack([np.abs(base[y].pred - base[y].obs).sum(axis=0) for y in years])
    o = np.stack([base[y].obs.sum(axis=0) for y in years])
    point = float((a_c.sum() - a_b.sum()) / o.sum())
    rng = np.random.default_rng(seed)
    ny, nb = o.shape
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        yi, bj = rng.integers(0, ny, ny), rng.integers(0, nb, nb)
        ix = np.ix_(yi, bj)
        den = o[ix].sum()
        diffs[i] = (a_c[ix].sum() - a_b[ix].sum()) / den if den > 0 else np.nan
    lo, hi = np.nanquantile(diffs, [(1 - BOOT_LEVEL) / 2, 1 - (1 - BOOT_LEVEL) / 2])
    return point, float(lo), float(hi)


def evaluate_criterion(
    sf_folds: list[FoldOut], ml_folds: list[FoldOut], pair: str, method: str, n_boot: int = N_BOOT
) -> Verdict:
    """All conditions for `method` (e.g. 'lgb_cell') against 'sf' in direction `pair`."""
    allf = sf_folds + ml_folds
    cand = _by_year(allf, pair, "loyo", method)
    base = _by_year(allf, pair, "loyo", "sf")
    years = sorted(set(cand) & set(base))
    conds: list[Condition] = []
    sc = score_table([f for f in allf if f.pair == pair and f.method in ("sf", method)])

    def row(scheme, meth, year, level):
        r = sc[
            (sc["scheme"] == scheme)
            & (sc["method"] == meth)
            & (sc["test_year"].astype(str) == str(year))
            & (sc["level"] == level)
        ]
        return r.iloc[0] if len(r) else None

    c_bm, b_bm = row("loyo", method, "all", "block-month"), row("loyo", "sf", "all", "block-month")
    c_by, b_by = row("loyo", method, "all", "block-year"), row("loyo", "sf", "all", "block-year")
    if c_bm is None or b_bm is None or c_by is None or b_by is None:
        return Verdict(pair, method, [Condition("datos", False, "sin resultados")], (np.nan,) * 3)

    d_bm = c_bm["wape"] - b_bm["wape"]
    d_by = c_by["wape"] - b_by["wape"]
    conds.append(
        Condition(
            "1. WAPE bloque-mes al menos 1 punto menor y bloque-año no mayor",
            bool(d_bm <= -MIN_POINTS and d_by <= 0),
            f"bloque-mes {_pct_points(d_bm)}, bloque-año {_pct_points(d_by)}",
        )
    )
    won = sum(1 for y in years if wape(cand[y].obs, cand[y].pred) < wape(base[y].obs, base[y].pred))
    conds.append(
        Condition(
            f"2. WAPE bloque-mes menor en al menos {MIN_YEARS_WON} de {len(years)} años de test",
            won >= MIN_YEARS_WON,
            f"{won} de {len(years)}",
        )
    )
    rc, rb = _by_year(allf, pair, "rolling", method), _by_year(allf, pair, "rolling", "sf")
    ry = sorted(set(rc) & set(rb))
    if ry:
        d_roll = wape(
            np.concatenate([rc[y].obs.ravel() for y in ry]), np.concatenate([rc[y].pred.ravel() for y in ry])
        ) - wape(
            np.concatenate([rb[y].obs.ravel() for y in ry]), np.concatenate([rb[y].pred.ravel() for y in ry])
        )
        conds.append(
            Condition(
                "3. Mejora del mismo signo con origen móvil",
                bool(d_roll < 0 and d_bm < 0),
                f"origen móvil {_pct_points(d_roll)} ({len(ry)} años)",
            )
        )
    else:
        conds.append(Condition("3. Mejora del mismo signo con origen móvil", False, "sin años comparables"))
    worst_c = max(abs(row("loyo", method, y, "block-month")["bias"]) for y in years)
    worst_b = max(abs(row("loyo", "sf", y, "block-month")["bias"]) for y in years)
    conds.append(
        Condition(
            "4. |sesgo| total no peor que SA2.2 + 0,5 puntos y el peor año no peor",
            bool(abs(c_bm["bias"]) <= abs(b_bm["bias"]) + BIAS_SLACK and worst_c <= worst_b + 1e-12),
            f"total {c_bm['bias'] * 100:+.2f} % vs {b_bm['bias'] * 100:+.2f} %; peor año {worst_c * 100:.1f} % vs {worst_b * 100:.1f} %",
        )
    )
    conds.append(
        Condition(
            "5. Devianza de Poisson bloque-mes no peor",
            bool(c_bm["deviance"] <= b_bm["deviance"]),
            f"{c_bm['deviance']:.3f} vs {b_bm['deviance']:.3f}",
        )
    )
    if pair == "modis_to_viirs":
        cc = coverage_table(allf, method=method)
        cb = coverage_table(allf, method="sf")

        def cov(tab):
            r = tab[
                (tab["pair"] == pair)
                & (tab["scheme"] == "loyo")
                & (tab["interval"] == "conformal")
                & (tab["level"] == "block-month")
                & (tab["test_year"].astype(str) == "all")
            ]
            return r.iloc[0] if len(r) else None

        a, b = cov(cc), cov(cb)
        if a is None or b is None:
            conds.append(Condition("6. Cobertura 80 ± 5 % y ancho no mayor", False, "sin intervalos"))
        else:
            conds.append(
                Condition(
                    "6. Cobertura 80 ± 5 % y ancho no mayor que SA2.2",
                    bool(
                        COVERAGE_BAND[0] <= a["coverage"] <= COVERAGE_BAND[1]
                        and a["rel_width"] <= b["rel_width"]
                    ),
                    f"cobertura {a['coverage'] * 100:.1f} %, ancho {a['rel_width']:.3f} vs SA2.2 {b['rel_width']:.3f}",
                )
            )
    point, lo, hi = bootstrap_diff(cand, base, n_boot)
    conds.append(
        Condition(
            "7. Intervalo bootstrap pareado (año y bloque) de la diferencia de WAPE excluye cero",
            bool(np.isfinite(hi) and hi < 0),
            f"{_pct_points(point)} [{lo * 100:+.2f}; {hi * 100:+.2f}] (95 %)",
        )
    )
    return Verdict(pair, method, conds, (point, lo, hi))
