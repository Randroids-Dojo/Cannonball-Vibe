# Q-034 continental topology closure

Date: 2026-08-31

Task: P0-021. Executes the closure slice the
[lock revision](2026-08-31-lock-revision.md) prescribed: resolve Q-034c and
Q-034d (the two transfer-anchor mismatches), stand up the ADR-0018
reconstruction gates for authored exceptions, and author the two pinned
micro-gap overlays through those gates.

Status: **topology closed — 12 of 12 segments chain anchor-to-anchor** (was 8
pure-NHPN, 10 with fills). The continuously locked/chained corridor is
**6,294.1 mi** (was 4,594.5). Q-034 has no remaining sub-item: a–d are all
resolved and implemented, every one of the 14 disposition sites carries an
implemented, machine-checked mechanism, and the disposition record moved to
`lock_revision_implemented_topology_closed`. The 1 m endpoint tolerance and
the 25 m anchor snap limit are unchanged; no direction is selected and no
authoritative distance is claimed.

## Q-034c/d — mechanism decision: edge-split-at-anchor

The 2026-08-31 measure review had cut the space to two mechanisms: re-derive
each mismatched anchor onto a candidate record endpoint, or teach the
edge-path solve to split an edge at an on-edge anchor. **Edge-split-at-anchor
was adopted**, on four grounds:

1. **Determinism.** Both anchors lie exactly on a locked record's interior at
   0.000 m line offset (i78: 433412 Holland Tunnel; i80: 431704). The split
   point is the anchor's projection onto that checksum-locked geometry — a
   pure function of two locked inputs. Re-derivation would instead couple a
   locked coordinate to whichever record endpoint happens to be nearest
   (381.157 m and 253.027 m away), an artifact of NHPN record segmentation
   that can move whenever the candidate set grows.
2. **Minimal disturbance.** The mechanism is a fallback used only when no
   record endpoint lies within the unchanged 25 m anchor snap limit, so the
   ten endpoint-anchored segments' solves are untouched by construction —
   verified entry-identical on re-derivation — and the ADR-0024 transfer lock
   stays byte-identical (`b267282a1d48…`, re-derivation reproduced
   `transfer_nodes_sha256` exactly).
3. **Architectural fit.** Shipping route state is edge ID plus
   distance-along-edge (AGENTS.md architecture boundary), so a transfer node
   on a record's interior is exactly representable. The two anchors were
   themselves derived by `snap_to_segment` onto these records' interiors —
   the anchors' own locked evidence already names the records the solve now
   splits.
4. **Product fit.** Re-derivation would move the Holland Tunnel portal and
   the US-46/I-80 transfer coordinate — research-grounded, product-visible
   route endpoints — by 381 m and 253 m. The split moves nothing.

### Implementation

`_solve_segment_edge_path` resolves each anchor through a shared
`_resolve_anchor_node`: endpoint snapping takes precedence exactly as before;
beyond the anchor limit, the deterministically nearest locked record line
within that same 25 m limit is split at the anchor's projection, replacing
its edge with two sub-edges joined at a node on the projection. The lock
records the split machine-checkably (`anchor_edge_splits`: side, OBJECTID,
part, page hash, perpendicular offset, split distance along the part) and any
solved edge that traverses a sub-edge carries `part_range_m`, the exact metre
range of the record part it covers. The validator enforces the anchor limit
on both the offset and the anchor-to-node distance, side uniqueness, page
hashes, interiority, and agreement between the recorded snap distance and the
split. The chain-connectivity model applies the identical fallback through
the same helper, so the two artifacts cannot disagree.

Re-derived against the regenerated cache, both splits landed at 0.000 m
offset:

| Segment | Split record | Part length | Split at | Anchor distance before → after |
| --- | --- | ---: | ---: | --- |
| i78-holland-tunnel-to-i81 (from) | 433412 (Holland Tunnel) | 1,576.081 m | 381.157 m | 381.157 m → 0.000 m |
| i80-new-jersey-to-big-springs (from) | 431704 (I-80) | 742.918 m | 253.027 m | 253.027 m → 0.000 m |

