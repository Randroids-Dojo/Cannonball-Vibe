import hashlib
import json
from pathlib import Path

import pytest

from cannonball_map.manifest import SourceManifest, validate_source


def write_manifest(path: Path, digest: str, **overrides: object) -> SourceManifest:
    values = {
        "source_id": "public-fixture",
        "publisher": "Test Federal Agency",
        "source_url": "https://example.gov/source",
        "acquired_on": "2026-07-14",
        "license_status": "public_domain",
        "license_evidence_url": "https://example.gov/public-domain",
        "sha256": digest,
        "derived_from": [],
    }
    values.update(overrides)
    path.write_text(json.dumps(values), encoding="utf-8")
    return SourceManifest.load(path)


def test_valid_public_domain_source_passes(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"federal route fixture")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = write_manifest(tmp_path / "source.manifest.json", digest)

    validate_source(manifest, source)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"license_status": "odbl"}, "not public_domain"),
        ({"derived_from": ["OpenStreetMap"]}, "OpenStreetMap-derived"),
        ({"sha256": "0" * 64}, "SHA-256 mismatch"),
    ],
)
def test_disallowed_or_tampered_sources_fail(
    tmp_path: Path,
    override: dict[str, object],
    message: str,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = write_manifest(tmp_path / "source.manifest.json", digest, **override)

    with pytest.raises(ValueError, match=message):
        validate_source(manifest, source)


def test_manifest_identity_is_enforced_against_catalog(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = write_manifest(tmp_path / "source.manifest.json", digest)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "public-fixture",
                        "publisher": "Test Federal Agency",
                        "license_status": "public_domain",
                        "license_evidence_url": "https://example.gov/public-domain",
                        "allowed_url_prefixes": ["https://example.gov/source"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    validate_source(manifest, source, catalog)
    for override, message in [
        ({"source_id": "unknown"}, "not in the approved catalog"),
        ({"publisher": "Someone Else"}, "Publisher"),
        ({"source_url": "https://unapproved.gov/source"}, "allowlist"),
        ({"source_url": "https://example.gov/source.evil"}, "allowlist"),
        ({"license_status": "odbl"}, "not public_domain"),
    ]:
        changed = write_manifest(tmp_path / "changed.json", digest, **override)
        with pytest.raises(ValueError, match=message):
            validate_source(changed, source, catalog)
