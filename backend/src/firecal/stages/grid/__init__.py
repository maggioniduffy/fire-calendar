"""Grid stage: filtered FIRMS detections aggregated to regular cells."""

from firecal.stages.grid.filters import FilterConfig, apply_filters
from firecal.stages.grid.grid import build_grid, cell_ids, grid_counts

__all__ = ["FilterConfig", "apply_filters", "build_grid", "cell_ids", "grid_counts"]