Both segments remain honestly unconnected in pure NHPN (8/12 unchanged): the
failure reason moved from "anchor farther than the anchor snap limit" to "no
connected path" — the Delaware River fill span and the two Omaha/Quad Cities
micro-gaps, exactly the remaining dispositions. All ten other segment entries
are byte-identical to the previous lock. Revised edge-path lock
`fcf0da1dcff8…`.

## ADR-0018 reconstruction gates

A new stage authors bounded exceptions as first-class deterministic content:
`author-continental-reconstruction-overlays` consumes only checksum-locked
inputs plus the locked response cache (no network), authors each
`bounded_reconstruction_exception` site as a chord overlay between the exact
boundary coordinates the disposition pinned, and **accepts it only when every
applicable gate passes**, refusing with machine-readable JSON diagnostics
otherwise (gate name, site, measured value, threshold, finding):

- **endpoint_position** — each boundary coordinate must land on a locked
  chain-end node within the unchanged 1 m endpoint tolerance (measured
  0.000 m at all four ends).
- **length_bound** — the chord recomputed in EPSG:5070 must agree with the
  pinned exception length within 5 mm and sit under the 30 m
  bounded-exception ceiling.
- **source_adjacency** — the two boundary nodes must present record ends that
  are milepost-contiguous on a shared LRS key (the 2026-08-14 adjacency
  rule): the exception class exists for gaps whose adjacency the source
  itself asserts, and anything else is a corridor void the gate refuses to
  author over.
- **self_intersection** — trivially checked for the two-vertex chord.
- **heading** is measured, not adjudicated: the adjoining record ends'
  25 m-chord tangents are recorded as the reconstruction-geometry stage's
  authoring constraint (see the Quad Cities finding below), and the
  curvature/grade/sightline/collision/lane/drivability gates are recorded as
  **explicitly deferred** to that stage with the reason — never silently
  skipped: the overlay is a bounded topological closure, not drivable
  surface geometry, and those gates measure the generated road.

Each overlay preserves ADR-0018's contract: stable identifier
(`<site_id>--authored-overlay`), recursive provenance (pins to all six
upstream artifacts; the disposition's full evidence chain including the probe
audits and the interior-sweep/NHS-probe response-artifact hashes; the
adjoining records' OBJECTIDs, mileposts, and locked page-response hashes),
validation (`validate-continental-reconstruction-overlays`,
cache-independent, wired into `scripts/validate-continental-route.sh`), and
content-addressed output (`overlays_sha256`, per-overlay `geometry_sha256`,
`chain_connectivity_sha256`).

## The two authored overlays

| Overlay | Boundary (pinned) | Length | Adjacency (shared key) | End-tangent deviation |
| --- | --- | ---: | --- | ---: |
| `i80…component-00-01--authored-overlay` (Omaha) | 189077 start ↔ 189376 start | 1.011 m | `000000008000055`, mp 444.787–445.032 ↔ 445.032–445.369 | 0.0° |
| `i80…component-01-02--authored-overlay` (Quad Cities) | 229620 end ↔ 229624 start | 9.190 m | `0000I0800000073`, mp 0.904–0.984 ↔ 0.984–1.061 | 77.2° |

Both boundaries are byte-equal to the disposition's pinned exception
boundaries (the validator enforces the equality), both lengths reproduce from
the pinned coordinates to the millimetre, and both sit far under the 30 m
ceiling.

**Quad Cities finding.** The first authoring run *rejected* the site: an
earlier draft of the heading gate required the adjoining end tangents to
agree within the census's 20° alignment lens, and they disagree by 77.2°.
Inspection of the locked geometry showed why: 229620 arrives at the gap
heading ~-176.8° (east→west) while 229624 departs at ~106° — the gap sits
exactly on the corner of I-80's own LRS at the I-80/I-74 interchange, where
the designated route turns through the junction (the same authoring
discontinuity the census measured replicated on the joining I-74/I-280
records 229625/229626, per the
[2026-08-30 break-end census](2026-08-30-spatial-break-probe.md)). A
straight-through heading precondition is the wrong gate for a topological
closure at a corner the source itself asserts: heading and curvature are
properties of the generated road, adjudicated by the geometry stage's own
ADR-0018 gates. The gate was reshaped to record the measured corner as that
stage's authoring constraint (the validator requires the measurement to be
present and finite), and the rejection-first run stands as evidence the gates
actually reject.

