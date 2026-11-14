"""Layer manifest contract (see docs/architecture.md)."""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class LayerManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1)
    kind: Literal["events", "points", "grid", "series", "polygons"]
    source: str = Field(min_length=1)
    period: str
    license: str = Field(min_length=1)
    updated_at: datetime
    experimental: bool = False
    files: list[str] = Field(min_length=1)

    @field_validator("period")
    @classmethod
    def _check_period(cls, v: str) -> str:
        parts = v.split("/")
        if len(parts) != 2:
            raise ValueError("period must be 'YYYY-MM-DD/YYYY-MM-DD'")
        try:
            start, end = (date.fromisoformat(p) for p in parts)
        except ValueError as exc:
            raise ValueError("period must contain ISO dates") from exc
        if any(len(p) != 10 for p in parts):
            raise ValueError("period must be 'YYYY-MM-DD/YYYY-MM-DD'")
        if start > end:
            raise ValueError("period start must not be after end")
        return v

    @field_validator("files")
    @classmethod
    def _check_files(cls, v: list[str]) -> list[str]:
        for f in v:
            if not f or f.startswith("/") or "\\" in f or ".." in f.split("/"):
                raise ValueError(f"file must be a plain relative path: {f!r}")
        if len(set(v)) != len(v):
            raise ValueError("files must be unique")
        return v

    @model_validator(mode="after")
    def _no_drive_paths(self) -> "LayerManifest":
        for f in self.files:
            if ":" in f.split("/")[0]:
                raise ValueError(f"file must be a plain relative path: {f!r}")
        return self

    @property
    def period_start(self) -> date:
        return date.fromisoformat(self.period.split("/")[0])

    @property
    def period_end(self) -> date:
        return date.fromisoformat(self.period.split("/")[1])


def load_manifest(path: Path) -> LayerManifest:
    return LayerManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def discover_layers(processed_dir: Path) -> list[LayerManifest]:
    found: list[LayerManifest] = []
    for path in sorted(Path(processed_dir).glob("*/manifest.json")):
        try:
            manifest = load_manifest(path)
        except Exception as exc:
            logger.warning("Skipping invalid manifest %s: %s", path, exc)
            continue
        if manifest.id != path.parent.name:
            logger.warning("Skipping %s: id %r does not match folder name", path, manifest.id)
            continue
        found.append(manifest)
    return sorted(found, key=lambda m: m.id)
