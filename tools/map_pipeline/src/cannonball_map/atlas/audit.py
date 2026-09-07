from __future__ import annotations

import csv
import html
import io
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from shapely.geometry import shape

from cannonball_map.atlas.io import (
    IntakeError,
    Provenance,
    canonical,
    clean,
    digest,
    geometry,
    get_field,
    has_value,
    locked_path,
    records,
    source_allowed,
    validate_values,
    versioned,
)
from cannonball_map.manifest import compute_sha256

KINDS = {"exit", "service", "place", "water", "boundary", "road", "toll"}
ERRORS = (ValueError, TypeError, KeyError, OSError, OverflowError, RuntimeError)


def observation(row: dict, profile: dict, item: dict, as_of: date) -> tuple[str | None, str | None]:
    spec = profile.get("date_field", {})
    value = get_field(row, spec.get("path")) if spec else item.get("observed_on")
    if value in (None, ""):
        return None, "observation_date_unknown"
    if spec.get("format") == "unix_ms":
        observed = datetime.fromtimestamp(float(value) / 1000, UTC).date()
        label = observed.isoformat()
    elif spec.get("format") == "year":
        observed = date(int(value), 1, 1)  # Conservative age bound; retain year precision.
        label = str(int(value))
    else:
        label = str(value)
        observed = date.fromisoformat(label[:10])
    if observed > as_of:
        return label, "observation_in_future"
    if (as_of - observed).days > profile.get("max_age_days", 730):
        return label, "stale_record"
    return label, None


def _message(error: Exception) -> tuple[str, str]:
    return getattr(error, "code", "invalid_input"), str(error)


