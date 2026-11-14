"""Command line entry point: `firecal <stage> <step>`."""

import typer

from firecal.io.enso import enso_app

app = typer.Typer(no_args_is_help=True, help="Harmonized MODIS + VIIRS fire calendar.")

app.add_typer(enso_app, name="enso", help="ONI and ENSO phase per month (SA0.9).")


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
