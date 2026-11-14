"""Command line entry point: `firecal <stage> <step>`."""

import typer

app = typer.Typer(no_args_is_help=True, help="Harmonized MODIS + VIIRS fire calendar.")

# Other modules register sub-commands here, e.g. app.add_typer(enso_app, name="enso").


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
