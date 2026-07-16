from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cannonball_map.catalog import load_catalog, require_catalog_source

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SourceManifest:
    source_id: str
    publisher: str
    source_url: str
    acquired_on: str
    license_status: str
    license_evidence_url: str
    sha256: str
    derived_from: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: Path) -> SourceManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            source_id=data["source_id"],
            publisher=data["publisher"],
            source_url=data["source_url"],
            acquired_on=data["acquired_on"],
            license_status=data["license_status"],
            license_evidence_url=data["license_evidence_url"],
            sha256=data["sha256"].lower(),
            derived_from=tuple(data.get("derived_from", [])),
        )


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_source(
    manifest: SourceManifest,
    source_path: Path,
    catalog_path: Path | None = None,
) -> None:
    if manifest.license_status != "public_domain":
        raise ValueError(
            f"Source '{manifest.source_id}' is '{manifest.license_status}', not public_domain."
        )
    if any(
        "openstreetmap" in ancestor.casefold() or ancestor.casefold() == "osm"
        for ancestor in manifest.derived_from
    ):
        raise ValueError("OpenStreetMap-derived data is prohibited by the project source policy.")
    if not manifest.license_evidence_url.startswith("https://"):
        raise ValueError("A public HTTPS license-evidence URL is required.")
    try:
        date.fromisoformat(manifest.acquired_on)
    except ValueError as error:
        raise ValueError("acquired_on must use ISO 8601 YYYY-MM-DD format.") from error
    if not SHA256_PATTERN.fullmatch(manifest.sha256):
        raise ValueError("sha256 must be a complete lowercase SHA-256 digest.")
    actual = compute_sha256(source_path)
    if actual != manifest.sha256:
        raise ValueError(f"SHA-256 mismatch: expected {manifest.sha256}, got {actual}.")
    if catalog_path is not None:
        require_catalog_source(
            load_catalog(catalog_path),
            source_id=manifest.source_id,
            publisher=manifest.publisher,
            license_status=manifest.license_status,
            source_url=manifest.source_url,
            license_evidence_url=manifest.license_evidence_url,
        )
