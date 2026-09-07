import copy
import hashlib
import json
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from typer.testing import CliRunner

from cannonball_map.atlas.acquire import AllowedRedirects, acquire_snapshot
from cannonball_map.atlas.audit import audit, verify_outputs
from cannonball_map.atlas.cli import app
from cannonball_map.atlas.io import IntakeError, Provenance, canonical, geometry, records


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Case:
    """Independent synthetic feature/inventory sources; no real source admission implied."""

    def __init__(self, root: Path):
        self.root = root
        self.profile = {
            "id": "exits",
            "source_id": "federal-exits",
            "publisher": "Fixture Agency",
            "license_status": "public_domain",
            "license_evidence_url": "https://example.gov/rights",
            "url": "https://example.gov/exits",
            "kind": "exit",
            "format": "geojson",
            "id_field": "ID",
            "crs": "EPSG:4326",
            "jurisdictions": ["CO"],
            "fields": {"exit_number": "NUMBER", "destination": "DEST"},
        }
        self.profiles = {"schema_version": 1, "datasets": [self.profile]}
        self.catalog = {
            "sources": [
                {
                    "id": sid,
                    "publisher": "Fixture Agency",
                    "license_status": "public_domain",
                    "license_evidence_url": "https://example.gov/rights",
                    "allowed_url_prefixes": [f"https://example.gov/{path}"],
                }
                for sid, path in [("federal-exits", "exits"), ("federal-inventory", "inventory")]
            ]
        }
        self.policy = {"schema_version": 1, "segments": [{"id": "i70", "jurisdictions": ["CO"]}]}
        self.scope = {
            "schema_version": 1,
            "segments": [
                {
                    "id": "i70",
                    "review_reference": "fixture-mask",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[-107, 38], [-105, 38], [-105, 40], [-107, 40], [-107, 38]]
                        ],
                    },
                    "requirements": [
                        {"kind": "exit", "fields": ["exit_number", "destination", "geometry"]}
                    ],
                }
            ],
        }
        self.features = {"type": "FeatureCollection", "features": [self.feature()]}
        self.inventory = {
            "schema_version": 1,
            "segment_id": "i70",
            "kind": "exit",
            "complete": True,
            "review_reference": "fixture-independent-check",
            "entities": [{"id": "exits:1"}],
        }
        self.artifacts = [
            self.item("features", "features.json", "federal-exits", "exits"),
            self.item("inventory", "inventory.json", "federal-inventory", "inventory"),
        ]
        self.job = {
            "schema_version": 1,
            "as_of": "2026-09-06",
            "datasets": [{"profile_id": "exits", "artifact_id": "features"}],
            "inventories": [{"segment_id": "i70", "kind": "exit", "artifact_id": "inventory"}],
        }

    @staticmethod
    def feature(record_id=1, number="004A", dest="Fixture Town", point=(-106, 39)):
        return {
            "type": "Feature",
            "properties": {"ID": record_id, "NUMBER": number, "DEST": dest},
            "geometry": {"type": "Point", "coordinates": list(point)},
        }

    @staticmethod
    def item(key, path, source_id, product):
        url = "https://example.gov/" + product
        return {
            "id": key,
            "path": path,
            "source_id": source_id,
            "publisher": "Fixture Agency",
            "license_status": "public_domain",
            "license_evidence_url": "https://example.gov/rights",
            "source_url": url,
            "acquired_at": "2026-09-01T00:00:00Z",
            "observed_on": "2026-08-01",
            "origin": "acquired",
            "parents": [],
            "response_metadata": {
                "status": 200,
                "final_url": url,
                "content_type": "application/json",
            },
        }

    def save(self):
        for name, payload in [
            ("catalog", self.catalog),
            ("profiles", self.profiles),
            ("policy", self.policy),
            ("features", self.features),
            ("inventory", self.inventory),
        ]:
            (self.root / f"{name}.json").write_bytes(canonical(payload))
        self.scope["route_selection_sha256"] = sha(self.root / "policy.json")
        (self.root / "scope.json").write_bytes(canonical(self.scope))
        for item in self.artifacts:
            item["sha256"] = sha(self.root / item["path"])
        (self.root / "artifacts.json").write_bytes(
            canonical({"schema_version": 1, "artifacts": self.artifacts})
        )
        for field, name in [
            ("catalog", "catalog"),
            ("profiles", "profiles"),
            ("route_selection", "policy"),
            ("scope", "scope"),
        ]:
            self.job[field] = {"path": f"{name}.json", "sha256": sha(self.root / f"{name}.json")}
        self.job["artifact_manifests"] = [
            {"path": "artifacts.json", "sha256": sha(self.root / "artifacts.json")}
        ]
        (self.root / "job.json").write_bytes(canonical(self.job))
        return self.root / "job.json"

    def run(self, output="out"):
        return audit(self.save(), self.root / output)