def audit(job_path: Path, output: Path) -> dict:
    job = versioned(job_path)
    as_of = date.fromisoformat(job["as_of"])
    inputs = {
        key: locked_path(job_path.parent, job[key])
        for key in ("catalog", "profiles", "route_selection", "scope")
    }
    bundles = [locked_path(job_path.parent, ref) for ref in job.get("artifact_manifests", [])]
    profiles_doc = versioned(inputs["profiles"])
    profiles = {p["id"]: p for p in profiles_doc["datasets"]}
    if len(profiles) != len(profiles_doc["datasets"]):
        raise IntakeError("duplicate_profile", "Dataset profile IDs must be unique")
    policy = versioned(inputs["route_selection"])
    policy_segments = {segment["id"]: segment for segment in policy["segments"]}
    scope_doc = versioned(inputs["scope"])
    if scope_doc["route_selection_sha256"] != job["route_selection"]["sha256"]:
        raise IntakeError("scope_policy_mismatch", "Scope is not bound to this route selection")
    scopes = {segment["id"]: segment for segment in scope_doc["segments"]}
    if len(scopes) != len(scope_doc["segments"]) or set(scopes) != set(policy_segments):
        raise IntakeError("scope_incomplete", "Scope must explicitly cover every selected segment")
    masks = {}
    for segment_id, scope in scopes.items():
        required = scope["requirements"]
        kinds = [req["kind"] for req in required]
        if not kinds or len(set(kinds)) != len(kinds) or not set(kinds) <= KINDS:
            raise IntakeError("requirements_invalid", f"{segment_id}: invalid required kinds")
        for req in required:
            if not isinstance(req["fields"], list) or not req["fields"]:
                raise IntakeError("requirements_invalid", "Required fields must be explicit")
            if any(not isinstance(field, str) or not field for field in req["fields"]) or len(
                set(req["fields"])
            ) != len(req["fields"]):
                raise IntakeError(
                    "requirements_invalid", "Required field names must be unique text"
                )
        if scope.get("geometry") is not None:
            if not scope.get("review_reference"):
                raise IntakeError("scope_unreviewed", "Corridor masks need a review reference")
            mask = geometry({}, scope["geometry"], {"format": "geojson"})
            if mask["type"] not in {"Polygon", "MultiPolygon"}:
                raise IntakeError("scope_geometry", "Corridor scopes must be polygons")
            masks[segment_id] = shape(mask)
    provenance = Provenance(bundles, inputs["catalog"], as_of)
    all_input_paths = [job_path.resolve(), *inputs.values(), *bundles, *provenance.paths.values()]
    if any(output.resolve() == p or output.resolve() in p.parents for p in all_input_paths):
        raise IntakeError("output_overlaps_input", "Output directory must not contain input files")
    bindings = {}
    for binding in job.get("bindings", []):
        key = (binding["profile_id"], str(binding["record_id"]))
        if key in bindings or not binding.get("review_reference"):
            raise IntakeError("binding_invalid", "Bindings need unique record IDs and review refs")
        if (
            binding["profile_id"] not in profiles
            or binding["segment_id"] not in scopes
            or not binding.get("entity_id")
        ):
            raise IntakeError("binding_invalid", "Binding references an unknown profile/segment")
        bindings[key] = binding
    inventory_refs = {}
    for ref in job.get("inventories", []):
        key = (ref["segment_id"], ref["kind"])
        if key in inventory_refs or key[0] not in scopes or key[1] not in KINDS:
            raise IntakeError("inventory_invalid", "Duplicate or unknown inventory scope")
        inventory_refs[key] = ref["artifact_id"]

    gaps: list[dict] = []

    def gap(code: str, message: str, **details) -> None:
        entry = {
            "code": code,
            "message": message,
            "segment_id": None,
            "kind": None,
            "entity_id": None,
            "field": None,
            "profile_id": None,
            "geometry": None,
            **details,
        }
        entry["id"] = digest(entry)[:24]
        gaps.append(entry)

    normalized = []
    sources = []
    source_roots: dict[str, set] = {}
    seen_datasets = set()
    for request in job["datasets"]:
        profile_id = request["profile_id"]
        if profile_id in seen_datasets or profile_id not in profiles:
            raise IntakeError("dataset_invalid", "Dataset requests must name unique profiles")
        seen_datasets.add(profile_id)
        profile = profiles[profile_id]
        if profile["kind"] not in KINDS:
            raise IntakeError("profile_invalid", "Unknown feature kind")
        source = {
            "profile_id": profile_id,
            "kind": profile["kind"],
            "url": profile["url"],
            "status": "ready",
            "records": 0,
            "excluded_outside_scope": 0,
            "duplicate_records": 0,
            "rejected_records": 0,
            "admission_notes": profile.get("admission_notes", ""),
        }
        sources.append(source)
        try:
            source_allowed(profile, inputs["catalog"])
            if not request.get("artifact_id"):
                raise IntakeError("not_acquired", "No locked artifact supplied")
            artifact_id = request["artifact_id"]
            item = provenance.validate(artifact_id)
            if item["source_id"] != profile["source_id"]:
                raise IntakeError("source_mismatch", "Artifact belongs to a different source")
            # Product URL identity prevents a cataloged family from impersonating another product.
            if item["source_url"].split("?")[0] != profile["url"].split("?")[0]:
                raise IntakeError(
                    "source_mismatch", "Artifact URL differs from the profile product"
                )
            source_roots[profile_id] = provenance.roots(artifact_id)
            pending = {}
            raw_records = {}
            duplicate_conflicts = set()
            for index, (row, raw_geometry) in enumerate(
                records(provenance.paths[artifact_id], profile), 1
            ):
                record_id = get_field(row, profile["id_field"])
                try:
                    if record_id in (None, "") or isinstance(record_id, (bool, list, dict)):
                        raise IntakeError("missing_record_id", f"Record {index} has no stable ID")
                    record_id = str(record_id)
                    raw_hash = digest([row, raw_geometry])
                    if record_id in raw_records:
                        if raw_hash != raw_records[record_id]:
                            duplicate_conflicts.add(record_id)
                        else:
                            source["duplicate_records"] += 1
                        continue
                    raw_records[record_id] = raw_hash
                    binding = bindings.get((profile_id, record_id))
                    geom = geometry(row, raw_geometry, profile)
                    eligible = [
                        sid
                        for sid in scopes
                        if not profile.get("jurisdictions")
                        or set(profile["jurisdictions"])
                        & set(policy_segments[sid]["jurisdictions"])
                    ]
                    segments = sorted(
                        sid
                        for sid in eligible
                        if sid in masks and geom is not None and masks[sid].intersects(shape(geom))
                    )
                    if binding:
                        sid = binding["segment_id"]
                        if sid not in eligible:
                            raise IntakeError(
                                "binding_outside_scope", "Binding jurisdiction differs"
                            )
                        if geom is not None and sid in masks and sid not in segments:
                            raise IntakeError(
                                "binding_outside_scope", "Binding is outside its mask"
                            )
                        segments = [sid]
                    elif (
                        geom is not None and not segments and all(sid in masks for sid in eligible)
                    ):
                        source["excluded_outside_scope"] += 1
                        continue
                    values = {
                        key: clean(get_field(row, field))
                        for key, field in profile["fields"].items()
                    }
                    validate_values(values)
                    observed, freshness = observation(row, profile, item, as_of)
                    issues = []
                    if freshness:
                        issues.append(freshness)
                    if geom is None:
                        issues.append("unlocated_record")
                    if not segments:
                        issues.append("unassigned_segment")
                    value_class = item.get(
                        "value_class",
                        {"acquired": "observed", "derived": "derived", "authored": "authored"}[
                            item["origin"]
                        ],
                    )
                    if value_class not in {"observed", "derived", "authored"}:
                        raise IntakeError("value_class_invalid", "Unknown semantic value class")
                    access = None
                    if binding and binding.get("access"):
                        access = binding["access"]
                        if not access.get("review_reference") or not access.get("record_reference"):
                            raise IntakeError(
                                "access_unverified", "Access evidence needs review/ref"
                            )
                        access_item = provenance.validate(access["artifact_id"])
                        _, access_freshness = observation({}, {}, access_item, as_of)
                        if access_freshness:
                            raise IntakeError(
                                "access_unverified", "Access evidence is stale or undated"
                            )
                    record = {
                        "id": digest([profile_id, record_id])[:24],
                        "profile_id": profile_id,
                        "source_record_id": record_id,
                        "artifact_id": artifact_id,
                        "artifact_sha256": item["sha256"],
                        "entity_id": binding["entity_id"]
                        if binding
                        else f"{profile_id}:{record_id}",
                        "kind": profile["kind"],
                        "segment_ids": segments,
                        "geometry": geom,
                        "values": values,
                        "value_classes": {
                            key: "unknown" if not has_value(val) else value_class
                            for key, val in values.items()
                        },
                        "observed_on": observed,
                        "quality_issues": issues,
                        "binding_review": binding["review_reference"] if binding else None,
                        "access_evidence": access,
                    }
                    if record_id in pending:
                        if canonical(pending[record_id]) != canonical(record):
                            duplicate_conflicts.add(record_id)
                        else:
                            source["duplicate_records"] += 1
                    else:
                        pending[record_id] = record
                except ERRORS as error:
                    source["rejected_records"] += 1
                    code, message = _message(error)
                    gap(
                        code,
                        message,
                        profile_id=profile_id,
                        kind=profile["kind"],
                        entity_id=str(record_id) if record_id is not None else f"row:{index}",
                    )
            for record_id in sorted(duplicate_conflicts):
                pending.pop(record_id, None)
                source["rejected_records"] += 1
                gap(
                    "duplicate_id_conflict",
                    "Same source ID has different records; both excluded",
                    profile_id=profile_id,
                    entity_id=record_id,
                    kind=profile["kind"],
                )
            for record in pending.values():
                for issue in record["quality_issues"]:
                    gap(
                        issue,
                        "Record retained for audit; cannot substantiate complete coverage",
                        profile_id=profile_id,
                        kind=record["kind"],
                        entity_id=record["entity_id"],
                        geometry=record["geometry"],
                    )
            source["records"] = len(pending)
            if source["rejected_records"] or any(r["quality_issues"] for r in pending.values()):
                source["status"] = "partial"
            normalized.extend(pending.values())
        except ERRORS as error:
            code, message = _message(error)
            source["status"] = "blocked" if code.endswith("blocked") else "invalid"
            if code == "not_acquired":
                source["status"] = "not_acquired"
            source["reason"] = code
            gap(code, message, profile_id=profile_id, kind=profile["kind"])

    groups = defaultdict(list)
    for record in normalized:
        for segment_id in record["segment_ids"]:
            groups[(segment_id, record["kind"], record["entity_id"])].append(record)
    conflicts = set()
    for key, group in groups.items():
        locations = {canonical(r["geometry"]) for r in group if r["geometry"] is not None}
        if len(locations) > 1:
            conflicts.add(key)
            gap(
                "geometry_conflict",
                "Bound sources disagree on location; review is required",
                segment_id=key[0],
                kind=key[1],
                entity_id=key[2],
                field="geometry",
                geometry=group[0]["geometry"],
            )
        fields = set().union(*(record["values"] for record in group))
        for field in sorted(fields):
            variants = {
                canonical(r["values"][field]) for r in group if has_value(r["values"].get(field))
            }
            if len(variants) > 1:
                conflicts.add(key)
                gap(
                    "value_conflict",
                    "Sources disagree; no value selected automatically",
                    segment_id=key[0],
                    kind=key[1],
                    entity_id=key[2],
                    field=field,
                    geometry=group[0]["geometry"],
                )

    coverage = []
    for segment_id, scope in sorted(scopes.items()):
        if segment_id not in masks:
            gap(
                "scope_geometry_missing",
                "Reviewed corridor mask has not been supplied",
                segment_id=segment_id,
            )
        for req in sorted(scope["requirements"], key=lambda r: r["kind"]):
            kind = req["kind"]
            cell = {
                "segment_id": segment_id,
                "kind": kind,
                "status": "unknown",
                "jurisdictions": policy_segments[segment_id]["jurisdictions"],
                "required_fields": req["fields"],
                "expected_count": None,
                "present_count": 0,
                "complete_count": 0,
                "coverage_percent": None,
                "inventory_artifact_id": inventory_refs.get((segment_id, kind)),
                "candidate_profiles": sorted(
                    p["id"]
                    for p in profiles.values()
                    if p["kind"] == kind
                    and (
                        not p.get("jurisdictions")
                        or set(p["jurisdictions"])
                        & set(policy_segments[segment_id]["jurisdictions"])
                    )
                ),
            }
            coverage.append(cell)
            inventory_id = cell["inventory_artifact_id"]
            if inventory_id is None:
                gap(
                    "inventory_unknown",
                    "No independently verified complete inventory; denominator unknown",
                    segment_id=segment_id,
                    kind=kind,
                )
                continue
            try:
                inv_item = provenance.validate(inventory_id)
                inventory = versioned(provenance.paths[inventory_id])
                if (
                    (inventory["segment_id"], inventory["kind"]) != (segment_id, kind)
                    or inventory.get("complete") is not True
                    or not inventory.get("review_reference")
                ):
                    raise IntakeError(
                        "inventory_unreviewed", "Inventory scope/completeness unverified"
                    )
                _, freshness = observation(
                    {}, {"max_age_days": req.get("max_age_days", 730)}, inv_item, as_of
                )
                if freshness:
                    raise IntakeError("inventory_stale_or_undated", freshness)
                inv_roots = provenance.roots(inventory_id)
                for profile_id, roots in source_roots.items():
                    p = profiles[profile_id]
                    if p["kind"] == kind and inv_roots & roots:
                        raise IntakeError(
                            "inventory_not_independent", "Inventory shares feature source ancestry"
                        )
                entities = inventory["entities"]
                ids = [entity["id"] for entity in entities]
                if len(set(ids)) != len(ids) or any(not isinstance(v, str) or not v for v in ids):
                    raise IntakeError(
                        "inventory_invalid", "Expected entity IDs must be unique strings"
                    )
                cell["expected_count"] = len(entities)
                for entity in sorted(entities, key=lambda e: e["id"]):
                    entity_id = entity["id"]
                    key = (segment_id, kind, entity_id)
                    group = groups.get(key, [])
                    location = entity.get("geometry") or (group[0]["geometry"] if group else None)
                    if location:
                        location = geometry({}, location, {"format": "geojson"})
                    details = {
                        "segment_id": segment_id,
                        "kind": kind,
                        "entity_id": entity_id,
                        "geometry": location,
                    }
                    if not group:
                        gap(
                            "missing_feature",
                            "Expected inventory entity has no matching record",
                            **details,
                        )
                        continue
                    cell["present_count"] += 1
                    usable = [r for r in group if not r["quality_issues"]]
                    valid = bool(usable) and key not in conflicts and segment_id in masks
                    for field in req["fields"]:
                        if field == "geometry":
                            present = any(r["geometry"] is not None for r in usable)
                        elif field == "access":
                            present = any(r["access_evidence"] is not None for r in usable)
                        else:
                            present = any(has_value(r["values"].get(field)) for r in usable)
                        if not present:
                            valid = False
                            gap(
                                "access_unverified" if field == "access" else "missing_field",
                                "Required field has no usable source value",
                                field=field,
                                **details,
                            )
                    if valid:
                        cell["complete_count"] += 1
                cell["status"] = (
                    "complete" if cell["complete_count"] == len(entities) else "incomplete"
                )
                if entities:
                    cell["coverage_percent"] = round(
                        100 * cell["complete_count"] / len(entities), 2
                    )
            except ERRORS as error:
                cell.update(
                    status="unknown",
                    expected_count=None,
                    coverage_percent=None,
                    present_count=0,
                    complete_count=0,
                )
                code, message = _message(error)
                gap(code, message, segment_id=segment_id, kind=kind)

    # Pin every checked ancestor so a downstream compiler can retain recursive provenance.
    input_hashes = {key: job[key]["sha256"] for key in inputs}
    input_hashes["job"] = compute_sha256(job_path)
    input_hashes["artifact_manifests"] = sorted(
        ref["sha256"] for ref in job.get("artifact_manifests", [])
    )
    report = {
        "schema_version": 1,
        "purpose": "offline_atlas_audit_not_runtime_content",
        "as_of": as_of.isoformat(),
        "status": "complete" if not gaps else "incomplete",
        "input_sha256": input_hashes,
        "sources": sorted(sources, key=lambda s: s["profile_id"]),
        "coverage": coverage,
        "gaps": sorted(gaps, key=lambda g: g["id"]),
        "verified_artifacts": {key: provenance.items[key] for key in sorted(provenance.checked)},
        "counts": {
            "records": len(normalized),
            "gaps": len(gaps),
            "coverage_cells": len(coverage),
            "complete_cells": sum(c["status"] == "complete" for c in coverage),
        },
    }
    write_outputs(output, report, sorted(normalized, key=lambda r: r["id"]))
    return report


