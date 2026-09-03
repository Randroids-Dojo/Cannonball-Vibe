# P0-021 continental collision chunking

- Date: 2026-09-01
- Status: collision locked; ADR-0019 package build remains open
- Platform: Windows 11, x86-64
- Decisions: ADR-0011, ADR-0018, ADR-0019, ADR-0020

## Scope

This slice converts the locked lane topology into deterministic 3D collision
ribbons. It covers all 12 westbound carriageway hosts, all 12 junction
movements, and both authored endpoint connectors. It does not claim runtime
streaming, bot traversal, sightline approval, geographic plausibility, or the
final FlatBuffer/GeoPackage package.

The derivation uses the lane-and-shoulder envelope for width, the locked
conditioned and boundary-pinned vertical profile for elevation, and the locked
speed-designed corner refinements for plan geometry. It samples every 25 m and
partitions each host into independently recoverable chunks no longer than
2,000 m. Adjacent chunks duplicate one exact boundary pair, making an open seam
a cache-independent validation failure.

The two West LA plan-view crossings use the lane lock's authored
grade-separation records. The transfer is raised by 5.03 m at each crossing
with a deterministic 100 m cosine ramp, preserving zero lift at the ramp ends.

## Results

- Hosts: 26 (12 segments, 12 junction movements, 2 endpoint connectors)
- Collision chunks: 5,109
- Triangle count: 815,044
- Open chunk seams: 0
- Grade separations applied: 2
- Collision lock size: 4,193,718 bytes
- Host digest: `254be4f9cbe9cdfc3564b9a4340c04ff0b2e36a5ce957ff2154483ed28b0062d`
- Chunk digest: `a109d6afba515b67b6192946412740f9e795aed702aef6550cc8a7ccad3c255a`
- Consecutive full derivations: semantically identical after removing only
  `derived_at`

## Rebuilt geometry cache finding

The ignored carriageway cache was absent. The NHPN supplementary and NHS fill
caches were re-acquired only after their live service metadata reproduced the
committed snapshot hashes. Rebuilding the carriageway with the current pinned
pipeline preserved every length, vertex count, route fact, and gate, but five
millimetre-quantized carriageway geometry digests differed from the older
committed lock. The dependent carriageway, junction, and lane locks were
therefore regenerated as one chain before collision derivation; no mismatching
cache was accepted and no geometry gate was weakened.

## Verification

The following commands passed:

```text
uv run --project tools/map_pipeline --frozen ruff check tools/map_pipeline
uv run --project tools/map_pipeline --frozen pytest tools/map_pipeline/tests/test_continental_collision.py -q
uv run --project tools/map_pipeline --frozen cannonball-map validate-continental-collision
uv run --project tools/map_pipeline --frozen pytest tools/map_pipeline/tests -q
dotnet build Cannonball.sln
dotnet test Cannonball.sln --no-build
```

The focused suite covers exact chunk-boundary sharing, the 5.03 m clearance
ramp, and tamper rejection for an opened seam. The cache-independent validator
also checks every upstream lock digest, chunk topology, length budget, summary,
and aggregate host/chunk digest.

The complete map suite passed and the C# suite passed 145 tests.
`scripts/validate-continental-route.sh` was also attempted, but this shell's
WSL bridge cannot resolve the Windows `uvx.exe` used by `.tools/uv-pinned/uv`;
it stopped before running a validator. The exact new cache-independent command
above passed directly. The full Godot gate was not run because the pinned Godot
4.7.1 .NET editor is not installed in this checkout or discoverable on the
host.

## Defect found at merge (2026-09-02)

The first CI run of this slice failed four map-pipeline lock tests on every
platform with "Junction geometry lock input hash drifted". The carriageway,
junction and lane locks regenerated above were written with CRLF line endings
on Windows and their file digests taken before git normalised them to LF
under `* text=auto eol=lf`. Every digest that named one of the three files
(`westbound_carriageway_lock_sha256` in the junction, lane and collision
locks; `junction_geometry_lock_sha256` in the lane and collision locks;
`lane_topology_lock_sha256` in the collision lock) therefore matched bytes
that never reached the repository, and the cache-independent validators
correctly refused the chain. The digests were recomputed from the committed
bytes, which changed six hash strings and nothing else: the collision
content, its host and chunk digests, and every gate are as recorded above.
Every lock writer in the pipeline now passes an explicit LF newline so a
Windows regeneration cannot drift again. The full map suite passed after the
repair; the C# suite passed 145 tests.

## Remaining work

The next bounded P0-021 slice is the ADR-0019 package build: emit the shipping
FlatBuffer root and chunks plus a semantically reproducible GeoPackage audit,
build twice, compare every shipping byte, and enforce the 64 MB root and 16 MB
chunk ceilings. Runtime loading, coast-to-coast walkers/bots on Linux and
Windows, and the human graybox review remain later gates.