@pytest.fixture
def case(tmp_path):
    return Case(tmp_path)


def codes(report):
    return {gap["code"] for gap in report["gaps"]}


def test_complete_independent_inventory_and_byte_identical_rebuild(case):
    first = case.run("one")
    second = audit(case.root / "job.json", case.root / "two")
    assert first["status"] == second["status"] == "complete"
    assert first["coverage"][0]["coverage_percent"] == 100
    for path in (case.root / "one").iterdir():
        assert path.read_bytes() == (case.root / "two" / path.name).read_bytes()
    record = json.loads((case.root / "one/features.jsonl").read_text())
    assert record["values"]["exit_number"] == "004A"
    assert record["value_classes"]["exit_number"] == "observed"
    verify_outputs(case.root / "one")
    (case.root / "one/gaps.csv").write_text("tampered")
    with pytest.raises(IntakeError, match="checksum"):
        verify_outputs(case.root / "one")


def test_unknown_denominator_is_not_zero_or_complete(case):
    case.job["inventories"] = []
    report = case.run()
    cell = report["coverage"][0]
    assert cell["status"] == "unknown"
    assert cell["expected_count"] is cell["coverage_percent"] is None
    assert "inventory_unknown" in codes(report)


def test_empty_reviewed_inventory_differs_from_missing_download(case):
    case.features["features"] = []
    case.inventory["entities"] = []
    assert case.run()["status"] == "complete"
    case.inventory["complete"] = False
    assert "inventory_unreviewed" in codes(case.run())


def test_gaps_have_exact_segment_entity_and_field(case):
    case.features["features"][0]["properties"]["DEST"] = None
    case.inventory["entities"].append(
        {"id": "exits:2", "geometry": {"type": "Point", "coordinates": [-106, 39.1]}}
    )
    report = case.run()
    assert report["coverage"][0]["expected_count"] == 2
    assert report["coverage"][0]["coverage_percent"] == 0
    missing = [g for g in report["gaps"] if g["code"] == "missing_field"]
    assert [(g["segment_id"], g["entity_id"], g["field"]) for g in missing] == [
        ("i70", "exits:1", "destination")
    ]
    assert any(g["entity_id"] == "exits:2" and g["geometry"] for g in report["gaps"])


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda c: c.profile.update(license_status="cc_by_4"), "license_blocked"),
        (lambda c: c.profile.update(source_id="not-cataloged"), "catalog_blocked"),
        (lambda c: c.job["datasets"][0].update(artifact_id=None), "not_acquired"),
        (lambda c: c.artifacts[0].update(derived_from=["OpenStreetMap"]), "provenance_invalid"),
        (
            lambda c: c.artifacts[0].update(
                parents=["missing"], origin="derived", process_reference="fixture"
            ),
            "missing_ancestor",
        ),
        (
            lambda c: c.artifacts[0].update(
                parents=["features"], origin="derived", process_reference="fixture"
            ),
            "ancestry_cycle",
        ),
        (lambda c: c.artifacts[0].update(acquired_at="2026-09-01T00:00:00"), "acquisition_time"),
        (lambda c: c.artifacts[0].update(acquired_at="2027-01-01T00:00:00Z"), "future_acquisition"),
        (
            lambda c: c.artifacts[0]["response_metadata"].update(
                final_url="https://evil.example/exits"
            ),
            "provenance_invalid",
        ),
        (lambda c: c.artifacts[0].update(observed_on="2010-01-01"), "stale_record"),
        (lambda c: c.artifacts[0].update(observed_on=None), "observation_date_unknown"),
        (lambda c: c.artifacts[1].update(observed_on=None), "inventory_stale_or_undated"),
        (lambda c: c.features["features"][0].update(geometry=None), "unlocated_record"),
        (lambda c: c.features["features"][0]["properties"].update(ID=None), "missing_record_id"),
    ],
)
def test_invalid_inputs_do_not_become_coverage(case, mutation, expected):
    mutation(case)
    report = case.run()
    assert report["status"] == "incomplete"
    assert expected in codes(report)
    assert report["coverage"][0]["complete_count"] == 0