def _safe_cell(value) -> str:
    return (
        html.escape(str(value if value is not None else "unknown"))
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def write_outputs(output: Path, report: dict, normalized: list[dict]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    features = [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": r["geometry"],
            "properties": {k: v for k, v in r.items() if k != "geometry"},
        }
        for r in normalized
    ]
    gap_features = [
        {
            "type": "Feature",
            "id": g["id"],
            "geometry": g["geometry"],
            "properties": {k: v for k, v in g.items() if k != "geometry"},
        }
        for g in report["gaps"]
    ]
    text = [
        "# Atlas data coverage",
        "",
        f"Status: **{report['status']}**. As of {report['as_of']}.",
        "",
        "Unknown denominators are not zero coverage. Outputs are offline audit data.",
        "",
        "| Segment | Kind | Expected | Present | Complete | Coverage | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for cell in report["coverage"]:
        text.append(
            "| "
            + " | ".join(
                _safe_cell(cell[key])
                for key in (
                    "segment_id",
                    "kind",
                    "expected_count",
                    "present_count",
                    "complete_count",
                    "coverage_percent",
                    "status",
                )
            )
            + " |"
        )
    text += [
        "",
        "## Source disposition",
        "",
        "| Dataset | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for source in report["sources"]:
        text.append(
            f"| {_safe_cell(source['profile_id'])} | {_safe_cell(source['status'])} | "
            f"{_safe_cell(source.get('reason', source.get('admission_notes', '')))} |"
        )
    text += [
        "",
        "## Gaps",
        "",
        "| Segment | Kind | Entity | Field | Code | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    csv_stream = io.StringIO(newline="")
    columns = ["id", "segment_id", "kind", "entity_id", "field", "profile_id", "code", "message"]
    writer = csv.DictWriter(csv_stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for entry in report["gaps"]:
        text.append(
            "| "
            + " | ".join(
                _safe_cell(entry[key])
                for key in ("segment_id", "kind", "entity_id", "field", "code", "message")
            )
            + " |"
        )
        row = {key: entry[key] for key in columns}
        for key, value in row.items():
            if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
                row[key] = "'" + value
        writer.writerow(row)
    outputs = {
        "coverage.json": canonical(report),
        "features.jsonl": b"".join(canonical(r) for r in normalized),
        "features.geojson": canonical({"type": "FeatureCollection", "features": features}),
        "gaps.geojson": canonical({"type": "FeatureCollection", "features": gap_features}),
        "gaps.csv": csv_stream.getvalue().encode("utf-8"),
        "report.md": ("\n".join(text) + "\n").encode("utf-8"),
    }
    manifest = {
        "schema_version": 1,
        "purpose": report["purpose"],
        "status": report["status"],
        "input_sha256": report["input_sha256"],
        "outputs": {},
    }
    for name, payload in outputs.items():
        temporary = output / (name + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(output / name)
        manifest["outputs"][name] = compute_sha256(output / name)
    temporary = output / "manifest.json.tmp"
    temporary.write_bytes(canonical(manifest))
    temporary.replace(output / "manifest.json")


def verify_outputs(output: Path) -> None:
    manifest = versioned(output / "manifest.json")
    expected_names = {
        "coverage.json",
        "features.jsonl",
        "features.geojson",
        "gaps.geojson",
        "gaps.csv",
        "report.md",
    }
    if set(manifest["outputs"]) != expected_names:
        raise IntakeError("output_manifest_invalid", "Unexpected or missing output names")
    for name, expected in manifest["outputs"].items():
        if compute_sha256(output / name) != expected:
            raise IntakeError("output_hash_mismatch", f"Output checksum differs: {name}")
