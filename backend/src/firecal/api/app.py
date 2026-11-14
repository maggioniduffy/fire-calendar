"""Read-only FastAPI app serving layers from data/processed."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from firecal import paths
from firecal.layers.manifest import LayerManifest, discover_layers


def create_app(processed_dir: Path | None = None) -> FastAPI:
    api = FastAPI(title="firecal", description="Read-only fire calendar API")

    def root() -> Path:
        return processed_dir if processed_dir is not None else paths.processed_dir()

    def find(layer_id: str) -> LayerManifest:
        for manifest in discover_layers(root()):
            if manifest.id == layer_id:
                return manifest
        raise HTTPException(status_code=404, detail="layer not found")

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

    return api


app = create_app()
