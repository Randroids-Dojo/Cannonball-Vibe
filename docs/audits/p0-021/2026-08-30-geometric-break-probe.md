# NHPN topology at the disconnected continental break sites

Date: 2026-08-30

Task: P0-021. Performs the geometric probe prescribed by
[the large-gap probe](2026-08-27-large-gap-probe.md).

Status: diagnostic acquisition. No route lock, transfer lock, edge-path lock,
snapping tolerance, selected path, or reconstruction exception changed. The
probe responses remain in the ignored `.tools/continental/nhpn-geometric-probe`
cache.

## Finding

The checksum-locked candidate graph still reproduces **6 of 12 segments
connected** and six unconnected. Those six produce 14 bounded probe sites:
12 component-gap candidates and the two already-recorded transfer-anchor
mismatches. An unfiltered spatial NHPN query finds a local undirected source
path at **5 of 14 sites**. Every one of those five paths uses one or more
OBJECTIDs absent from the candidate lock; none is supplied only by records
already locked for another segment. The other nine sites remain disconnected
in the unfiltered local source graph.

This closes the diagnostic question but not the route-selection question. The
five source paths are candidates for exact acquisition and direction/corridor
validation, not approved bridges. The nine sites with no source path still
need another approved source or an explicit, bounded ADR-0018 reconstruction
exception. Q-034 records that per-break disposition rather than hiding it in
code.

## Method

For each unconnected segment, the command rebuilds the endpoint-snapped graph
from the checksum-locked page cache and requires the result to reproduce the
committed edge-path diagnostics byte-semantically. It then:

1. assigns deterministic component indices;
2. chooses the minimum set of component-pair sites with a minimum spanning
   tree weighted by nearest chain-end separation;
3. adds a separate site for each transfer anchor farther than the locked 25 m
   anchor limit;
4. expands the two site points by 250 m in EPSG:5070 and queries the resulting
   EPSG:4326 envelope with `where=1=1`, so no route sign or state filter can
   hide a local joining feature;
5. rebuilds an endpoint-snapped graph from each complete response and tests for
   an undirected path with the unchanged 1 m endpoint tolerance and 25 m probe
   anchor limit; and
6. classifies the chosen path's OBJECTIDs as in the segment lock, elsewhere in
   the candidate lock, or unacquired.

The minimum spanning tree selects diagnostic sites only. It does not assert
that the nearest components are road-adjacent; the unfiltered source graph must
still supply a path, and even a supplied path is not a westbound or legal-route
selection.

## Results

| Segment and site | Separation | Features | Source path | Path identity |
| --- | ---: | ---: | --- | --- |
| I-10 Ontario to I-405, components 00-01 | 2,491.563 m | 91 | yes | 22 unacquired CA OBJECTIDs signed S-10 / U-101 |
| I-15 Salt Lake to Cove Fort, components 00-01 | 88.176 m | 6 | yes | OBJECTID 43841, U-189, Utah |
| I-15 Salt Lake to Cove Fort, components 00-02 | 27,347.243 m | 68 | no | no local source path |
| I-40 I-81 to Barstow, components 00-01 | 14.069 m | 10 | yes | OBJECTID 38597, S-95, Arizona |
| I-40 I-81 to Barstow, components 01-02 | 1,854.000 m | 47 | no | no local source path |
| I-40 I-81 to Barstow, components 02-03 | 13,571.622 m | 943 | no | no local source path |
| I-40 I-81 to Barstow, components 02-04 | 228.362 m | 3 | yes | OBJECTID 218838, unsigned, Tennessee |
| I-70 Denver to Cove Fort, components 00-01 | 320.000 m | 7 | no | no local source path |
| I-70 Denver to Cove Fort, components 01-02 | 5.819 m | 7 | yes | OBJECTID 59709, I-270 / U-36, Colorado |
| I-78 Holland Tunnel to I-81, from anchor | 381.157 m | 4 | no | anchor remains outside the source graph |
| I-78 Holland Tunnel to I-81, components 00-01 | 3,021.991 m | 13 | no | no local source path |
| I-80 New Jersey to Big Springs, from anchor | 253.027 m | 5 | no | anchor remains outside the source graph |
| I-80 New Jersey to Big Springs, components 00-01 | 1.011 m | 2 | no | no third feature; still 0.011 m beyond the locked tolerance |
| I-80 New Jersey to Big Springs, components 01-02 | 9.190 m | 11 | no | no local source path |

The five positive paths are bounded source-topology facts only:

- OBJECTID 43841 is signed U-189 where the I-15 candidate predicate excluded
  it.
- OBJECTID 38597 is signed S-95 where the I-40 predicate excluded it.
- OBJECTID 218838 is unsigned, the exact class of feature the milepost lens
  could not see.
- OBJECTID 59709 is signed I-270 and U-36 near Denver, not I-70.
- The Los Angeles path uses 22 S-10 and U-101 records. Its existence does not
  establish that this 2.49 km surface/freeway path is the intended I-10 to
  I-405 westbound transfer.

