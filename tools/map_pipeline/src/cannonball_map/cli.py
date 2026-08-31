import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

import typer

from cannonball_map.acquisition import UrllibArcGisTransport, acquire_nhpn
from cannonball_map.catalog import load_catalog, url_matches_prefix
from cannonball_map.continental import (
    acquire_continental_nhpn_candidates,
    audit_continental_milepost_gaps,
    derive_continental_edge_path_lock,
    derive_continental_transfer_lock,
    probe_continental_break_ends,
    probe_continental_gap_interiors,
    probe_continental_geometric_breaks,
    probe_continental_milepost_gaps,
    probe_continental_nhs_breaks,
    validate_continental_break_dispositions,
    validate_continental_edge_path_lock,
    validate_continental_route_lock,
    validate_continental_transfer_lock,
)
from cannonball_map.elevation import ElevationMetadata, ElevationSampler
from cannonball_map.lockfile import materialize_locked_role, validate_lock
from cannonball_map.manifest import SourceManifest, validate_source
from cannonball_map.pipeline import GRADE_SMOOTHING_METERS, build_route_graph
from cannonball_map.sharding import write_sharded_package
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
    grade_smoothing_meters: float = typer.Option(
        GRADE_SMOOTHING_METERS,
        "--grade-smoothing-meters",
        help=(
            "Vertical-curve grading window over the corridor elevation profile. "
            "The default is the ratified shipped window; 0 disables grading and "
            "reproduces the ungraded profile."
        ),
    ),
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
    if elevation is None:
        raise typer.BadParameter(
            "runtime schema 5 requires elevation, elevation-metadata, and acquisition-lock"
        )
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
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_output = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-audit-staging-", dir=output.parent)
    )
    try:
        if elevation and metadata:
            with ElevationSampler(elevation, metadata, "EPSG:5070") as sampler:
                package = build_route_graph(
                    source,
                    manifest,
                    audit_output,
                    resample_meters=resample_meters,
                    grade_smoothing_meters=grade_smoothing_meters,
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
                audit_output,
                resample_meters=resample_meters,
                grade_smoothing_meters=grade_smoothing_meters,
                chunk_meters=chunk_meters,
                snap_tolerance_meters=snap_tolerance_meters,
                catalog_path=catalog,
                acquisition_lock_sha256=lock_digest,
            )
        package = write_sharded_package(
            package,
            output,
            audit_artifacts={"normalized.gpkg": audit_output / "normalized.gpkg"},
        )
    finally:
        shutil.rmtree(audit_output, ignore_errors=True)
    pointer = json.loads((output / "current-package.json").read_text(encoding="utf-8"))
    runtime_path = output / pointer["root_relative_path"]
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


@app.command("acquire-continental-nhpn")
def acquire_continental_nhpn_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    output: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        file_okay=True,
        dir_okay=False,
    ),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        file_okay=False,
        dir_okay=True,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    page_size: int = typer.Option(2_000, min=1, max=2_000),
) -> None:
    """Lock NHPN route-family candidate snapshots for every continental segment."""
    payload = acquire_continental_nhpn_candidates(
        selection,
        catalog,
        output,
        cache,
        page_size=page_size,
    )
    total = payload["nhpn"]["candidate_union"]["expected_count"]
    typer.echo(f"continental-nhpn-locked: {output} ({total} unique candidates)")


