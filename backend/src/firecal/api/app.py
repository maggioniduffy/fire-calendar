"""Read-only FastAPI app serving layers from data/processed."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response

from firecal import paths
from firecal.layers.manifest import LayerManifest, discover_layers
from firecal.stages.calendar import cells as cal_cells
from firecal.stages.calendar import export as cal_export
from firecal.stages.calendar import service as cal_service
from firecal.stages.calendar.store import LAYER_ID, SeriesStore


def create_app(processed_dir: Path | None = None, detections_dir: Path | None = None) -> FastAPI:
    api = FastAPI(title="firecal", description="Read-only fire calendar API")
    cache: dict[str, object] = {}

    def root() -> Path:
        return processed_dir if processed_dir is not None else paths.processed_dir()

    def find(layer_id: str) -> LayerManifest:
        for manifest in discover_layers(root()):
            if manifest.id == layer_id:
                return manifest
        raise HTTPException(status_code=404, detail="layer not found")

    def get_store() -> SeriesStore:
        """Store of the harmonized layer, built lazily and rebuilt when its manifest changes."""
        manifest = root() / LAYER_ID / "manifest.json"
        try:
            stamp = manifest.stat().st_mtime_ns
            if cache.get("stamp") != stamp:
                store = SeriesStore(root() / LAYER_ID)
                store.manifest  # noqa: B018  (fail early on a missing or invalid manifest)
                cache.update(stamp=stamp, store=store)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="harmonized layer not built") from exc
        return cache["store"]  # type: ignore[return-value]

    def run(fn, *args):
        try:
            return fn(*args)
        except cal_export.DetectionsUnavailableError as exc:
            raise HTTPException(
                status_code=404, detail="raw detections not available on this server; use kind=cells"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/layers")
    def list_layers() -> list[LayerManifest]:
        return discover_layers(root())

    @api.get("/layers/{layer_id}")
    def get_layer(layer_id: str) -> LayerManifest:
        return find(layer_id)

    @api.get("/layers/{layer_id}/data")
    def get_layer_data(layer_id: str, file: str | None = Query(default=None)) -> FileResponse:
        manifest = find(layer_id)
        name = file if file is not None else manifest.files[0]
        if name not in manifest.files:
            raise HTTPException(status_code=404, detail="file not listed in manifest")
        path = root() / manifest.id / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return FileResponse(path)

    @api.post("/calendar")
    def calendar(req: cal_service.CalendarRequest) -> dict:
        return run(cal_service.calendar_payload, get_store(), req)

    @api.post("/stats")
    def stats(req: cal_service.StatsRequest) -> dict:
        return run(cal_service.stats_payload, get_store(), req)

    @api.post("/cells")
    def cells(req: cal_cells.CellsRequest) -> dict:
        return run(cal_cells.cells_payload, get_store(), req)

    @api.post("/detections")
    def detections(req: cal_cells.DetectionsRequest) -> dict:
        return run(cal_cells.detections_payload, get_store(), req, detections_dir)

    @api.post("/export.csv")
    def export_csv(req: cal_export.ExportRequest) -> Response:
        store = get_store()
        text, filename = run(cal_export.export_csv, store, req, req.kind, detections_dir)
        prov = cal_export.provenance(store, req.kind)
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Firecal-Source": prov["source"],
            "X-Firecal-Period": prov["period"],
            "X-Firecal-Method": prov["method"],
            "X-Firecal-Calibration": prov["calibration_version"],
        }
        if req.kind == "detections":
            headers["X-Firecal-Note"] = cal_export.DETECTIONS_NOTE
        return Response(text, media_type="text/csv; charset=utf-8", headers=headers)

    return api


app = create_app()
