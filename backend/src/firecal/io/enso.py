"""Shared ENSO index: monthly ONI (NOAA CPC) and El Nino / La Nina phase.

Phase follows the NOAA CPC operational definition: El Nino when ONI >= +0.5 for at least
5 consecutive overlapping seasons, La Nina when ONI <= -0.5 for at least 5 consecutive,
otherwise neutral. Retrospective use only; an association index, never a cause.
"""

from io import StringIO
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
import typer

from firecal.paths import interim_dir

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
SOURCE = "NOAA CPC ONI"
NINO_THRESHOLD = 0.5
NINA_THRESHOLD = -0.5
MIN_RUN = 5
MISSING_SENTINEL = -99.0  # values <= this are treated as missing
DEFINITION = (
    "El Nino: ONI >= +0.5 for at least 5 consecutive overlapping seasons; "
    "La Nina: ONI <= -0.5 for at least 5 consecutive; otherwise neutral "
    "(NOAA CPC operational definition). Every month inside a qualifying run gets the phase."
)

# Seasons are labelled by initials; each maps to its central month.
SEASON_CENTER_MONTH = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}  # fmt: skip


def default_path() -> Path:
    return interim_dir() / "enso" / "oni_monthly.parquet"


def fetch_oni(url: str = ONI_URL, timeout: float = 30.0, client: httpx.Client | None = None) -> str:
    """Download the raw ONI ascii file. Pass `client` to inject a (mock) transport."""
    if client is not None:
        response = client.get(url, timeout=timeout, follow_redirects=True)
    else:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text


def parse_oni(text: str) -> pd.DataFrame:
    """Parse CPC ONI ascii (SEAS YR TOTAL ANOM) into `date`, `season`, `oni`.

    `date` is the first day of the season's central month. Sorted by date. Unknown season
    labels raise ValueError; sentinel values (<= -99) become NaN.
    """
    raw = pd.read_csv(StringIO(text), sep=r"\s+")
    month = raw["SEAS"].map(SEASON_CENTER_MONTH)
    if month.isna().any():
        raise ValueError(f"unknown season labels: {sorted(raw['SEAS'][month.isna()].unique())}")
    date = pd.to_datetime({"year": raw["YR"], "month": month, "day": 1})
    oni = raw["ANOM"].astype(float)
    oni = oni.mask(oni <= MISSING_SENTINEL)
    df = pd.DataFrame({"date": date, "season": raw["SEAS"].astype(str), "oni": oni})
    return df.sort_values("date").reset_index(drop=True)


def _oni_series(data: pd.DataFrame | pd.Series) -> pd.Series:
    if isinstance(data, pd.DataFrame):
        s = data["oni"]
        if "date" in data.columns:
            s = pd.Series(s.to_numpy(), index=pd.DatetimeIndex(data["date"]))
        return s
    return data


def above_threshold(
    oni: pd.Series,
    *,
    nino_threshold: float = NINO_THRESHOLD,
    nina_threshold: float = NINA_THRESHOLD,
) -> pd.Series:
    """Single-month classification: 'nino' if oni >= nino_threshold, 'nina' if
    oni <= nina_threshold, else 'neutral' (NaN is neutral)."""
    out = pd.Series("neutral", index=oni.index, dtype=object)
    out[oni >= nino_threshold] = "nino"
    out[oni <= nina_threshold] = "nina"
    return out


def classify_phase(
    data: pd.DataFrame | pd.Series,
    *,
    nino_threshold: float = NINO_THRESHOLD,
    nina_threshold: float = NINA_THRESHOLD,
    min_run: int = MIN_RUN,
) -> pd.Series:
    """ENSO phase per month using the CPC run-length rule.

    `data` is a Series of ONI values indexed by month start dates (DatetimeIndex), or a
    DataFrame with an `oni` column and a `date` column or DatetimeIndex. A month gets
    'nino'/'nina' only if it lies in a run of >= `min_run` consecutive calendar months at or
    beyond the threshold (+0.5 / -0.5 inclusive); runs are broken by NaN or by a gap in the
    monthly sequence. Everything else is 'neutral'. The result keeps the input's order/index.
    """
    oni = _oni_series(data)
    dates = pd.DatetimeIndex(oni.index)
    single = above_threshold(oni, nino_threshold=nino_threshold, nina_threshold=nina_threshold).to_numpy()
    month_no = pd.Series(dates.year * 12 + dates.month).to_numpy()
    order = month_no.argsort(kind="stable")
    ordered = pd.DataFrame({"m": month_no[order], "cls": single[order]})
    new_run = (ordered["m"].diff() != 1) | (ordered["cls"] != ordered["cls"].shift())
    run_id = new_run.cumsum()
    run_len = ordered.groupby(run_id)["cls"].transform("size")
    qualifies = (ordered["cls"] != "neutral") & (run_len >= min_run)
    phase_sorted = ordered["cls"].where(qualifies, "neutral").to_numpy()
    phase = pd.Series(index=oni.index, dtype=object)
    phase.iloc[order] = phase_sorted
    return phase


def build_enso(text: str) -> pd.DataFrame:
    """Parse raw ONI text into date, season, oni, above_threshold, phase."""
    df = parse_oni(text)
    series = pd.Series(df["oni"].to_numpy(), index=pd.DatetimeIndex(df["date"]))
    df["above_threshold"] = above_threshold(series).to_numpy()
    df["phase"] = classify_phase(series).to_numpy()
    df.attrs.update({"source": SOURCE, "url": ONI_URL, "definition": DEFINITION})
    return df


def write_enso(df: pd.DataFrame, path: Path | str | None = None) -> Path:
    target = Path(path) if path is not None else default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target, index=False)  # pandas stores df.attrs in the parquet metadata
    return target


def read_enso(path: Path | str | None = None) -> pd.DataFrame:
    return pd.read_parquet(Path(path) if path is not None else default_path())


def run(path: Path | str | None = None, client: httpx.Client | None = None) -> Path:
    """Fetch, build and write the ONI table. Idempotent: overwrites the same file."""
    return write_enso(build_enso(fetch_oni(client=client)), path)


enso_app = typer.Typer(help="ENSO index (NOAA CPC ONI).", no_args_is_help=True)


@enso_app.command("build")
def build_command(
    path: Annotated[Path | None, typer.Option(help="Output parquet (default: data/interim/enso).")] = None,
) -> None:
    """Download ONI, classify ENSO phases and write the monthly parquet."""
    out = run(path)
    typer.echo(f"{out} ({len(read_enso(out))} rows)")
