from __future__ import annotations

from pathlib import Path

import duckdb


def summarize_telemetry(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = duckdb.connect()
    try:
        rows = connection.execute(
            """
            select
                name,
                count(*) as event_count,
                avg(try_cast(properties.speedMetersPerSecond as double)) as average_speed_mps,
                max(distanceMeters) as maximum_distance_meters
            from read_json_auto(?)
            group by name
            order by name
            """,
            [str(path)],
        ).fetchall()
        return [
            {
                "name": row[0],
                "event_count": row[1],
                "average_speed_mps": row[2],
                "maximum_distance_meters": row[3],
            }
            for row in rows
        ]
    finally:
        connection.close()
