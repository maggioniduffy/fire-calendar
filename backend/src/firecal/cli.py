"""Command line entry point: `firecal <stage> <step>`."""

import typer

from firecal.io.burned_area import burned_app
from firecal.io.enso import enso_app
from firecal.io.firms import firms_app
from firecal.stages.enso_lite.cli import lite_command
from firecal.stages.harmonize.commands import harmonize_app
from firecal.stages.harmonize.series_cli import series_app
from firecal.stages.publish.cli import boundaries_app, publish_app

app = typer.Typer(no_args_is_help=True, help="Harmonized MODIS + VIIRS fire calendar.")

enso_app.command("lite")(lite_command)
app.add_typer(enso_app, name="enso", help="ONI and ENSO phase per month (SA0.9).")
app.add_typer(firms_app, name="firms", help="FIRMS download, ingest, grid and profile (phase 1).")
app.add_typer(burned_app, name="burned", help="MCD64A1 burned area download and grid (SA2.9).")
app.add_typer(harmonize_app, name="harmonize", help="MODIS/VIIRS harmonization baselines (phase 2).")
app.add_typer(series_app, name="series", help="Harmonized MODIS-eq / VIIRS-eq series layer (SA2.11).")
app.add_typer(boundaries_app, name="boundaries", help="Administrative boundaries (SA7.2).")
app.add_typer(publish_app, name="publish", help="Static export for the online demo (SA7.2).")


@app.callback()
def main() -> None:
    """Harmonized MODIS + VIIRS fire calendar."""


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
) -> None:
    """Run the read-only API."""
    import uvicorn

    uvicorn.run("firecal.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
