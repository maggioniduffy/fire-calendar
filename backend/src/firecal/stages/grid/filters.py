"""SA1.3 detection filters: fire type and confidence."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FilterConfig:
    modis_min_confidence: int = 30
    viirs_classes: tuple[str, ...] = ("nominal", "high")
    types: tuple[int, ...] = (0,)  # 0 presumed vegetation fire; 1 volcano, 2 other static land, 3 offshore
    keep_missing_type: bool = False


def apply_filters(df: pd.DataFrame, cfg: FilterConfig | None = None) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return the filtered frame and the number of rows dropped per reason (applied in this order)."""
    cfg = cfg or FilterConfig()
    drops: dict[str, int] = {}
    keep_type = df["type"].isin(cfg.types)
    if cfg.keep_missing_type:
        keep_type |= df["type"].isna()
    drops["type"] = int((~keep_type).sum())
    df = df[keep_type.to_numpy()]

    modis = (df["sensor"] == "modis").to_numpy()
    bad_modis = modis & ~(df["confidence_pct"] >= cfg.modis_min_confidence).fillna(False).to_numpy()
    drops["modis_confidence"] = int(bad_modis.sum())
    df = df[~bad_modis]

    viirs = (df["sensor"] == "viirs").to_numpy()
    bad_viirs = viirs & ~df["confidence_class"].isin(cfg.viirs_classes).to_numpy()
    drops["viirs_confidence"] = int(bad_viirs.sum())
    return df[~bad_viirs], drops
