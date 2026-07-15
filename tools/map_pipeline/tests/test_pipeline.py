import hashlib
import json
from pathlib import Path

from Cannonball.Content.RouteGraphBuffer import RouteGraphBuffer
from cannonball_map.flatbuffer_writer import write_flatbuffer
from cannonball_map.pipeline import build_route_graph


def test_pipeline_builds_deterministic_connected_chunks(tmp_path: Path) -> None:
    source = tmp_path / "route.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-100.0, 40.0], [-99.99, 40.0]],
                        },
                    },
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-99.99, 40.0], [-99.98, 40.0]],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "route.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_id": "synthetic-public-domain-fixture",
                "publisher": "Test Federal Agency",
                "source_url": "https://example.gov/route",
                "acquired_on": "2026-07-14",
                "license_status": "public_domain",
                "license_evidence_url": "https://example.gov/public-domain",
                "sha256": digest,
                "derived_from": [],
            }
        ),
        encoding="utf-8",
    )

    first = build_route_graph(source, manifest, tmp_path / "first", chunk_meters=500)
    second = build_route_graph(source, manifest, tmp_path / "second", chunk_meters=500)

    assert first["content_version"] == second["content_version"]
    assert len(first["edges"]) == 2
    assert len(first["chunks"]) >= 4
    runtime_path = tmp_path / "first" / "route_graph.cbrg"
    write_flatbuffer(first, runtime_path)
    payload = runtime_path.read_bytes()
    assert RouteGraphBuffer.RouteGraphBufferBufferHasIdentifier(payload, 0)
    root = RouteGraphBuffer.GetRootAs(payload)
    assert root.SchemaVersion() == 1
    assert root.EdgesLength() == 2