def test_recursive_tampered_and_unapproved_parent_is_rejected(case):
    parent = copy.deepcopy(case.artifacts[0])
    parent.update(id="parent", path="parent.json", license_status="odbl")
    (case.root / "parent.json").write_bytes(b"{}")
    case.artifacts.append(parent)
    case.artifacts[0].update(origin="derived", parents=["parent"], process_reference="fixture")
    assert "provenance_invalid" in codes(case.run())
    parent["license_status"] = "public_domain"
    job = case.save()
    (case.root / "parent.json").write_bytes(b"changed bytes")
    assert "provenance_invalid" in codes(audit(job, case.root / "tamper"))


def test_inventory_cannot_be_derived_from_downloaded_feature_population(case):
    case.artifacts[1].update(
        origin="derived", parents=["features"], process_reference="counting features"
    )
    report = case.run()
    assert "inventory_not_independent" in codes(report)
    assert report["coverage"][0]["expected_count"] is None


def test_exact_duplicates_collapse_but_changed_duplicates_are_quarantined(case):
    case.features["features"].append(copy.deepcopy(case.features["features"][0]))
    report = case.run()
    assert report["sources"][0]["duplicate_records"] == 1
    assert report["counts"]["records"] == 1
    case.features["features"][1]["properties"]["NUMBER"] = "004B"
    report = case.run()
    assert "duplicate_id_conflict" in codes(report)
    assert report["counts"]["records"] == 0


def test_cross_source_conflict_requires_explicit_entity_binding(case):
    other = copy.deepcopy(case.profile)
    other.update(id="alternate")
    case.profiles["datasets"].append(other)
    alternate = copy.deepcopy(case.features)
    alternate["features"][0]["properties"]["NUMBER"] = "5"
    (case.root / "alternate.json").write_bytes(canonical(alternate))
    art = copy.deepcopy(case.artifacts[0])
    art.update(id="alternate", path="alternate.json")
    case.artifacts.append(art)
    case.job["datasets"].append({"profile_id": "alternate", "artifact_id": "alternate"})
    case.job["bindings"] = [
        {
            "profile_id": "alternate",
            "record_id": "1",
            "segment_id": "i70",
            "entity_id": "exits:1",
            "review_reference": "fixture crosswalk",
        }
    ]
    report = case.run()
    assert "value_conflict" in codes(report)
    assert report["coverage"][0]["complete_count"] == 0


def test_scope_does_not_include_other_parts_of_same_highway(case):
    case.features["features"][0]["geometry"]["coordinates"] = [-100, 40]
    report = case.run()
    assert report["sources"][0]["excluded_outside_scope"] == 1
    assert "missing_feature" in codes(report)


def test_missing_segment_and_missing_mask_are_explicit(case):
    case.scope["segments"][0]["geometry"] = None
    assert "scope_geometry_missing" in codes(case.run())
    case.policy["segments"].append({"id": "i40", "jurisdictions": ["AZ"]})
    with pytest.raises(IntakeError, match="every selected segment"):
        case.run()


def test_service_near_highway_does_not_prove_access(case):
    case.profile["kind"] = "service"
    case.scope["segments"][0]["requirements"] = [
        {"kind": "service", "fields": ["geometry", "access"]}
    ]
    case.inventory["kind"] = "service"
    case.job["inventories"][0]["kind"] = "service"
    assert "access_unverified" in codes(case.run())


def test_acquisition_date_never_overrides_old_record_observation(case):
    case.profile["date_field"] = {"path": "UPDATEYR", "format": "year"}
    case.features["features"][0]["properties"]["UPDATEYR"] = 2010
    assert "stale_record" in codes(case.run())
    record = json.loads((case.root / "out/features.jsonl").read_text())
    assert record["observed_on"] == "2010"


