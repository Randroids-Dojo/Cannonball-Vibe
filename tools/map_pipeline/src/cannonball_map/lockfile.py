from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cannonball_map.catalog import load_catalog, require_catalog_source, url_matches_prefix
from cannonball_map.manifest import SHA256_PATTERN, compute_sha256


@dataclass(frozen=True)
class LockedArtifact:
    role: str
    url: str
    sha256: str
    path: Path | None


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_lock(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported source lock schema.")
    return payload


def validate_lock(path: Path, catalog_path: Path) -> dict[str, Any]:
    payload = load_lock(path)
    root = path.parent.parent.parent
    actual_catalog = compute_sha256(catalog_path)
    if payload.get("catalog_sha256") != actual_catalog:
        raise ValueError("Source catalog hash drifted from the acquisition lock.")
    catalog = load_catalog(catalog_path)
    artifact_by_hash: dict[str, dict[str, Any]] = {}
    for acquisition in payload.get("acquisitions", []):
        catalog_source = require_catalog_source(
            catalog,
            source_id=acquisition["source_id"],
            publisher=acquisition["publisher"],
            license_status=acquisition["license_status"],
            source_url=acquisition["source_url"],
            license_evidence_url=acquisition["license_evidence_url"],
        )
        artifacts = acquisition.get("artifacts", [])
        if not artifacts:
            raise ValueError(f"Source '{acquisition['source_id']}' has no locked artifacts.")
        for artifact in artifacts:
            source_url = artifact.get("url") or artifact.get("source_url", "")
            if not any(
                url_matches_prefix(source_url, prefix)
                for prefix in catalog_source.allowed_url_prefixes
            ):
                raise ValueError(
                    f"Artifact '{artifact.get('role')}' URL is outside the catalog allowlist."
                )
            digest = artifact.get("sha256", "")
            if not SHA256_PATTERN.fullmatch(digest):
                raise ValueError(f"Artifact '{artifact.get('role')}' has an invalid SHA-256.")
            if digest in artifact_by_hash:
                raise ValueError(f"Artifact SHA-256 is repeated: {digest}.")
            artifact_by_hash[digest] = artifact
            if artifact.get("url"):
                if not artifact.get("acquired_at"):
                    raise ValueError(f"Artifact '{artifact.get('role')}' has no acquisition time.")
                response = artifact.get("response", {})
                if response.get("status") != 200 or not response.get("content_type"):
                    raise ValueError(
                        f"Artifact '{artifact.get('role')}' has incomplete response metadata."
                    )
                if int(artifact.get("byte_count", 0)) <= 0:
                    raise ValueError(f"Artifact '{artifact.get('role')}' has no byte count.")
            elif artifact.get("derivation"):
                if not artifact.get("derived_at") or not artifact.get("path"):
                    raise ValueError(
                        f"Derived artifact '{artifact.get('role')}' has incomplete provenance."
                    )
            else:
                raise ValueError(
                    f"Artifact '{artifact.get('role')}' is neither acquired nor derived."
                )
            local = artifact.get("path")
            if local:
                candidate = Path(local)
                if candidate.is_absolute() or ".." in candidate.parts:
                    raise ValueError(f"Locked artifact path is unsafe: {local}")
                local_path = (root / candidate).resolve()
                if not local_path.is_relative_to(root.resolve()):
                    raise ValueError(f"Locked artifact escapes the repository: {local}")
                if not local_path.is_file():
                    raise ValueError(f"Locked artifact is missing: {local}")
                actual = compute_sha256(local_path)
                if actual != digest:
                    message = (
                        f"Locked artifact hash drift for '{local}': "
                        f"expected {digest}, got {actual}."
                    )
                    raise ValueError(message)
            ancestors = artifact.get("derived_from_sha256", [])
            if not isinstance(ancestors, list) or any(
                not SHA256_PATTERN.fullmatch(ancestor) for ancestor in ancestors
            ):
                raise ValueError(f"Artifact '{artifact.get('role')}' has invalid ancestry.")
            if artifact.get("derivation") and not ancestors:
                raise ValueError(f"Derived artifact '{artifact.get('role')}' has no ancestry.")
    for digest, artifact in artifact_by_hash.items():
        for ancestor in artifact.get("derived_from_sha256", []):
            if ancestor not in artifact_by_hash:
                raise ValueError(
                    f"Artifact '{artifact.get('role')}' has dangling ancestor {ancestor}."
                )
        _validate_acyclic_ancestry(digest, artifact_by_hash, set())
    nhpn = next(
        (item for item in payload["acquisitions"] if item["kind"] == "arcgis-feature-layer"),
        None,
    )
    if nhpn is None:
        raise ValueError("Lock has no NHPN acquisition.")
    ids = nhpn["snapshot"]["object_ids"]
    if ids != sorted(set(ids)):
        raise ValueError("NHPN object IDs are not unique and stably sorted.")
    if len(ids) != nhpn["snapshot"]["expected_count"]:
        raise ValueError("NHPN expected count does not match its locked ID snapshot.")
    if canonical_sha256(ids) != nhpn["snapshot"]["object_ids_sha256"]:
        raise ValueError("NHPN object ID snapshot hash drifted.")
    if nhpn["snapshot"]["page_size"] > nhpn["service"]["max_record_count"]:
        raise ValueError("NHPN page size exceeds the locked service limit.")
    required_nhpn_roles = {
        "official-corridor-response",
        "official-corridor-geojson",
        "official-corridor-manifest",
    }
    if required_nhpn_roles != {artifact["role"] for artifact in nhpn["artifacts"]}:
        raise ValueError("NHPN lock does not contain the required artifact set.")
    elevation = next(
        (item for item in payload["acquisitions"] if item["kind"] == "tnm-3dep-product"),
        None,
    )
    if elevation is None:
        raise ValueError("Lock has no 3DEP acquisition.")
    source = catalog[elevation["source_id"]]
    locked_product = elevation["product"]
    discovery = elevation["discovery"]
    matches_catalog = any(
        product["dataset"] == discovery["dataset"]
        and product["format"] == discovery["format"]
        and product["extent"] == discovery["extent"]
        and product["resolution"] == locked_product["resolution"]
        for product in source.raw.get("products", [])
    )
    if not matches_catalog:
        raise ValueError("3DEP product does not match an explicit catalog product.")
    for field in (
        "source_id",
        "title",
        "publication_date",
        "raster_crs",
        "horizontal_datum",
        "vertical_datum",
        "elevation_units",
    ):
        if not str(locked_product.get(field, "")).strip():
            raise ValueError(f"3DEP product is missing required field '{field}'.")
    if int(discovery.get("candidate_count", 0)) < 1 or not discovery.get("request"):
        raise ValueError("3DEP discovery contract is incomplete.")
    if not SHA256_PATTERN.fullmatch(discovery.get("response_sha256", "")):
        raise ValueError("3DEP discovery response hash is invalid.")
    required_elevation_roles = {
        "full-historical-geotiff",
        "fgdc-product-metadata",
        "official-corridor-crop",
        "corridor-crop-metadata",
    }
    if required_elevation_roles != {
        artifact["role"] for artifact in elevation["artifacts"]
    }:
        raise ValueError("3DEP lock does not contain the required artifact set.")
    return payload


def _validate_acyclic_ancestry(
    digest: str,
    artifacts: dict[str, dict[str, Any]],
    visiting: set[str],
) -> None:
    if digest in visiting:
        raise ValueError("Artifact ancestry contains a cycle.")
    visiting.add(digest)
    for ancestor in artifacts[digest].get("derived_from_sha256", []):
        if ancestor in artifacts:
            _validate_acyclic_ancestry(ancestor, artifacts, visiting)
    visiting.remove(digest)


def materialize_locked_artifact(
    artifact: LockedArtifact,
    destination: Path,
    fetch: Callable[[str], bytes],
) -> Path:
    """Fetch an exact locked URL. Discovery is intentionally not accepted here."""
    payload = fetch(artifact.url)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != artifact.sha256:
        message = (
            f"Downloaded hash drift for '{artifact.role}': "
            f"expected {artifact.sha256}, got {actual}."
        )
        raise ValueError(message)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return destination


def materialize_locked_role(
    payload: dict[str, Any],
    role: str,
    destination: Path,
    fetch: Callable[[str], bytes],
) -> Path:
    artifacts = [
        artifact
        for acquisition in payload["acquisitions"]
        for artifact in acquisition["artifacts"]
    ]
    matches = [artifact for artifact in artifacts if artifact["role"] == role]
    if len(matches) != 1:
        raise ValueError(f"Artifact role must identify exactly one artifact: {role}")
    by_hash = {artifact["sha256"]: artifact for artifact in artifacts}

    def materialize(artifact: dict[str, Any], output: Path) -> Path:
        if artifact.get("url"):
            locked = LockedArtifact(
                artifact["role"], artifact["url"], artifact["sha256"], None
            )
            return materialize_locked_artifact(locked, output, fetch)
        recipe = artifact["derivation"]
        kind = recipe["kind"]
        if kind == "static-canonical-json-v1":
            encoded = (json.dumps(recipe["content"], indent=2, sort_keys=True) + "\n").encode()
            return _write_verified_bytes(output, encoded, artifact["sha256"])
        ancestors = artifact["derived_from_sha256"]
        with tempfile.TemporaryDirectory(prefix="cannonball-lock-") as temporary:
            parent = by_hash[ancestors[0]]
            parent_path = materialize(parent, Path(temporary) / "parent")
            if kind == "canonical-json-v1":
                value = json.loads(parent_path.read_text(encoding="utf-8"))
                encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
                return _write_verified_bytes(output, encoded, artifact["sha256"])
            if kind == "raster-window-v1":
                return _materialize_raster_window(parent_path, output, recipe, artifact["sha256"])
        raise ValueError(f"Unsupported locked derivation kind: {kind}")

    return materialize(matches[0], destination)


def _write_verified_bytes(destination: Path, payload: bytes, expected: str) -> Path:
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"Derived artifact hash drift: expected {expected}, got {actual}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return destination


def _materialize_raster_window(
    parent: Path,
    destination: Path,
    recipe: dict[str, Any],
    expected: str,
) -> Path:
    import rasterio
    from rasterio.windows import Window

    window = Window(
        recipe["column_offset"],
        recipe["row_offset"],
        recipe["width"],
        recipe["height"],
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with rasterio.open(parent) as source:
        data = source.read(window=window)
        profile = source.profile.copy()
        profile.update(
            width=data.shape[2],
            height=data.shape[1],
            transform=source.window_transform(window),
            compress=recipe["compression"],
            predictor=recipe["predictor"],
            tiled=True,
            blockxsize=recipe["block_size"],
            blockysize=recipe["block_size"],
        )
        with rasterio.open(temporary, "w", **profile) as target:
            target.write(data)
    actual = compute_sha256(temporary)
    if actual != expected:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"Derived raster hash drift: expected {expected}, got {actual}.")
    temporary.replace(destination)
    return destination