## Connectivity: before and after

| Metric | Before | After |
| --- | ---: | ---: |
| Segments with an undirected pure-NHPN path anchor-to-anchor | 8 of 12 | 8 of 12 (unchanged — nothing was added to NHPN) |
| Segments chaining anchor-to-anchor (NHPN + fills + overlays + splits) | 10 of 12 | **12 of 12** |
| Continuously locked/chained corridor | 4,594.5 mi | **6,294.1 mi** |

- New chains: i78-holland-tunnel-to-i81 143.6 mi (228,062.6 m NHPN including
  the split sub-edge + 3,022.0 m Delaware River fill chord) and
  i80-new-jersey-to-big-springs 1,556.0 mi (2,504,060.3 m NHPN + 10.2 m of
  authored overlay chords).
- The fill lock's own chain section (fills + splits, no overlays) moved 2 → 3
  chained: i78 chains at the fill stage; i80 lists exactly its two exception
  sites as blockers until the overlay lock bridges them.
- Chain lengths are shortest undirected mixed-ancestry chains; fill and
  overlay spans contribute chord length only. Not an authoritative distance
  and not a westbound selection.

## Artifact and lock-chain state

| Artifact | Status | SHA-256 |
| --- | --- | --- |
| `data/sources/continental-route-lock.json` | unchanged | `cbdaaa3710e2b2e9…` |
| `data/routes/continental/transfer-node-lock.v1.json` | **unchanged (byte-identical)** | `b267282a1d480147…` |
| `data/routes/continental/edge-path-lock.v1.json` | re-derived (splits recorded) | `fcf0da1dcff80eb7…` |
| `data/routes/continental/nhs-fill-lock.v1.json` | re-issued (new edge pin, chain 3/4) | `2d05552540107464…` |
| `data/routes/continental/break-disposition.v1.json` | `lock_revision_implemented_topology_closed` | `48c9a40e33bf6a30…` |
| `data/routes/continental/reconstruction-overlay-lock.v1.json` | new — `micro_gap_overlays_authored_conflation_pending` | `b01be230edc495e5…` |

The disposition validator now proves closure: no ambiguous site may remain,
each `anchor_edge_split` site must be implemented by a matching recorded
split in the edge-path lock, and the overlay lock must pin the disposition's
hash and cover exactly the exception sites (each artifact reads the other
raw, so the mutual pins close without recursion).
`scripts/validate-continental-route.sh` runs six stages: candidate, transfer,
edge-path, NHS fill, break dispositions (now with `--overlay-lock`), and the
reconstruction overlays.

## Provenance and replay

- Base revision: `9dd46b9` (main), branch
  `agent/p0-021-topology-closure-20260831`; macOS 26.7 arm64; uv 0.9.24,
  Python 3.13.11, GeoPandas 1.1.4, NetworkX 3.6.1, PyProj 3.7.2,
  Shapely 2.1.2.
- The NHPN response cache (base and supplementary) was regenerated from the
  live service before anything else: the base acquisition reproduced the
  twelve committed segment snapshots byte-identically (only `created_at` and
  the base-only union differ from the supplemented lock), and the supplements
  acquisition reproduced the committed supplements exactly modulo acquisition
  timestamps. Live NHPN metadata remained byte-identical to the locked hash
  (`5150b91e…`). The NHS fill acquisition was pinned with
  `--expected-metadata-sha256 a29f96df…` and matched.
- Replay of every revised lock is exact: `derive-continental-transfers`
  reproduces the committed transfer nodes byte-identically;
  `derive-continental-edge-paths` twice produces identical `segments` and
  `segments_sha256`; `acquire-continental-nhs-fills` resumes all five site
  page sets from checkpoints (0 retries) and reproduces the fill lock exactly
  modulo acquisition timestamps with an identical
  `chain_connectivity_sha256`; `author-continental-reconstruction-overlays`
  twice produces identical locks modulo `authored_at`.