@pytest.mark.parametrize("fmt", ["geojson", "arcgis", "csv", "ndjson", "geopackage", "geoparquet"])
def test_adapters_preserve_source_ids_and_normalize_coordinates(tmp_path, fmt):
    point = {"type": "Point", "coordinates": [-106, 39]}
    profile = {
        "format": fmt,
        "id_field": "ID",
        "crs": "EPSG:4326",
        "layer": "places",
        "longitude_field": "lon",
        "latitude_field": "lat",
    }
    path = tmp_path / "data.json"
    if fmt == "geojson":
        path.write_bytes(canonical({"type": "FeatureCollection", "features": [Case.feature()]}))
    elif fmt == "ndjson":
        path.write_bytes(canonical(Case.feature()))
    elif fmt == "arcgis":
        path.write_bytes(
            canonical(
                {
                    "spatialReference": {"wkid": 4326},
                    "features": [{"attributes": {"ID": 1}, "geometry": {"x": -106, "y": 39}}],
                }
            )
        )
    elif fmt == "csv":
        path.write_text("ID|lon|lat\n001|-106|39\n", encoding="utf-8")
        profile["delimiter"] = "|"
    elif fmt == "geopackage":
        import geopandas as gpd
        from shapely.geometry import Point

        path = tmp_path / "data.gpkg"
        gpd.GeoDataFrame({"ID": [1]}, geometry=[Point(-106, 39)], crs="EPSG:4326").to_file(
            path, layer="places"
        )
    else:
        import duckdb
        from shapely.geometry import Point

        path = tmp_path / "data.parquet"
        with duckdb.connect() as conn:
            conn.execute("CREATE TABLE places (ID INTEGER, geometry BLOB)")
            conn.execute("INSERT INTO places VALUES (1, ?)", [Point(-106, 39).wkb])
            conn.execute("COPY places TO ? (FORMAT PARQUET)", [str(path)])
    raw = list(records(path, profile))
    assert len(raw) == 1
    assert str(raw[0][0]["ID"]) == ("001" if fmt == "csv" else "1")
    assert geometry(*raw[0], profile) == point


def test_crs_transform_and_invalid_geometry():
    from pyproj import Transformer

    x, y = Transformer.from_crs(4326, 3857, always_xy=True).transform(-106, 39)
    result = geometry({}, {"x": x, "y": y}, {"format": "arcgis", "crs": "EPSG:3857"})
    assert result["coordinates"] == pytest.approx([-106, 39])
    with pytest.raises(IntakeError):
        geometry({}, {"type": "Point", "coordinates": [400, 90]}, {"format": "geojson"})


def test_truncated_response_is_not_a_valid_empty_dataset(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"features":[],"exceededTransferLimit":true}')
    with pytest.raises(IntakeError, match="truncated"):
        list(records(path, {"format": "arcgis"}))


def test_job_hashes_and_cli_exit_codes(case):
    job = case.save()
    runner = CliRunner()
    result = runner.invoke(app, ["audit", str(job), "--output", str(case.root / "cli")])
    assert result.exit_code == 0, result.output
    case.job["inventories"] = []
    job = case.save()
    result = runner.invoke(app, ["audit", str(job), "--output", str(case.root / "cli")])
    assert result.exit_code == 2
    (case.root / "profiles.json").write_bytes(b"{}")
    result = runner.invoke(app, ["audit", str(job), "--output", str(case.root / "cli")])
    assert result.exit_code == 1 and '"code":"hash_mismatch"' in result.output


class FakeArcGIS:
    def __init__(self, *, omit=False, drift=False):
        self.urls = []
        self.omit = omit
        self.drift = drift
        self.id_calls = 0

    def get(self, url):
        self.urls.append(url)
        query = parse_qs(urlsplit(url).query)
        if "/query?" not in url:
            payload = {
                "objectIdField": "ID",
                "fields": [{"name": n} for n in ["ID", "NUMBER", "DEST"]],
                "maxRecordCount": 1,
                "editingInfo": {"lastEditDate": 1},
            }
        elif "returnCountOnly" in query:
            payload = {"count": 2}
        elif "returnIdsOnly" in query:
            self.id_calls += 1
            payload = {
                "objectIdFieldName": "ID",
                "objectIds": [1, 2, 3] if self.drift and self.id_calls > 1 else [1, 2],
            }
        else:
            ids = [int(v) for v in query["objectIds"][0].split(",")]
            payload = {
                "features": [
                    {
                        "attributes": {"ID": n, "NUMBER": str(n), "DEST": "Town"},
                        "geometry": {"x": -106, "y": 39},
                    }
                    for n in ids
                    if not self.omit
                ]
            }
        return canonical(payload), {
            "status": 200,
            "content_type": "application/json",
            "final_url": url,
        }