@app.command("validate-continental-lock")
def validate_continental_lock_command(
    lock: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    require_complete: bool = typer.Option(False),
) -> None:
    """Validate the continental candidate lock and optionally require final completion."""
    try:
        payload = validate_continental_route_lock(
            lock,
            catalog,
            selection,
            require_complete=require_complete,
        )
    except ValueError as error:
        typer.echo(f"continental-lock-invalid: {error}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"continental-lock-ok: {lock} ({payload['status']})")


@app.command("derive-continental-transfers")
def derive_continental_transfers_command(
    policy: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    output: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """Derive exact transfer anchors from the locked NHPN response cache."""
    try:
        payload = derive_continental_transfer_lock(
            policy,
            selection,
            lock,
            catalog,
            cache,
            output,
        )
    except ValueError as error:
        typer.echo(f"continental-transfers-invalid: {error}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(
        f"continental-transfers-derived: {output} "
        f"({len(payload['transfer_nodes'])} nodes)"
    )


@app.command("validate-continental-transfers")
def validate_continental_transfers_command(
    transfer_lock: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Validate the transfer-node lock without requiring downloaded responses."""
    try:
        payload = validate_continental_transfer_lock(
            transfer_lock,
            policy,
            selection,
            lock,
            catalog,
        )
    except ValueError as error:
        typer.echo(f"continental-transfers-invalid: {error}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(
        f"continental-transfers-ok: {transfer_lock} "
        f"({len(payload['transfer_nodes'])} nodes)"
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


@app.command("derive-continental-edge-paths")
def derive_continental_edge_paths_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        help="Locked route selection.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        help="Locked NHPN candidate acquisition.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    transfer_lock: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        help="Locked transfer nodes.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        help="Transfer node policy.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(
        Path("data/sources/catalog.json"),
        help="Source catalog.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        help="Locked NHPN response cache.",
        exists=True, file_okay=False, dir_okay=True,
    ),
    output: Path = typer.Option(
        Path("data/routes/continental/edge-path-lock.v1.json"),
        help="Edge-path lock to write.",
        file_okay=True, dir_okay=False,
    ),
) -> None:
    """Audit NHPN endpoint connectivity from checksum-locked responses."""
    try:
        payload = derive_continental_edge_path_lock(
            selection, route_lock, transfer_lock, policy, catalog, cache, output
        )
    except ValueError as error:
        typer.echo(f"continental-edge-paths-failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"continental-edge-paths: {output} "
        f"({payload['connected_segment_count']}/{payload['segment_count']} connected, "
        f"{payload['status']})"
    )


@app.command("validate-continental-edge-paths")
def validate_continental_edge_paths_command(
    edge_path_lock: Path = typer.Argument(
        Path("data/routes/continental/edge-path-lock.v1.json"),
        help="Edge-path lock to validate.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    transfer_lock: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        help="Locked transfer nodes.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        help="Transfer node policy.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        help="Locked route selection.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        help="Locked NHPN candidate acquisition.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(
        Path("data/sources/catalog.json"),
        help="Source catalog.",
        exists=True, file_okay=True, dir_okay=False,
    ),
) -> None:
    """Validate the edge-path lock without the ignored NHPN response cache."""
    try:
        payload = validate_continental_edge_path_lock(
            edge_path_lock, transfer_lock, policy, selection, route_lock, catalog
        )
    except ValueError as error:
        typer.echo(f"continental-edge-paths-invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"continental-edge-paths-ok: {edge_path_lock} "
        f"({payload['connected_segment_count']}/{payload['segment_count']} connected)"
    )


@app.command("audit-continental-milepost-gaps")
def audit_continental_milepost_gaps_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        exists=True, file_okay=False, dir_okay=True,
    ),
    output: Path | None = typer.Option(None, file_okay=True, dir_okay=False),
) -> None:
    """Characterise milepost gaps in the locked candidate set. Changes no lock."""
    try:
        payload = audit_continental_milepost_gaps(selection, route_lock, catalog, cache)
    except ValueError as error:
        typer.echo(f"continental-milepost-gaps-failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    typer.echo(
        f"continental-milepost-gaps: {payload['gap_count']} gaps, "
        f"{payload['gaps_within_source_quantum']} within the "
        f"{payload['source_milepost_quantum_meters']:.2f} m source quantum, "
        f"{payload['gaps_over_one_mile']} over a mile"
    )


@app.command("probe-continental-milepost-gaps")
def probe_continental_milepost_gaps_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        help="Locked NHPN response cache.",
        exists=True, file_okay=False, dir_okay=True,
    ),
    probe_cache: Path = typer.Option(
        Path(".tools/continental/nhpn-gap-probe"),
        help="Ignored cache for the probe's own whole-key responses.",
        file_okay=False, dir_okay=True,
    ),
    minimum_gap_miles: float = typer.Option(1.0, min=0.0),
    page_size: int = typer.Option(2_000, min=1, max=2_000),
    output: Path | None = typer.Option(None, file_okay=True, dir_okay=False),
) -> None:
    """Probe what NHPN carries inside the locked gaps. Diagnostic; changes no lock."""
    try:
        payload = probe_continental_milepost_gaps(
            selection,
            route_lock,
            catalog,
            cache,
            probe_cache,
            page_size=page_size,
            minimum_gap_miles=minimum_gap_miles,
        )
    except ValueError as error:
        typer.echo(f"continental-gap-probe-failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    typer.echo(
        f"continental-gap-probe: {payload['gap_count']} gaps probed, "
        f"{payload['gaps_fully_covered']} fully covered by records on their key, "
        f"{payload['gaps_partially_covered']} partially covered, "
        f"{payload['gaps_no_records']} without records on their key, "
        f"{payload['predicate_anomaly_count']} predicate anomalies"
    )


@app.command("probe-continental-geometric-breaks")
def probe_continental_geometric_breaks_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    transfer_lock: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    edge_path_lock: Path = typer.Option(
        Path("data/routes/continental/edge-path-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        help="Locked NHPN response cache.",
        exists=True, file_okay=False, dir_okay=True,
    ),
    probe_cache: Path = typer.Option(
        Path(".tools/continental/nhpn-geometric-probe"),
        help="Ignored cache for the probe's bounded spatial responses.",
        file_okay=False, dir_okay=True,
    ),
    padding_meters: float = typer.Option(250.0, min=1.0),
    page_size: int = typer.Option(2_000, min=1, max=2_000),
    output: Path | None = typer.Option(None, file_okay=True, dir_okay=False),
) -> None:
    """Probe source topology around locked disconnected graph sites."""
    try:
        payload = probe_continental_geometric_breaks(
            selection,
            route_lock,
            transfer_lock,
            policy,
            edge_path_lock,
            catalog,
            cache,
            probe_cache,
            page_size=page_size,
            padding_meters=padding_meters,
        )
    except ValueError as error:
        typer.echo(f"continental-geometric-probe-failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    typer.echo(
        f"continental-geometric-probe: {payload['site_count']} sites probed, "
        f"{payload['source_connection_count']} source connections found"
    )


@app.command("probe-continental-break-ends")
def probe_continental_break_ends_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    transfer_lock: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    edge_path_lock: Path = typer.Option(
        Path("data/routes/continental/edge-path-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        help="Locked NHPN response cache.",
        exists=True, file_okay=False, dir_okay=True,
    ),
    probe_cache: Path = typer.Option(
        Path(".tools/continental/nhpn-break-probe"),
        help="Ignored cache for the census's per-end spatial responses.",
        file_okay=False, dir_okay=True,
    ),
    page_size: int = typer.Option(2_000, min=1, max=2_000),
    output: Path | None = typer.Option(None, file_okay=True, dir_okay=False),
) -> None:
    """Census what joins every unconnected-segment break end. Changes no lock.

    Complements probe-continental-geometric-breaks: that command tests for a
    local unfiltered source path across each bounded component-pair site; this
    one reports, per chain end, every joining feature with its keys, signs, and
    measured offsets, including where no local source path exists.
    """
    try:
        payload = probe_continental_break_ends(
            selection,
            route_lock,
            transfer_lock,
            policy,
            edge_path_lock,
            catalog,
            cache,
            probe_cache,
            page_size=page_size,
        )
    except ValueError as error:
        typer.echo(f"continental-break-ends-probe-failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    ends = [
        end for segment in payload["segments"] for end in segment["break_ends"]
    ]
    voids = sum(1 for end in ends if end["classification"] == "source_void_beyond_lock")
    asserted = sum(1 for end in ends if end["classification"] == "asserted_join_present")
    typer.echo(
        f"continental-break-ends: {payload['unconnected_segment_count']} segments, "
        f"{payload['break_end_count']} break ends probed, "
        f"{asserted} with an asserted endpoint join, "
        f"{voids} with nothing beyond the locked records"
    )


@app.command("probe-continental-gap-interiors")
def probe_continental_gap_interiors_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    transfer_lock: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    edge_path_lock: Path = typer.Option(
        Path("data/routes/continental/edge-path-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        help="Locked NHPN response cache.",
        exists=True, file_okay=False, dir_okay=True,
    ),
    probe_cache: Path = typer.Option(
        Path(".tools/continental/nhpn-interior-sweep"),
        help="Ignored cache for the sweep's windowed spatial responses.",
        file_okay=False, dir_okay=True,
    ),
    page_size: int = typer.Option(2_000, min=1, max=2_000),
    output: Path | None = typer.Option(None, file_okay=True, dir_okay=False),
) -> None:
    """Sweep the break-pair interiors wider than the census windows. Changes no lock.

    Closes the census's named evidence hole: the pair interiors wider than two
    500 m windows, tiled with the same unfiltered envelope machinery and
    classified against each pair's end-to-end chord.
    """
    try:
        payload = probe_continental_gap_interiors(
            selection,
            route_lock,
            transfer_lock,
            policy,
            edge_path_lock,
            catalog,
            cache,
            probe_cache,
            page_size=page_size,
        )
    except ValueError as error:
        typer.echo(f"continental-interior-sweep-failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    swept = [gap for segment in payload["segments"] for gap in segment["swept_gaps"]]
    on_axis = sum(1 for gap in swept if gap["classification"] == "mainline_candidate_on_axis")
    voids = sum(1 for gap in swept if gap["classification"] == "interior_void_beyond_lock")
    typer.echo(
        f"continental-interior-sweep: {payload['swept_gap_count']} gap interiors swept "
        f"({payload['swept_meters_total'] / 1000.0:.1f} km), "
        f"{on_axis} with an on-axis aligned feature, "
        f"{voids} with nothing beyond the locked records"
    )


@app.command("probe-continental-nhs-breaks")
def probe_continental_nhs_breaks_command(
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    transfer_lock: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    edge_path_lock: Path = typer.Option(
        Path("data/routes/continental/edge-path-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
    cache: Path = typer.Option(
        Path(".tools/continental/nhpn"),
        help="Locked NHPN response cache.",
        exists=True, file_okay=False, dir_okay=True,
    ),
    probe_cache: Path = typer.Option(
        Path(".tools/continental/nhs-break-probe"),
        help="Ignored cache for the NHS probe's spatial responses.",
        file_okay=False, dir_okay=True,
    ),
    expected_metadata_sha256: str | None = typer.Option(
        None,
        help="Refuse the probe when the live NHS metadata hash differs from this.",
    ),
    page_size: int = typer.Option(2_000, min=1, max=2_000),
    output: Path | None = typer.Option(None, file_okay=True, dir_okay=False),
) -> None:
    """Probe the ADR-0026 NHS source at the break sites and swept interiors.

    Records what NHS asserts - route identity, measures, geometric continuity -
    at every bounded break site and inside every swept gap interior, with the
    same paging, checkpoint, and hash discipline as the NHPN acquisition.
    Changes no lock and selects nothing.
    """
    try:
        payload = probe_continental_nhs_breaks(
            selection,
            route_lock,
            transfer_lock,
            policy,
            edge_path_lock,
            catalog,
            cache,
            probe_cache,
            expected_metadata_sha256=expected_metadata_sha256,
            page_size=page_size,
        )
    except ValueError as error:
        typer.echo(f"continental-nhs-probe-failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    typer.echo(
        f"continental-nhs-probe: {payload['site_count']} sites and "
        f"{payload['interior_gap_count']} gap interiors probed, "
        f"{payload['sites_with_nhs_between_ends']} sites with NHS geometry "
        "within the lens of both ends"
    )


@app.command("validate-continental-break-dispositions")
def validate_continental_break_dispositions_command(
    disposition: Path = typer.Argument(
        Path("data/routes/continental/break-disposition.v1.json"),
        help="Q-034 per-site disposition record to validate.",
        exists=True, file_okay=True, dir_okay=False,
    ),
    selection: Path = typer.Option(
        Path("data/routes/continental/route-selection.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    route_lock: Path = typer.Option(
        Path("data/sources/continental-route-lock.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    transfer_lock: Path = typer.Option(
        Path("data/routes/continental/transfer-node-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    policy: Path = typer.Option(
        Path("data/routes/continental/transfer-node-policy.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    edge_path_lock: Path = typer.Option(
        Path("data/routes/continental/edge-path-lock.v1.json"),
        exists=True, file_okay=True, dir_okay=False,
    ),
    catalog: Path = typer.Option(DEFAULT_CATALOG, exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Validate the Q-034 break-disposition record without the response cache."""
    try:
        payload = validate_continental_break_dispositions(
            disposition,
            selection,
            route_lock,
            transfer_lock,
            policy,
            edge_path_lock,
            catalog,
        )
    except ValueError as error:
        typer.echo(f"continental-break-dispositions-invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    counts = ", ".join(
        f"{name}={count}"
        for name, count in sorted(payload["disposition_counts"].items())
    )
    typer.echo(
        f"continental-break-dispositions-ok: {disposition} "
        f"({payload['site_count']} sites: {counts})"
    )