- All responses stay in the ignored `.tools/continental/` caches; nothing
  continental is committed. `data/sources/catalog.json` is untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-nhpn --output .tools/continental/route-lock-repro.json
# exit 0: reproduces the committed base snapshots byte-identically

uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-nhpn-supplements \
  --output .tools/continental/route-lock-supplements-repro.json
# exit 0: 5 sites, 28 records; identical modulo acquisition timestamps

uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-edge-paths
# exit 0: 8/12 connected; i78/i80 anchors resolved by recorded edge splits

uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-nhs-fills \
  --expected-metadata-sha256 a29f96df0512d0748d0c243cf15867d432439f6df5927d9b9d682e167410c027
# exit 0: 5 fill sites, 3 of 4 unconnected segments chain with fills

uv run --project tools/map_pipeline --frozen cannonball-map \
  author-continental-reconstruction-overlays
# exit 0: 2 overlays, 12/12 segments chaining anchor-to-anchor

./scripts/validate-continental-route.sh
# exit 0: all six stages green
```

## Verification

`ruff` clean; 210 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`; the repository-root bare `pytest` collection
trap is unchanged). New unit tests cover the split fallback (on-edge anchor
resolution, partial-edge ranges, reversed sub-edge travel, endpoint
precedence), the edge-path validator's split tampering rejections (offset
over the limit, invalid side, unlocked page hash, drifted distance, exterior
split), the overlay authoring gates (each hard gate's rejection path through
fabricated geometry), the overlay validator's semantic tampering rejections
(claimed direction, boundary drift, failed gate, missing heading measurement,
partial coverage, unauthored citation, corridor drift), the closed
disposition status (overlay lock required, ambiguous site rejected,
unimplemented anchor split rejected), and the repository artifacts' exact
recorded state.

`GODOT_BIN` resolved through `scripts/godot.sh` (official 4.7.1.stable.mono);
`./scripts/check.sh` passed every step: doctor, warning-free dotnet build,
xUnit suite, Ruff, frame-allocation scan, the six-stage continental
validation (candidate, transfer, edge-path, NHS fill, break dispositions with
the overlay lock, reconstruction overlays), 210 map-pipeline tests (scoped
`pytest tools/map_pipeline` — the documented invocation; the repository-root
bare `pytest` collection trap is unchanged), 13 PlayGodot unit tests, and the
official-Godot save-writing smoke (80.7 mph peak, save at 56.4 m, 10.598 ms
max chunk build, 1.256 ms max collision build). Gate summary SHA-256
`0f431ca5e4ebdf7b7ba746269901417b45567195745aa80f2bd5dafb209d3206`; doctor
report SHA-256
`33cb1935e7bc974bbc4cc89452ab1f85a6648768cd2301f08b7df88be56e1dca`.

## What P0-021 still needs

1. **NHPN↔NHS geometry conflation** over the five locked fill spans (the fill
   lock records what NHS asserts; nothing is conflated yet).
2. **3DEP product lock** (product, resolution, date, datums) over the closed
   corridor, then elevation for all geometry including the fill spans and the
   two overlay connections.
3. **Westbound directed edge selection** over the closed topology (the
   present chains are undirected; a shortest undirected chain can cross
   between opposing carriageways).
4. **Reconstruction geometry**: directed carriageways, ramps, lane topology,
   collision, and endpoint connectors, with the full ADR-0018 gate battery —
   including the deferred heading/curvature gates at the two overlay sites
   (Quad Cities carries a recorded 77.2° corner constraint).
5. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`, byte-identical double builds, and
   the walker/bot traversals on both platforms.
6. **Human gates**: corridor-level geographic plausibility review and the
   coast-to-coast graybox drive.

## Next bounded decision

The NHPN↔NHS conflation model over the locked fill spans, and the 3DEP
product lock over the closed corridor — the two remaining inputs the
reconstruction-geometry stage needs before the westbound directed selection
can be solved and validated.