def test_paged_acquisition_reconciles_ids_and_resumes_checked_pages(case):
    case.profile["format"] = "arcgis"
    case.save()
    source = FakeArcGIS()
    first = acquire_snapshot(
        case.profile,
        case.root / "catalog.json",
        case.root / "acquire",
        where="STATE='CO'",
        observed_on="2026-08-01",
        transport=source,
    )
    assert first["resumed_responses"] == 0
    second = acquire_snapshot(
        case.profile,
        case.root / "catalog.json",
        case.root / "acquire",
        where="STATE='CO'",
        observed_on="2026-08-01",
        transport=FakeArcGIS(),
    )
    assert second["resumed_responses"] == 2
    bundle = case.root / "acquire/artifacts.json"
    graph = Provenance([bundle], case.root / "catalog.json", date(2099, 1, 1))
    item = graph.validate(second["artifact_id"])
    assert len(item["parents"]) == 7
    assert len(json.loads((case.root / "acquire/dataset.json").read_text())["features"]) == 2
    # A corrupt cached page is downloaded again, not silently reused.
    cached = next(
        p
        for p in (case.root / "acquire/responses").glob("*.json")
        if "objectIds=" in json.loads(p.read_text())["source_url"]
    )
    cached.with_suffix(".bin").write_bytes(b"corrupt")
    third = acquire_snapshot(
        case.profile,
        case.root / "catalog.json",
        case.root / "acquire",
        where="STATE='CO'",
        observed_on="2026-08-01",
        transport=FakeArcGIS(),
    )
    assert third["resumed_responses"] == 1


@pytest.mark.parametrize("option,code", [("omit", "incomplete_page"), ("drift", "service_drift")])
def test_incomplete_acquisition_never_emits_a_manifest(case, option, code):
    case.profile["format"] = "arcgis"
    case.save()
    with pytest.raises(IntakeError) as caught:
        acquire_snapshot(
            case.profile,
            case.root / "catalog.json",
            case.root / "acquire",
            where="STATE='CO'",
            transport=FakeArcGIS(**{option: True}),
        )
    assert caught.value.code == code
    assert not (case.root / "acquire/artifacts.json").exists()


def test_blocked_acquisition_never_contacts_provider(case):
    case.profile["license_status"] = "cc0_unreviewed"
    case.save()
    source = FakeArcGIS()
    with pytest.raises(IntakeError):
        acquire_snapshot(
            case.profile, case.root / "catalog.json", case.root / "blocked", transport=source
        )
    assert source.urls == []
    assert not (case.root / "blocked").exists()


def test_redirect_cannot_leave_catalog_allowlist():
    handler = AllowedRedirects(("https://example.gov/data/",))
    request = urllib.request.Request("https://example.gov/data/source")
    with pytest.raises(IntakeError, match="outside"):
        handler.redirect_request(
            request, None, 302, "redirect", {}, "https://example.gov.evil/data/"
        )


def test_continental_starter_reports_every_policy_segment(tmp_path):
    root = Path(__file__).resolve().parents[3]
    report = audit(root / "data/atlas/continental-job.v1.json", tmp_path / "continental")
    selection = json.loads((root / "data/routes/continental/route-selection.v1.json").read_text())
    assert {c["segment_id"] for c in report["coverage"]} == {s["id"] for s in selection["segments"]}
    assert report["status"] == "incomplete"
    assert all(c["expected_count"] is None for c in report["coverage"])
    assert report["counts"]["records"] == 0


@pytest.mark.parametrize("empty", ["  ", [], {}, [None], {"primary": ""}])
def test_empty_source_values_remain_unknown(case, empty):
    case.features["features"][0]["properties"]["DEST"] = empty
    report = case.run()
    assert "missing_field" in codes(report)
    assert report["coverage"][0]["complete_count"] == 0


def test_duplicate_conflict_outside_mask_does_not_hide_disagreement(case):
    case.features["features"].append(Case.feature(point=(-100, 40)))
    report = case.run()
    assert "duplicate_id_conflict" in codes(report)
    assert report["counts"]["records"] == 0


