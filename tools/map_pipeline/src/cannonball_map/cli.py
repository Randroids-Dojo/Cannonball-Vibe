from pathlib import Path

import typer

from cannonball_map.flatbuffer_writer import write_flatbuffer
from cannonball_map.manifest import SourceManifest, validate_source
from cannonball_map.pipeline import build_route_graph
from cannonball_map.telemetry import summarize_telemetry

app = typer.Typer(no_args_is_help=True)


@app.command("validate-source")
def validate_source_command(
    source: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    manifest: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Verify provenance, license policy, acquisition date, and checksum."""
    validate_source(SourceManifest.load(manifest), source)
    typer.echo(f"source-ok: {source}")


@app.command()
def build(
    source: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    manifest: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    output: Path = typer.Option(Path("data/processed")),
    resample_meters: float = 25.0,
    chunk_meters: float = 2_000.0,
    snap_tolerance_meters: float = 10.0,
) -> None:
    """Build deterministic GeoPackage, audit JSON, and FlatBuffer route data."""
    package = build_route_graph(
        source,
        manifest,
        output,
        resample_meters=resample_meters,
        chunk_meters=chunk_meters,
        snap_tolerance_meters=snap_tolerance_meters,
    )
    runtime_path = output / "route_graph.cbrg"
    write_flatbuffer(package, runtime_path)
    typer.echo(f"built: {runtime_path} ({len(package['edges'])} edges)")


@app.command("telemetry-summary")
def telemetry_summary(
    telemetry: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Summarize local JSONL playtest telemetry with DuckDB."""
    for row in summarize_telemetry(telemetry):
        typer.echo(
            f"{row['name']}: count={row['event_count']} "
            f"avg_mps={row['average_speed_mps']} max_m={row['maximum_distance_meters']}"
        )


if __name__ == "__main__":
    app()
