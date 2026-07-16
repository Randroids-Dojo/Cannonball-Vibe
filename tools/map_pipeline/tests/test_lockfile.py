from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cannonball_map.lockfile import (
    LockedArtifact,
    materialize_locked_artifact,
    materialize_locked_role,
    validate_lock,
)


def test_repository_source_lock_and_checked_in_artifacts_validate() -> None:
    payload = validate_lock(
        Path("data/sources/source-lock.json"),
        Path("data/sources/catalog.json"),
    )
    assert len(payload["acquisitions"]) == 2


def test_locked_replay_uses_exact_url_without_discovery_and_rejects_drift(
    tmp_path: Path,
) -> None:
    payload = b"exact artifact"
    artifact = LockedArtifact(
        "fixture",
        "https://artifacts.example.gov/exact.bin",
        hashlib.sha256(payload).hexdigest(),
        None,
    )
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        assert "discover" not in url
        return payload

    materialize_locked_artifact(artifact, tmp_path / "artifact.bin", fetch)
    assert calls == [artifact.url]

    drifted = LockedArtifact(artifact.role, artifact.url, "0" * 64, None)
    with pytest.raises(ValueError, match="Downloaded hash drift"):
        materialize_locked_artifact(drifted, tmp_path / "bad.bin", fetch)


def test_locked_derived_replay_uses_ancestor_url_and_no_discovery(tmp_path: Path) -> None:
    raw = b'{"z":1,"a":2}'
    canonical = b'{\n  "a": 2,\n  "z": 1\n}\n'
    raw_hash = hashlib.sha256(raw).hexdigest()
    canonical_hash = hashlib.sha256(canonical).hexdigest()
    payload = {
        "acquisitions": [
            {
                "artifacts": [
                    {
                        "role": "raw",
                        "url": "https://artifacts.example.gov/exact.json",
                        "sha256": raw_hash,
                    },
                    {
                        "role": "canonical",
                        "sha256": canonical_hash,
                        "derived_from_sha256": [raw_hash],
                        "derivation": {"kind": "canonical-json-v1"},
                    },
                ]
            }
        ]
    }
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        assert "discover" not in url
        return raw

    output = materialize_locked_role(payload, "canonical", tmp_path / "canonical.json", fetch)
    assert output.read_bytes() == canonical
    assert calls == ["https://artifacts.example.gov/exact.json"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("url", "https://unapproved.example/artifact", "outside the catalog allowlist"),
        ("path", "../../escape.bin", "path is unsafe"),
    ],
)
def test_lock_rejects_unapproved_urls_and_unsafe_paths(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    payload = json.loads(Path("data/sources/source-lock.json").read_text(encoding="utf-8"))
    payload["acquisitions"][0]["artifacts"][0][field] = value
    lock = tmp_path / "a" / "b" / "source-lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        validate_lock(lock, Path("data/sources/catalog.json"))