def test_geojson_declared_crs_mismatch_is_rejected(case):
    case.features["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    assert "crs_mismatch" in codes(case.run())


def test_failed_page_can_be_reacquired_after_service_recovers(case):
    case.profile["format"] = "arcgis"
    case.save()
    with pytest.raises(IntakeError):
        acquire_snapshot(
            case.profile,
            case.root / "catalog.json",
            case.root / "acquire",
            where="STATE='CO'",
            transport=FakeArcGIS(omit=True),
        )
    result = acquire_snapshot(
        case.profile,
        case.root / "catalog.json",
        case.root / "acquire",
        where="STATE='CO'",
        transport=FakeArcGIS(),
    )
    assert Path(result["manifest"]).is_file()


def test_changed_service_edition_does_not_reuse_old_pages(case):
    case.profile["format"] = "arcgis"
    case.save()
    acquire_snapshot(
        case.profile,
        case.root / "catalog.json",
        case.root / "acquire",
        where="STATE='CO'",
        transport=FakeArcGIS(),
    )

    class Updated(FakeArcGIS):
        def get(self, url):
            raw, meta = super().get(url)
            body = json.loads(raw)
            if "editingInfo" in body:
                body["editingInfo"]["lastEditDate"] = 2
            return canonical(body), meta

    result = acquire_snapshot(
        case.profile,
        case.root / "catalog.json",
        case.root / "acquire",
        where="STATE='CO'",
        transport=Updated(),
    )
    assert result["resumed_responses"] == 0


def test_explicit_job_lock_does_not_reapprove_sources(case):
    job = case.save()
    case.profile["license_status"] = "not_allowed"
    (case.root / "profiles.json").write_bytes(canonical(case.profiles))
    result = CliRunner().invoke(app, ["lock", str(job)])
    assert result.exit_code == 0, result.output
    report = audit(job, case.root / "locked")
    assert "license_blocked" in codes(report)


@pytest.mark.parametrize(
    "field,value",
    [("DEST", {"bad": "mapping"}), ("NUMBER", ["4", "5"]), ("NUMBER", 4.5), ("NUMBER", True)],
)
def test_wrong_semantic_types_are_rejected(case, field, value):
    case.features["features"][0]["properties"][field] = value
    assert "field_type_invalid" in codes(case.run())


def test_whole_number_exit_normalization_preserves_its_value(case):
    case.features["features"][0]["properties"]["NUMBER"] = 157.0
    assert case.run()["status"] == "complete"
    record = json.loads((case.root / "out/features.jsonl").read_text())
    assert record["values"]["exit_number"] == "157"


def test_cited_access_record_can_close_documentary_access_gap(case):
    case.profile["kind"] = "service"
    case.scope["segments"][0]["requirements"] = [
        {"kind": "service", "fields": ["geometry", "access"]}
    ]
    case.inventory["kind"] = "service"
    case.job["inventories"][0]["kind"] = "service"
    case.job["bindings"] = [
        {
            "profile_id": "exits",
            "record_id": "1",
            "segment_id": "i70",
            "entity_id": "exits:1",
            "review_reference": "synthetic fixture review",
            "access": {
                "artifact_id": "inventory",
                "record_reference": "fixture row 1",
                "review_reference": "synthetic documentary access review",
            },
        }
    ]
    assert case.run()["status"] == "complete"
    case.job["bindings"][0]["access"]["artifact_id"] = "missing-evidence"
    assert "missing_ancestor" in codes(case.run())


def test_malformed_feature_is_reported_without_a_traceback(case):
    case.features["features"].append(None)
    report = case.run()
    assert "invalid_record" in codes(report)
    assert report["counts"]["records"] == 0


def test_ambiguous_csv_headers_are_rejected(tmp_path):
    path = tmp_path / "ambiguous.csv"
    path.write_text("ID,ID\n1,2\n")
    with pytest.raises(IntakeError, match="duplicated"):
        list(records(path, {"format": "csv"}))


def test_committed_atlas_inputs_use_git_line_endings():
    root = Path(__file__).resolve().parents[3]
    for name in ("datasets.v1.json", "continental-scope.v1.json", "continental-job.v1.json"):
        # A Windows generator must not hash CRLF bytes which Git normalizes on commit.
        assert b"\r\n" not in (root / "data/atlas" / name).read_bytes()
