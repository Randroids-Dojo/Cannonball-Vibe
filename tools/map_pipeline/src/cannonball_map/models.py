from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RouteSample:
    distance_meters: float
    lateral_meters: float
    elevation_meters: float
    curvature: float
    grade: float


@dataclass(frozen=True)
class PipelineEdge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    length_meters: float
    lane_count: int
    speed_limit_mps: float
    region_id: str
    generation_profile: str
    samples: tuple[RouteSample, ...]

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["samples"] = [asdict(sample) for sample in self.samples]
        return result


@dataclass(frozen=True)
class PipelineChunk:
    chunk_id: str
    edge_id: str
    start_meters: float
    end_meters: float
    content_hash: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
