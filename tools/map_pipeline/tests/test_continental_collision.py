from __future__ import annotations

from copy import deepcopy

import pytest
from shapely.geometry import LineString

from cannonball_map.continental_collision import (
    COLLISION_STATUS,
    _chunks,
    _ribbon_samples,
    _sha,
    validate_continental_collision_payload,
)


def test_collision_ribbon_chunks_share_exact_boundaries() -> None:
    samples = _ribbon_samples(
        LineString([(0.0, 0.0), (4_050.0, 0.0)]),
        [
            {
                "start_m": 0.0,
                "end_m": 4_050.0,
                "lanes": [{"width_m": 3.6}, {"width_m": 3.6}],
                "left_shoulder_m": 1.2,
                "right_shoulder_m": 3.0,
            }
        ],
        [100.0, 110.0],
        4_050.0,
        [],
    )
    chunks = _chunks("fixture", "segment", samples)

    assert len(chunks) == 3
    assert chunks[0]["exit_boundary"] == chunks[1]["entry_boundary"]
    assert chunks[1]["exit_boundary"] == chunks[2]["entry_boundary"]
    assert sum(chunk["triangle_count"] for chunk in chunks) == 324


def test_collision_clearance_ramp_reaches_declared_height() -> None:
    samples = _ribbon_samples(
        LineString([(0.0, 0.0), (200.0, 0.0)]),
        [{"start_m": 0.0, "end_m": 200.0, "lanes": [{"width_m": 4.0}]}],
        [10.0],
        200.0,
        [100.0],
    )

    crossing = next(sample for sample in samples if sample["station_m"] == 100.0)
    assert crossing["left"][2] == pytest.approx(15.03)
    assert samples[0]["left"][2] == pytest.approx(10.0)
    assert samples[-1]["left"][2] == pytest.approx(10.0)


def test_collision_validator_rejects_open_chunk_seam() -> None:
    chunks = [
        {
            "chunk_id": "fixture--collision-0000",
            "host_id": "fixture",
            "host_kind": "segment",
            "start_m": 0.0,
            "end_m": 25.0,
            "sample_count": 2,
            "triangle_count": 2,
            "geometry_sha256": "a" * 64,
            "entry_boundary": {"left": [0, 1, 0], "right": [0, -1, 0]},
            "exit_boundary": {"left": [25, 1, 0], "right": [25, -1, 0]},
        },
        {
            "chunk_id": "fixture--collision-0001",
            "host_id": "fixture",
            "host_kind": "segment",
            "start_m": 25.0,
            "end_m": 50.0,
            "sample_count": 2,
            "triangle_count": 2,
            "geometry_sha256": "b" * 64,
            "entry_boundary": {"left": [25, 1, 0], "right": [25, -1, 0]},
            "exit_boundary": {"left": [50, 1, 0], "right": [50, -1, 0]},
        },
    ]
    hosts = [{"host_id": "fixture", "host_kind": "segment"}]
    payload = {
        "schema_version": 1,
        "status": COLLISION_STATUS,
        "hosts": hosts,
        "hosts_sha256": _sha(hosts),
        "chunks": chunks,
        "chunks_sha256": _sha(chunks),
        "grade_separations": [],
        "summary": {
            "host_count": 1,
            "chunk_count": 2,
            "open_chunk_seams": 0,
            "grade_separation_count": 0,
        },
    }
    validate_continental_collision_payload(payload)

    tampered = deepcopy(payload)
    tampered["chunks"][1]["entry_boundary"]["left"][1] = 2
    tampered["chunks_sha256"] = _sha(tampered["chunks"])
    with pytest.raises(ValueError, match="seam is open"):
        validate_continental_collision_payload(tampered)
