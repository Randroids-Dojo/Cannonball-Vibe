from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "data/routes/fixtures/validation/p0-012-corpus-lock.json"
PROHIBITED_ANCESTRY = {"openstreetmap", "osm"}


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


def _structured_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _structured_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _structured_strings(child)]
    return [value] if isinstance(value, str) else []


def _contains_prohibited_ancestry(value: object) -> bool:
    for candidate in _structured_strings(value):
        words = re.findall(r"[a-z0-9]+", candidate.casefold())
        compact = "".join(words)
        if "openstreetmap" in compact or PROHIBITED_ANCESTRY.intersection(words):
            return True
    return False


def _provenance_documents(corpus: dict) -> dict[Path, dict]:
    pending = {
        REPO_ROOT / artifact["path"]
        for artifact in corpus["artifacts"]
        if Path(artifact["path"]).suffix.casefold() in {".json", ".geojson"}
    }
    pending.update(REPO_ROOT / path for path in corpus["legal_fixture_paths"])
    documents: dict[Path, dict] = {}
    while pending:
        resolved = pending.pop().resolve()
        assert resolved.is_relative_to(REPO_ROOT)
        if resolved in documents:
            continue
        document = _read(resolved)
        documents[resolved] = document
        for candidate in _structured_strings(document):
            if len(candidate) > 512 or not candidate.casefold().endswith((".json", ".geojson")):
                continue
            referenced = (REPO_ROOT / candidate).resolve()
            if referenced.is_relative_to(REPO_ROOT) and referenced.is_file():
                pending.add(referenced)
    return documents


def _python_selectors(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selectors: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        selectors.add(node.name)
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or len(decorator.args) < 2:
                continue
            try:
                names = ast.literal_eval(decorator.args[0])
                values = ast.literal_eval(decorator.args[1])
            except (ValueError, TypeError):
                continue
            if tuple(names) != ("mutation", "message"):
                continue
            selectors.update(f"{node.name}[{mutation}-{message}]" for mutation, message in values)
    return selectors


def _catalogued_test_selectors() -> set[str]:
    python = _python_selectors(REPO_ROOT / "tools/map_pipeline/tests/test_semantics.py")
    csharp = set()
    for path in (REPO_ROOT / "tests/Cannonball.Core.Tests").glob("*.cs"):
        csharp.update(
            re.findall(
                r"\b(?:public\s+)?void\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                path.read_text(encoding="utf-8"),
            )
        )
    return python | csharp


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

    documents = _provenance_documents(corpus)
    assert REPO_ROOT / "data/sources/representative-corridor-lock.json" in documents
    assert not any(_contains_prohibited_ancestry(document) for document in documents.values())


def test_validation_corpus_covers_every_declared_topology_contract() -> None:
    corpus = _read(LOCK_PATH)
    legal = [_read(path) for path in corpus["legal_fixture_paths"]]
    coverage = {item for fixture in legal for item in fixture["coverage"]}
    transfer_forms = {
        item for fixture in legal for item in fixture.get("highway_transfer_forms", [])
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
    assert mutation_tests.issubset(_catalogued_test_selectors())
    assert all(mutation["expected_failure"] for mutation in mutations)
    assert "route-plan-lane-discontinuity" in mutation_ids
