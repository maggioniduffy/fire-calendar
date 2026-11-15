"""SA1.6 NRT static-source mask (pre-registration P6 and Revision 1 in plan/02-harmonization.md).

NRT detections carry no `type`. The mask stands in for the type filter: cells where SP history shows
`type != 0` detections (volcano, other static land, offshore) in at least `k` distinct years are removed.
Cell size (0.01 or 0.02 degrees) and `k` (2, 3 or 5) are chosen per sensor family with a protocol that never
looks at the year it is scored on:

- selection: history <= 2023, scored on SP 2024, smallest max |bias| over satellite x day/night;
- acceptance: the selected parameters on history <= 2024, scored once on SP 2025 (gates below);
- deployment: history <= 2025, only for a family that passed. A family that fails keeps its NRT rows out.

The score compares the all-type count minus the masked cells with the `type == 0` count (same confidence
filters). It validates the `type` proxy only; the NRT vs SP processing difference stays unverified.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.paths import interim_dir
from firecal.stages.grid.filters import FilterConfig, apply_filters
from firecal.stages.grid.grid import cell_ids, choose_levels, level_files, read_year

log = logging.getLogger(__name__)

FAMILIES: dict[str, tuple[str, ...]] = {
    "modis": ("terra", "aqua"),
    "viirs": ("snpp", "noaa20", "noaa21"),
}
RESOLUTIONS = (0.01, 0.02)
MIN_YEARS = (2, 3, 5)
CANDIDATES = tuple((r, k) for r in RESOLUTIONS for k in MIN_YEARS)

SELECT_HISTORY_END, SELECT_YEAR = 2023, 2024
ACCEPT_HISTORY_END, ACCEPT_YEAR = 2024, 2025
DEPLOY_HISTORY_END = 2025

NATIONAL_BIAS_LIMIT = 0.03
BLOCK_BIAS_LIMIT = 0.10
BLOCK_MIN_T0 = 100
BLOCK_FRACTION = 0.90
BLOCK_SIZE = 2.5

_COLUMNS = [
    "sensor",
    "satellite",
    "acq_date",
    "daynight",
    "latitude",
    "longitude",
    "confidence_pct",
    "confidence_class",
    "type",
]
MASK_JSON = "nrt_mask.json"
MASK_CELLS = "nrt_mask_cells.parquet"


def mask_dir() -> Path:
    return interim_dir() / "firms"


# ---------------------------------------------------------------- mask object used by the grid


@dataclass
class FamilyMask:
    family: str
    accepted: bool
    res: float
    k: int
    cells: np.ndarray  # sorted cell ids at `res` to remove


@dataclass
class NrtMask:
    families: dict[str, FamilyMask]

    def apply(self, nrt: pd.DataFrame) -> pd.DataFrame:
        """Mask NRT rows by their sensor family; a family that is not accepted keeps no row."""
        if nrt.empty:
            return nrt
        keep = np.zeros(len(nrt), dtype=bool)
        sensor = nrt["sensor"].to_numpy()
        for fam, fm in self.families.items():
            sel = sensor == fam
            if not fm.accepted or not sel.any():
                continue
            cid = cell_ids(nrt["latitude"].to_numpy()[sel], nrt["longitude"].to_numpy()[sel], fm.res)
            keep[np.flatnonzero(sel)] = ~np.isin(cid, fm.cells)
        return nrt[keep]


def save_nrt_mask(masks: dict[str, FamilyMask], meta: dict, directory: Path | None = None) -> Path:
    directory = directory or mask_dir()
    directory.mkdir(parents=True, exist_ok=True)
    cells = pd.concat(
        [pd.DataFrame({"family": fam, "cell_id": fm.cells.astype("int64")}) for fam, fm in masks.items()],
        ignore_index=True,
    )
    tmp = directory / (MASK_CELLS + ".tmp")
    pq.write_table(pa.Table.from_pandas(cells, preserve_index=False), tmp)
    tmp.replace(directory / MASK_CELLS)
    body = {
        **meta,
        "families": {
            fam: {"accepted": fm.accepted, "res": fm.res, "k": fm.k, "cells": int(len(fm.cells))}
            for fam, fm in masks.items()
        },
    }
    path = directory / MASK_JSON
    path.write_text(json.dumps(body, indent=1) + "\n")
    return path


def load_nrt_mask(directory: Path | None = None) -> NrtMask | None:
    directory = directory or mask_dir()
    path = directory / MASK_JSON
    if not path.exists():
        return None
    body = json.loads(path.read_text())
    cells = pq.read_table(directory / MASK_CELLS).to_pandas()
    out = {}
    for fam, p in body["families"].items():
        ids = np.sort(cells.loc[cells["family"] == fam, "cell_id"].to_numpy(dtype="int64"))
        out[fam] = FamilyMask(fam, bool(p["accepted"]), float(p["res"]), int(p["k"]), ids)
    return NrtMask(out)


# ---------------------------------------------------------------- SP data


def load_sp(detections: Path, family: str, max_year: int = DEPLOY_HISTORY_END) -> pd.DataFrame:
    """SP detections of a sensor family (no NRT), one source per satellite x month (adds `year`, `level`)."""
    frames = []
    for year, files in sorted(level_files(detections).items()):
        if year > max_year:
            continue
        files = [(lv, f) for lv, f in files if lv != "nrt"]
        if not files:
            continue
        df = read_year(files, _COLUMNS)
        df = df[df["sensor"] == family]
        if df.empty:
            continue
        df = choose_levels(df).copy()
        df["year"] = year
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[*_COLUMNS, "year", "level"])
    return pd.concat(frames, ignore_index=True)


def _is_static(df: pd.DataFrame) -> np.ndarray:
    t = df["type"]
    return (t.notna() & (t != 0)).to_numpy()


class History:
    """Distinct (cell, year) pairs with a `type != 0` detection, per cell size."""

    def __init__(self, sp: pd.DataFrame):
        static = sp[_is_static(sp)]
        self._pairs: dict[float, pd.DataFrame] = {}
        for res in RESOLUTIONS:
            pairs = pd.DataFrame(
                {
                    "cell_id": cell_ids(static["latitude"].to_numpy(), static["longitude"].to_numpy(), res),
                    "year": static["year"].to_numpy(),
                }
            ).drop_duplicates()
            self._pairs[res] = pairs

    def cells(self, res: float, k: int, end_year: int) -> np.ndarray:
        p = self._pairs[res]
        n = p[p["year"] <= end_year].groupby("cell_id")["year"].nunique()
        return np.sort(n.index[n >= k].to_numpy(dtype="int64"))


# ---------------------------------------------------------------- scoring


def scoring_frame(sp: pd.DataFrame, year: int, cfg: FilterConfig | None = None) -> pd.DataFrame:
    """SP rows of `year` after the confidence filters (type filter skipped)."""
    return apply_filters(sp[sp["year"] == year], cfg, skip_type=True)[0]


def _counts(frame: pd.DataFrame, masked: np.ndarray, by: list[str]) -> pd.DataFrame:
    t0 = (frame["type"] == 0).to_numpy()
    d = frame[by].copy()
    d["t0"] = t0
    d["all_types"] = True
    d["proxy"] = ~masked
    d["false_removals"] = masked & t0
    d["misses"] = ~masked & ~t0
    return d.groupby(by, sort=True).sum().astype("int64").reset_index()


def _bias(proxy: pd.Series, t0: pd.Series) -> pd.Series:
    return (proxy - t0) / t0.where(t0 > 0)


def score_cells(frame: pd.DataFrame, cells: np.ndarray | None, res: float | None) -> pd.DataFrame:
    """Per satellite x day/night: type==0 count, all-type count, masked proxy, bias, gross error.

    `cells=None` is "no mask" (all rows kept).
    """
    if cells is None or res is None:
        masked = np.zeros(len(frame), dtype=bool)
    else:
        cid = cell_ids(frame["latitude"].to_numpy(), frame["longitude"].to_numpy(), res)
        masked = np.isin(cid, cells)
    out = _counts(frame, masked, ["satellite", "daynight"])
    out["bias"] = _bias(out["proxy"], out["t0"])
    out["gross_error"] = out["false_removals"] + out["misses"]
    return out


def score_blocks(frame: pd.DataFrame, cells: np.ndarray | None, res: float | None) -> pd.DataFrame:
    """Per 2.5 degree block (family pooled): type==0 count, proxy count, relative bias, gross error."""
    from firecal.stages.harmonize.regions import block_ids

    if cells is None or res is None:
        masked = np.zeros(len(frame), dtype=bool)
    else:
        cid = cell_ids(frame["latitude"].to_numpy(), frame["longitude"].to_numpy(), res)
        masked = np.isin(cid, cells)
    f = frame.assign(block=block_ids(frame["latitude"].to_numpy(), frame["longitude"].to_numpy(), BLOCK_SIZE))
    out = _counts(f, masked, ["block"])
    out["bias"] = _bias(out["proxy"], out["t0"])
    out["gross_error"] = out["false_removals"] + out["misses"]
    return out


def max_abs_bias(cell_table: pd.DataFrame) -> float:
    b = cell_table["bias"].abs()
    return float("inf") if b.isna().any() or b.empty else float(b.max())


@dataclass
class FamilyResult:
    family: str
    selection: pd.DataFrame  # one row per candidate: res, k, mask cells, max |bias| on the selection year
    nomask_select: float
    chosen: tuple[float, float]  # (res, k)
    accept_cells: pd.DataFrame  # masked score per satellite x day/night on the acceptance year
    accept_nomask: pd.DataFrame
    blocks: pd.DataFrame  # masked block score on the acceptance year
    blocks_nomask: pd.DataFrame
    checks: dict[str, bool]
    accepted: bool
    deploy_cells: np.ndarray
    n_accept_cells: int
    rows_by_level: dict[str, int]
    years: tuple[int, int]


def select_and_accept(sp: pd.DataFrame, family: str, cfg: FilterConfig | None = None) -> FamilyResult:
    hist = History(sp)
    f_sel = scoring_frame(sp, SELECT_YEAR, cfg)
    rows = []
    for res, k in CANDIDATES:
        cells = hist.cells(res, k, SELECT_HISTORY_END)
        rows.append(
            {
                "res": res,
                "k": k,
                "mask_cells": len(cells),
                "max_abs_bias": max_abs_bias(score_cells(f_sel, cells, res)),
            }
        )
    sel = pd.DataFrame(rows)
    # ties (equal to the float) go to the first candidate: smaller cell, then smaller k
    best = sel.loc[sel["max_abs_bias"].idxmin()]
    res, k = float(best["res"]), int(best["k"])
    nomask_sel = max_abs_bias(score_cells(f_sel, None, None))

    f_acc = scoring_frame(sp, ACCEPT_YEAR, cfg)
    cells_acc = hist.cells(res, k, ACCEPT_HISTORY_END)
    acc = score_cells(f_acc, cells_acc, res)
    acc0 = score_cells(f_acc, None, None)
    blocks = score_blocks(f_acc, cells_acc, res)
    blocks0 = score_blocks(f_acc, None, None)

    gated = blocks[blocks["t0"] >= BLOCK_MIN_T0]
    frac = float((gated["bias"].abs() <= BLOCK_BIAS_LIMIT).mean()) if len(gated) else float("nan")
    checks = {
        "national_bias_within_3pct": bool((acc["bias"].abs() <= NATIONAL_BIAS_LIMIT).all()),
        "lower_max_bias_than_no_mask": max_abs_bias(acc) < max_abs_bias(acc0),
        "blocks_within_10pct_ge_90pct": bool(frac >= BLOCK_FRACTION),
    }
    accepted = all(checks.values())
    rows_by_level = sp.groupby("level").size().to_dict()
    return FamilyResult(
        family=family,
        selection=sel,
        nomask_select=nomask_sel,
        chosen=(res, k),
        accept_cells=acc,
        accept_nomask=acc0,
        blocks=blocks,
        blocks_nomask=blocks0,
        checks=checks,
        accepted=accepted,
        deploy_cells=hist.cells(res, k, DEPLOY_HISTORY_END),
        n_accept_cells=len(cells_acc),
        rows_by_level={k_: int(v) for k_, v in rows_by_level.items()},
        years=(int(sp["year"].min()), int(sp["year"].max())),
    )


def build_nrt_mask(
    detections: Path | None = None, directory: Path | None = None, cfg: FilterConfig | None = None
) -> dict[str, FamilyResult]:
    """Run selection and acceptance per family, save the deployment mask, return the results."""
    detections = detections or interim_dir() / "firms" / "detections"
    results: dict[str, FamilyResult] = {}
    masks: dict[str, FamilyMask] = {}
    for fam in FAMILIES:
        sp = load_sp(detections, fam)
        r = select_and_accept(sp, fam, cfg)
        results[fam] = r
        masks[fam] = FamilyMask(
            fam,
            r.accepted,
            r.chosen[0],
            int(r.chosen[1]),
            r.deploy_cells if r.accepted else np.empty(0, dtype="int64"),
        )
        log.info("NRT mask %s: res=%s k=%s accepted=%s", fam, r.chosen[0], r.chosen[1], r.accepted)
    save_nrt_mask(
        masks,
        {
            "protocol": "P6 + Revision 1 (plan/02-harmonization.md)",
            "selection": f"history <= {SELECT_HISTORY_END}, scored on SP {SELECT_YEAR}",
            "acceptance": f"history <= {ACCEPT_HISTORY_END}, scored on SP {ACCEPT_YEAR}",
            "deployment_history_end": DEPLOY_HISTORY_END,
        },
        directory,
    )
    return results


# ---------------------------------------------------------------- report


def _pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{100 * x:+.2f} %"


def _cell_table(acc: pd.DataFrame, acc0: pd.DataFrame) -> list[str]:
    m = acc.merge(
        acc0[["satellite", "daynight", "proxy", "bias"]],
        on=["satellite", "daynight"],
        suffixes=("", "_nomask"),
    )
    L = [
        "| satellite | day/night | type==0 | all types (no mask) | bias no mask | masked proxy | bias masked "
        "| false removals | misses | gross error |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in m.itertuples():
        L.append(
            f"| {r.satellite} | {r.daynight} | {r.t0} | {r.proxy_nomask} | {_pct(r.bias_nomask)} | {r.proxy} "
            f"| {_pct(r.bias)} | {r.false_removals} | {r.misses} | {r.gross_error} |"
        )
    return L


def render_report(results: dict[str, FamilyResult], det_note: str) -> str:
    from firecal.stages.harmonize.regions import block_origin

    L = [
        "# SA1.6 NRT static-source mask (P6 + Revision 1)",
        "",
        "Generated by `firecal firms nrt-mask` (`firecal.stages.grid.nrt_mask`).",
        "",
        "Scope: this validates the `type` proxy only (all-type count minus masked cells vs the `type == 0` "
        "count, same confidence filters). NRT rows have no `type`; whether NRT and SP differ in their "
        "processing (detections, confidence, FRP) is **unverified** and is not tested here.",
        "",
        f"Source: {det_note}",
        f"Periods: selection = history <= {SELECT_HISTORY_END}, scored on SP {SELECT_YEAR}; acceptance = "
        f"history <= {ACCEPT_HISTORY_END}, scored on SP {ACCEPT_YEAR}; deployment = history <= "
        f"{DEPLOY_HISTORY_END}. Mask = cells where `type != 0` occurs in at least k distinct years "
        f"(cell 0.01 or 0.02 deg, k in {list(MIN_YEARS)}); no confidence filter on the history.",
        "",
        "Gates (accepted per family; a family that fails keeps its NRT rows out of the grid): "
        f"national bias within +-{100 * NATIONAL_BIAS_LIMIT:.0f} % per satellite x day/night; max |bias| "
        f"lower than with no mask; at least {100 * BLOCK_FRACTION:.0f} % of the {BLOCK_SIZE} deg blocks with "
        f">= {BLOCK_MIN_T0} `type == 0` detections within +-{100 * BLOCK_BIAS_LIMIT:.0f} % block-year "
        "(family pooled).",
        "",
        'Interpretation note: "lower |bias| than no mask" is gated on the maximum over satellite x '
        "day/night (the selection criterion); the per-cell comparison is in the tables.",
        "",
        "| family | cell (deg) | k | accepted | deployment mask cells |",
        "|---|---:|---:|---|---:|",
    ]
    for fam, r in results.items():
        L.append(
            f"| {fam} | {r.chosen[0]} | {int(r.chosen[1])} | {'yes' if r.accepted else 'NO'} "
            f"| {len(r.deploy_cells) if r.accepted else 0} |"
        )
    for fam, r in results.items():
        L += [
            "",
            f"## {fam.upper()}",
            "",
            f"SP rows used (all years up to {DEPLOY_HISTORY_END}): "
            + ", ".join(f"{lv} {n}" for lv, n in sorted(r.rows_by_level.items()))
            + f"; years {r.years[0]}-{r.years[1]}. Satellites: {', '.join(FAMILIES[fam])}.",
            "",
            f"### Selection (history <= {SELECT_HISTORY_END}, SP {SELECT_YEAR})",
            "",
            f"Max |bias| over satellite x day/night. No mask: {100 * r.nomask_select:.2f} %. "
            "Ties go to the first row (smaller cell, then smaller k).",
            "",
            "| cell (deg) | k | mask cells | max abs bias |",
            "|---:|---:|---:|---:|",
        ]
        for s in r.selection.itertuples():
            star = " (chosen)" if (s.res, s.k) == (r.chosen[0], int(r.chosen[1])) else ""
            L.append(f"| {s.res}{star} | {s.k} | {s.mask_cells} | {100 * s.max_abs_bias:.2f} % |")
        gated = r.blocks[r.blocks["t0"] >= BLOCK_MIN_T0]
        ok = gated[gated["bias"].abs() <= BLOCK_BIAS_LIMIT]
        bad = gated.drop(ok.index)
        small = r.blocks[r.blocks["t0"] < BLOCK_MIN_T0]
        frac = len(ok) / len(gated) if len(gated) else float("nan")
        L += [
            "",
            f"### Acceptance (history <= {ACCEPT_HISTORY_END}, cell {r.chosen[0]} deg, "
            f"k = {int(r.chosen[1])}, "
            f"mask cells {r.n_accept_cells}, scored once on SP {ACCEPT_YEAR})",
            "",
            *_cell_table(r.accept_cells, r.accept_nomask),
            "",
            "Residual bias above is the published NRT proxy bias (per satellite x day/night, national).",
            "",
            f"Max |bias|: masked {100 * max_abs_bias(r.accept_cells):.2f} %, no mask "
            f"{100 * max_abs_bias(r.accept_nomask):.2f} %.",
            f"Blocks with >= {BLOCK_MIN_T0} type==0 detections: {len(gated)}; within +-"
            f"{100 * BLOCK_BIAS_LIMIT:.0f} %: {len(ok)} ({100 * frac:.1f} %).",
            "",
        ]
        for name, passed in r.checks.items():
            L.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
        L.append(
            f"- **{fam}: {'ACCEPTED' if r.accepted else 'NOT ACCEPTED (NRT rows stay out of the grid)'}**"
        )
        L += ["", f"Blocks outside +-{100 * BLOCK_BIAS_LIMIT:.0f} % ({len(bad)}):", ""]
        if len(bad):
            lat, lon = block_origin(bad["block"].to_numpy(), BLOCK_SIZE)
            L += [
                "| block | SW corner (lat, lon) | type==0 | proxy | bias | false removals | misses |",
                "|---:|---|---:|---:|---:|---:|---:|",
            ]
            for b, la, lo in zip(bad.itertuples(), lat, lon, strict=True):
                L.append(
                    f"| {b.block} | ({la:.1f}, {lo:.1f}) | {b.t0} | {b.proxy} | {_pct(b.bias)} "
                    f"| {b.false_removals} | {b.misses} |"
                )
        else:
            L.append("none")
        L += [
            "",
            "Gross error (false removals + misses) in absolute rows, SP "
            f"{ACCEPT_YEAR}: gated blocks {int(gated['gross_error'].sum())} of {int(gated['t0'].sum())} "
            f"type==0 rows; national {int(r.accept_cells['gross_error'].sum())}.",
            f"Small blocks (< {BLOCK_MIN_T0} type==0, not gated): {len(small)} blocks, type==0 "
            f"{int(small['t0'].sum())}, proxy {int(small['proxy'].sum())}, false removals "
            f"{int(small['false_removals'].sum())}, misses {int(small['misses'].sum())}.",
        ]
    return "\n".join(L) + "\n"


def write_report(results: dict[str, FamilyResult], out: Path, det_note: str) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(results, det_note))
    return out


def detection_note(detections: Path) -> str:
    counts: dict[str, set[int]] = {}
    for year, files in level_files(detections).items():
        for lv, f in files:
            if lv != "nrt":
                product = (f.parent.parent if lv == "country-sp" else f.parent.parent.parent).name
                counts.setdefault(f"{product.split('=')[1]} {lv}", set()).add(year)
    parts = [f"{k} {min(v)}-{max(v)}" for k, v in sorted(counts.items())]
    return "FIRMS SP detections under data/interim/firms/detections (" + "; ".join(parts) + ")."
