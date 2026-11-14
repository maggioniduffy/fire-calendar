"""Data directory locations. Resolved lazily so FIRECAL_DATA_DIR can be set after import."""

import os
from pathlib import Path

# backend/src/firecal/paths.py -> parents[3] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    return Path(os.environ.get("FIRECAL_DATA_DIR", REPO_ROOT / "data"))


def raw_dir() -> Path:
    return data_dir() / "raw"


def interim_dir() -> Path:
    return data_dir() / "interim"


def processed_dir() -> Path:
    return data_dir() / "processed"
