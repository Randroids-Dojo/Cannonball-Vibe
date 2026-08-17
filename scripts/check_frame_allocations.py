"""Fail the build when per-frame code allocates finalizable Godot objects.

Why this exists
---------------
On 2026-08-16 the owner reported the car stuttering roughly twice a second. It was
not the road, the suspension, the tyres or the mesh: the game allocated 11.7 KB on
every rendered frame, which filled gen0 about every two seconds, and each
collection stalled a frame for 30 to 40 ms.

The reason the pauses were long enough to see is specific and worth stating.
Godot's C# wrappers carry finalizers, so an object like the Dictionary returned by
`IntersectRay` *cannot* die in gen0 - it is queued for finalization and promoted
to gen1 by construction. Every collection in the game was therefore a gen1
collection. Tuning the nursery cannot fix that; only not allocating can.

What this checks
----------------
Calls known to allocate a finalizable Godot object, appearing inside a per-frame
method body. It is deliberately a small, literal list rather than a general
analysis: a check that produces false positives gets suppressed wholesale, and one
that needs a call graph will not survive contact with a refactor.

It does not catch allocation in a helper called from `_Process`. That is a real
gap, stated rather than hidden, and the reason the reference capture also reports
allocation per subsystem: this catches the common shape, the capture catches the
rest.

Suppressing
-----------
Append `// frame-alloc-ok: <reason>` to the line. A reason is required, because
the interesting cases are the ones somebody decided were fine.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Each entry is (pattern, what it allocates). Patterns are matched literally
# against a source line inside a per-frame method.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    (".IntersectRay(", "a Godot Dictionary per call, plus the query object"),
    (".IntersectShape(", "a Godot Array of Dictionaries per call"),
    (".GetRestInfo(", "a Godot Dictionary per call"),
    (".CastMotion(", "a Godot Array per call"),
    (".IntersectPoint(", "a Godot Array of Dictionaries per call"),
    ("PhysicsRayQueryParameters3D.Create(", "a finalizable query object per call"),
    ("new PhysicsRayQueryParameters3D", "a finalizable query object per call"),
    ("new PhysicsShapeQueryParameters3D", "a finalizable query object per call"),
    ("new Godot.Collections.Dictionary", "a finalizable Godot Dictionary"),
    ("new Godot.Collections.Array", "a finalizable Godot Array"),
    ("new SphereShape3D", "a finalizable shape resource"),
    ("new BoxShape3D", "a finalizable shape resource"),
    ("new StandardMaterial3D", "a finalizable material resource"),
    ("new ArrayMesh", "a finalizable mesh resource"),
    ("new SurfaceTool", "a finalizable SurfaceTool"),
)

PER_FRAME_METHODS = re.compile(
    r"^\s*public\s+override\s+void\s+(_Process|_PhysicsProcess)\s*\(",
)

SUPPRESSION = re.compile(r"//\s*frame-alloc-ok:\s*\S")


def per_frame_bodies(text: str) -> list[tuple[str, int, list[str]]]:
    """Return (method, first line number, body lines) for each per-frame method."""
    lines = text.split("\n")
    found: list[tuple[str, int, list[str]]] = []
    for index, line in enumerate(lines):
        match = PER_FRAME_METHODS.match(line)
        if not match:
            continue
        depth = 0
        started = False
        body: list[str] = []
        for offset in range(index, len(lines)):
            current = lines[offset]
            depth += current.count("{") - current.count("}")
            if "{" in current:
                started = True
            body.append(current)
            if started and depth <= 0:
                break
        found.append((match.group(1), index + 1, body))
    return found


def scan(root: Path) -> list[str]:
    failures: list[str] = []
    for path in sorted(root.rglob("*.cs")):
        if any(part in {"bin", "obj", ".godot"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for method, first_line, body in per_frame_bodies(text):
            for offset, line in enumerate(body):
                if SUPPRESSION.search(line):
                    continue
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                for pattern, cost in FORBIDDEN:
                    if pattern in line:
                        failures.append(
                            f"{path.as_posix()}:{first_line + offset}: "
                            f"{pattern.strip()} inside {method} allocates {cost}. "
                            "Godot wrappers have finalizers, so this cannot die in "
                            "gen0 and is promoted to gen1 every frame. Hold a "
                            "persistent node or cached instance instead, or append "
                            "'// frame-alloc-ok: <reason>'."
                        )
    return failures


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "game")
    if not root.is_dir():
        print(f"frame-allocations: nothing to scan at {root}", file=sys.stderr)
        return 1
    failures = scan(root)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(
            f"\nframe-allocations: {len(failures)} per-frame allocation(s) of "
            "finalizable Godot objects.",
            file=sys.stderr,
        )
        return 1
    print("frame-allocations: no per-frame Godot allocation found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
