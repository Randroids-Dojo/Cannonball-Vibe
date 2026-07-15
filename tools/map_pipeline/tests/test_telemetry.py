import json
from pathlib import Path

from cannonball_map.telemetry import summarize_telemetry


def test_duckdb_summarizes_jsonl_telemetry(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.jsonl"
    events = [
        {
            "name": "pace_sample",
            "distanceMeters": 100,
            "properties": {"speedMetersPerSecond": 40},
        },
        {
            "name": "pace_sample",
            "distanceMeters": 250,
            "properties": {"speedMetersPerSecond": 60},
        },
    ]
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

    summary = summarize_telemetry(path)

    assert summary == [
        {
            "name": "pace_sample",
            "event_count": 2,
            "average_speed_mps": 50.0,
            "maximum_distance_meters": 250,
        }
    ]
