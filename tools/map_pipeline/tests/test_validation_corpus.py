from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "data/routes/fixtures/validation/p0-012-corpus-lock.json"


def _read(path: str | Path) -> dict:
    resolved = path if isinstance(path, Path) else REPO_ROOT / path
    return json.loads(resolved.read_text(encoding="utf-8"))


def _sha256(path: str) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()


def _locked_source_artifacts(source_lock: dict) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for acquisition in source_lock["acquisitions"]:
        for artifact in acquisition["artifacts"]:
            if "path" in artifact:
                artifacts[artifact["path"]] = artifact["sha256"]
    return artifacts


def test_validation_corpus_is_checksum_locked_and_recursively_ancestral() -> None:
    corpus = _read(LOCK_PATH)
    artifacts = corpus["artifacts"]
    paths = [artifact["path"] for artifact in artifacts]

    assert len(paths) == len(set(paths))
    assert all(_sha256(artifact["path"]) == artifact["sha256"] for artifact in artifacts)
    assert set(corpus["legal_fixture_paths"]).issubset(paths)
    assert corpus["invalid_mutation_catalog"] in paths

    source_lock = _read("data/sources/representative-corridor-lock.json")
    source_artifacts = _locked_source_artifacts(source_lock)
    for artifact in artifacts:
        if artifact["provenance_kind"].startswith("approved_public_domain_source"):
            assert source_artifacts[artifact["path"]] == artifact["sha256"]

    allowed_parent_locks = {
        "data/sources/representative-corridor-lock.json",
        "data/routes/fixtures/validation/p0-012-corpus-lock.json",
    }
    for path in corpus["legal_fixture_paths"]:
        fixture = _read(path)
        provenance = fixture["semantics_provenance"]
        assert provenance["kind"] in {"authored_override", "deterministic_derivation"}
        assert provenance["parent_lock"] in allowed_parent_locks
        assert (REPO_ROOT / provenance["parent_fixture"]).is_file()
        assert "OpenStreetMap" not in json.dumps(fixture)


def test_validation_corpus_covers_every_declared_topology_contract() -> None:
    corpus = _read(LOCK_PATH)
    legal = [_read(path) for path in corpus["legal_fixture_paths"]]
    coverage = {item for fixture in legal for item in fixture["coverage"]}
    transfer_forms = {
        item
        for fixture in legal
        for item in fixture.get("highway_transfer_forms", [])
    }

    assert set(corpus["coverage_required"]).issubset(coverage)
    assert len(transfer_forms) >= corpus["minimum_highway_transfer_forms"]
    assert len({fixture["scenario"]["success_marker"] for fixture in legal}) == len(legal)
    assert all(fixture["scenario"]["fixture"] for fixture in legal)
    assert all(fixture["scenario"]["profile"] for fixture in legal)


def test_invalid_mutation_catalog_covers_the_semantic_contract() -> None:
    corpus = _read(LOCK_PATH)
    mutations = _read(corpus["invalid_mutation_catalog"])["mutations"]
    mutation_ids = {mutation["id"] for mutation in mutations}
    mutation_tests = {mutation["test"] for mutation in mutations}
    contract = _read("data/routes/fixtures/semantics/representative-contract.json")
    required_ids = {case.replace("_", "-") for case in contract["malformed_cases"]}

    assert required_ids.issubset(mutation_ids)
    assert len(mutation_tests) == len(mutations)
    assert all(mutation["expected_failure"] for mutation in mutations)
    assert "route-plan-lane-discontinuity" in mutation_ids