The 1.011 m I-80 discontinuity is deliberately still red. It is only 11 mm
over the locked 1 m endpoint tolerance, but changing that tolerance is a
lock-affecting policy decision; the probe neither widens it nor calls the gap
safe to bridge.

## Provenance and replay

- Base revision: `50baebf368d1ada45395bb4cef68758af746108f`.
- Platform: Windows x86-64, Git Bash; final acquisition UTC:
  `2026-08-31T04:30:40Z`.
- NHPN canonical service metadata SHA-256:
  `5150b91eb2c736bbc2fc26666c6607365bb4b3608187ac459719a3a4e11f50b5`;
  it exactly matches the candidate lock.
- Route selection SHA-256:
  `00ac4df354a8644997a2a073ee07c736ff3f3bc2d2565c8cd9cb51b957d2ff2f`.
- Candidate lock SHA-256:
  `f5ad2786e031a8640a242aae73ee8665a548dfda15368a9b940bd360b73aef72`.
- Transfer lock SHA-256:
  `4a2a0c6e48ab14a54f5bbad1b086e96fcb35e6c3a50e21924428278662f3f175`.
- Edge-path lock SHA-256:
  `30dcb410333d5b7fda9669325e050de4542807c51cb6515b9dfacedfce2dab01`.
- Final diagnostic JSON SHA-256:
  `42c84e4f06eb4ca98047a706e59d3c7df8be94d66d4778943494c38b0b4eb178`.
- The 14 queries returned 1,217 feature classifications with zero retries and
  zero records without usable geometry.
- A second run resumed all 14 pages with zero retries and reproduced identical
  semantics after excluding `acquired_at` and the expected `resumed_pages`
  counter.

The final diagnostic and its replay ran through the repository's uv 0.9.24
shim, resumed all 14 responses, and produced identical semantics. Python
3.13.11, GeoPandas 1.1.4, NetworkX 3.6.1, PyProj 3.7.2, and Shapely 2.1.2
supplied the probe runtime. An earlier exploratory acquisition under the
workstation's uv 0.11.29 produced the same five findings but is not the evidence
artifact cited above.

## Commands and status

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-edge-paths \
  --output .tools/continental/edge-path-repro.json
# exit 0: 6/12 connected

uv run --project tools/map_pipeline --frozen ruff check \
  tools/map_pipeline/src/cannonball_map/continental.py \
  tools/map_pipeline/src/cannonball_map/cli.py \
  tools/map_pipeline/tests/test_continental_pipeline.py
# exit 0

uv run --project tools/map_pipeline --frozen pytest \
  tools/map_pipeline/tests/test_continental_pipeline.py -q
# exit 0: 53 passed

uv run --project tools/map_pipeline --frozen cannonball-map \
  probe-continental-geometric-breaks \
  --output .tools/continental/geometric-break-probe-final.json
# exit 0: 14 sites, 5 source connections

uv run --project tools/map_pipeline --frozen cannonball-map \
  probe-continental-geometric-breaks \
  --output .tools/continental/geometric-break-probe-final-rerun.json
# exit 0: all 14 pages resumed; semantic replay identical

./scripts/check.sh
# exit 0: doctor; warning-free build; 145 xUnit; Ruff; frame-allocation
# scan; continental lock validation; 155 map-pipeline; 13 PlayGodot unit;
# official Godot 4.7.1 save-writing smoke
```

The complete local gate ran from `2026-08-31T04:32:21Z` through
`2026-08-31T04:32:47Z` and passed every step. Its summary SHA-256 is
`74cbc59ca0ffe7f560a7ef479270b73ba4fdfadc2e4972e0a23fa999e10af2a3`;
the doctor report SHA-256 is
`33cb1935e7bc974bbc4cc89452ab1f85a6648768cd2301f08b7df88be56e1dca`.
The Godot smoke reached 80.7 mph, wrote a save at 56.4 m, completed at 60.3 m,
and reported 18.236 ms maximum chunk build and 2.228 ms maximum collision
build.

Two pre-gate invocations failed and were recovered without code changes. A
repository-root `pytest` command used only the map-pipeline environment and
incorrectly collected PlayGodot tests, producing five import-collection
errors; the scoped map command fixed the invocation. The first pinned full-map
attempt then saw 33 existing geodata tests fail while Pyogrio transiently could
not load its bundled GDAL DLL after earlier overlapping uv environment
activity; that timing is a possible cause, not an established one.
`import pyogrio._io` passed immediately afterward, the unchanged scoped suite
passed 154/154, and the serial full front door passed the same 154 tests. These
were command/environment retries, not withdrawn test failures.

## Next bounded decision

Q-034 must dispose each site under ADR-0018. The working default is to acquire
and lock nothing yet: validate travel direction, route role, and corridor fit
for the five positive paths; seek another approved source or write a bounded
reconstruction exception for each of the nine negative sites. No one may infer
approval for the five paths merely because the source graph connects them.
