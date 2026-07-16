import hashlib
import json
import urllib.request
from pathlib import Path

import typer

from cannonball_map.acquisition import UrllibArcGisTransport, acquire_nhpn
from cannonball_map.catalog import load_catalog, url_matches_prefix
from cannonball_map.elevation import ElevationMetadata, ElevationSampler
from cannonball_map.flatbuffer_writer import write_flatbuffer
from cannonball_map.lockfile import materialize_locked_role, validate_lock
from cannonball_map.manifest import SourceManifest, validate_source
from cannonball_map.pipeline import build_route_graph
from cannonball_map.telemetry import summarize_telemetry

app = typer.Typer(no_args_is_help=True)
DEFAULT_CATALOG = Path("data/sources/catalog.json")


@app.command("validate-source")
def validate_source_command(
    source: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    manifest: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Verify provenance, license policy, acquisition date, and checksum."""
    validate_source(SourceManifest.load(manifest), source, catalog)
    typer.echo(f"source-ok: {source}")


@app.command()
def build(
    source: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    manifest: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    output: Path = typer.Option(Path("data/processed")),
    resample_meters: float = 25.0,
    chunk_meters: float = 2_000.0,
    snap_tolerance_meters: float = 10.0,
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    elevation: Path | None = typer.Option(None, exists=True, file_okay=True, dir_okay=False),
    elevation_metadata: Path | None = typer.Option(
        None, exists=True, file_okay=True, dir_okay=False
    ),
    acquisition_lock: Path | None = typer.Option(
        None, exists=True, file_okay=True, dir_okay=False
    ),
) -> None:
    """Build deterministic GeoPackage, audit JSON, and FlatBuffer route data."""
    if (elevation is None) != (elevation_metadata is None):
        raise typer.BadParameter("elevation and elevation-metadata must be provided together")
    if elevation is not None and acquisition_lock is None:
        raise typer.BadParameter("acquisition-lock is required when elevation is provided")
    metadata = None
    if elevation_metadata:
        metadata = ElevationMetadata(**json.loads(elevation_metadata.read_text(encoding="utf-8")))
    lock_payload = validate_lock(acquisition_lock, catalog) if acquisition_lock else None
    lock_digest = (
        hashlib.sha256(acquisition_lock.read_bytes()).hexdigest() if acquisition_lock else ""
    )
    if lock_payload:
        locked_hashes = {
            artifact["sha256"]
            for acquisition in lock_payload["acquisitions"]
            for artifact in acquisition.get("artifacts", [])
        }
        source_hash = SourceManifest.load(manifest).sha256
        if source_hash not in locked_hashes:
            raise typer.BadParameter("source manifest hash is not present in acquisition-lock")
        if metadata and metadata.artifact_sha256 not in locked_hashes:
            raise typer.BadParameter("elevation artifact hash is not present in acquisition-lock")
        if metadata:
            elevation_source = next(
                acquisition
                for acquisition in lock_payload["acquisitions"]
                if acquisition["kind"] == "tnm-3dep-product"
            )
            product = elevation_source["product"]
            expected_metadata = {
                "product_id": product["source_id"],
                "product_title": product["title"],
                "product_resolution": product["resolution"],
                "raster_crs": product["raster_crs"],
                "horizontal_datum": product["horizontal_datum"],
                "vertical_datum": product["vertical_datum"],
                "elevation_units": product["elevation_units"],
            }
            for field, expected in expected_metadata.items():
                if getattr(metadata, field) != expected:
                    raise typer.BadParameter(
                        f"elevation metadata field '{field}' does not match acquisition-lock"
                    )
    if elevation and metadata:
        with ElevationSampler(elevation, metadata, "EPSG:5070") as sampler:
            package = build_route_graph(
                source,
                manifest,
                output,
                resample_meters=resample_meters,
                chunk_meters=chunk_meters,
                snap_tolerance_meters=snap_tolerance_meters,
                catalog_path=catalog,
                elevation_sampler=sampler,
                acquisition_lock_sha256=lock_digest,
            )
    else:
        package = build_route_graph(
            source,
            manifest,
            output,
            resample_meters=resample_meters,
            chunk_meters=chunk_meters,
            snap_tolerance_meters=snap_tolerance_meters,
            catalog_path=catalog,
            acquisition_lock_sha256=lock_digest,
        )
    runtime_path = output / "route_graph.cbrg"
    write_flatbuffer(package, runtime_path)
    typer.echo(f"built: {runtime_path} ({len(package['edges'])} edges)")


@app.command("validate-lock")
def validate_lock_command(
    lock: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Validate a source lock and every checked-in artifact without discovery."""
    payload = validate_lock(lock, catalog)
    typer.echo(f"lock-ok: {lock} ({len(payload['acquisitions'])} sources)")


@app.command("acquire-nhpn")
def acquire_nhpn_command(
    query_url: str = typer.Option(...),
    output: Path = typer.Option(..., file_okay=True, dir_okay=False),
    checkpoint: Path = typer.Option(..., file_okay=False, dir_okay=True),
    where: str = typer.Option("1=1"),
    bbox: str | None = typer.Option(None, help="xmin,ymin,xmax,ymax in EPSG:4326"),
    page_size: int = typer.Option(2_000, min=1, max=2_000),
) -> None:
    """Acquire a stable, resumable NHPN OBJECTID snapshot and raw feature pages."""
    query = {"where": where}
    if bbox:
        query.update(
            {
                "geometry": bbox,
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        )
    result = acquire_nhpn(
        UrllibArcGisTransport(),
        query_url,
        query,
        checkpoint,
        page_size=page_size,
    )
    payload = {
        "expected_count": result.expected_count,
        "object_ids": result.object_ids,
        "features": result.features,
        "retries": result.retries,
        "resumed_pages": result.resumed_pages,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(
        f"acquired: {output} ({result.expected_count} features, "
        f"retries={result.retries}, resumed={result.resumed_pages})"
    )


@app.command("materialize-lock")
def materialize_lock_command(
    lock: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    role: str = typer.Option(..., help="Exact acquired artifact role to materialize"),
    output: Path = typer.Option(..., file_okay=True, dir_okay=False),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Materialize one exact locked artifact without calling discovery services."""
    payload = validate_lock(lock, catalog)
    sources = load_catalog(catalog)
    approved_by_url = {
        artifact["url"]: sources[acquisition["source_id"]].allowed_url_prefixes
        for acquisition in payload["acquisitions"]
        for artifact in acquisition["artifacts"]
        if artifact.get("url")
    }

    def fetch(url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=120) as response:
            final_url = response.geturl()
            if not any(
                url_matches_prefix(final_url, prefix) for prefix in approved_by_url[url]
            ):
                raise ValueError(f"Artifact redirect is outside the catalog allowlist: {final_url}")
            return response.read()

    materialize_locked_role(payload, role, output, fetch)
    typer.echo(f"materialized: {output} ({role})")


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
