"""Pure-Python curve utilities for the Hero GT generator.

Everything here runs without Blender so it can be unit-tested with plain
Python: Catmull-Rom interpolation of scalar and vector keys along the car's
length, smooth-step blends, and the profile evaluator that turns a set of
named section parameters into an ordered half-loop of (x, z) points.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Sequence


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 1.0 if value >= edge1 else 0.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


@dataclass(frozen=True)
class Key:
    """A scalar key at longitudinal position ``y``."""

    y: float
    value: float


class Spline:
    """Centripetal Catmull-Rom through scalar keys, clamped outside the range.

    Keys must be sorted by ``y``. Between keys the curve is C1 and passes
    through every key, which is what a designer expects from "the beltline is
    0.86 m at the A-pillar and 0.92 m at the B-pillar". A ``tension`` of 0
    gives the classic Catmull-Rom; 1 gives straight segments.
    """

    def __init__(self, keys: Sequence[tuple[float, float]], tension: float = 0.0) -> None:
        if len(keys) < 2:
            raise ValueError("a spline needs at least two keys")
        ys = [float(y) for y, _ in keys]
        if any(b <= a for a, b in zip(ys, ys[1:])):
            raise ValueError("spline keys must be strictly increasing in y")
        self._ys = ys
        self._vs = [float(v) for _, v in keys]
        self._tension = clamp(tension, 0.0, 1.0)

    @property
    def start(self) -> float:
        return self._ys[0]

    @property
    def end(self) -> float:
        return self._ys[-1]

    def __call__(self, y: float) -> float:
        ys, vs = self._ys, self._vs
        if y <= ys[0]:
            return vs[0]
        if y >= ys[-1]:
            return vs[-1]
        i = bisect.bisect_right(ys, y) - 1
        i = min(i, len(ys) - 2)
        y0, y1 = ys[i], ys[i + 1]
        t = (y - y0) / (y1 - y0)
        p1, p2 = vs[i], vs[i + 1]
        p0 = vs[i - 1] if i > 0 else p1 - (p2 - p1)
        p3 = vs[i + 2] if i + 2 < len(vs) else p2 + (p2 - p1)
        # Tangents scaled by the local spacing so uneven keys stay smooth.
        h = y1 - y0
        h0 = y0 - (ys[i - 1] if i > 0 else y0 - h)
        h1 = (ys[i + 2] if i + 2 < len(ys) else y1 + h) - y1
        m1 = (1.0 - self._tension) * ((p2 - p0) / (h0 + h)) * h
        m2 = (1.0 - self._tension) * ((p3 - p1) / (h + h1)) * h
        t2, t3 = t * t, t * t * t
        return (
            (2 * t3 - 3 * t2 + 1) * p1
            + (t3 - 2 * t2 + t) * m1
            + (-2 * t3 + 3 * t2) * p2
            + (t3 - t2) * m2
        )


def bump(y: float, centre: float, half_width: float, power: float = 2.0) -> float:
    """A smooth 0..1 bump centred on ``centre`` that reaches 0 at ``half_width``.

    Used for wheel-arch blisters and the power bulge: cosine-shaped, with
    ``power`` sharpening the peak.
    """
    distance = abs(y - centre)
    if distance >= half_width:
        return 0.0
    return (0.5 + 0.5 * math.cos(math.pi * distance / half_width)) ** power


def catmull_rom_points(points: Sequence[tuple[float, float]], samples_per_segment: int, closed: bool = False) -> list[tuple[float, float]]:
    """Resample a 2D polyline through its points with a Catmull-Rom curve."""
    if len(points) < 2:
        return list(points)
    pts = list(points)
    count = len(pts)
    result: list[tuple[float, float]] = []
    segments = count if closed else count - 1
    for i in range(segments):
        p1 = pts[i]
        p2 = pts[(i + 1) % count]
        if closed:
            p0 = pts[(i - 1) % count]
            p3 = pts[(i + 2) % count]
        else:
            p0 = pts[i - 1] if i > 0 else (2 * p1[0] - p2[0], 2 * p1[1] - p2[1])
            p3 = pts[i + 2] if i + 2 < count else (2 * p2[0] - p1[0], 2 * p2[1] - p1[1])
        for s in range(samples_per_segment):
            t = s / samples_per_segment
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            z = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            result.append((x, z))
    if not closed:
        result.append(pts[-1])
    return result


def resample_by_arc_length(points: Sequence[tuple[float, float]], count: int) -> list[tuple[float, float]]:
    """Return ``count`` points evenly spaced along the polyline's arc length."""
    if count < 2:
        raise ValueError("count must be at least 2")
    lengths = [0.0]
    for (x0, z0), (x1, z1) in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.hypot(x1 - x0, z1 - z0))
    total = lengths[-1]
    if total == 0.0:
        return [tuple(points[0])] * count
    result: list[tuple[float, float]] = []
    for i in range(count):
        target = total * i / (count - 1)
        j = bisect.bisect_right(lengths, target) - 1
        j = min(max(j, 0), len(points) - 2)
        span = lengths[j + 1] - lengths[j]
        t = 0.0 if span == 0.0 else (target - lengths[j]) / span
        x = lerp(points[j][0], points[j + 1][0], t)
        z = lerp(points[j][1], points[j + 1][1], t)
        result.append((x, z))
    return result
