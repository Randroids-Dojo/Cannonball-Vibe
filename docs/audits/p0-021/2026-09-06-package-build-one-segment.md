# P0-021: the runtime package for one continental segment

Date: 2026-09-06. Related: P0-021, ADR-0019, ADR-0024, ADR-0026,
[the plan](2026-09-06-package-build-plan.md).

Status: `i70-denver-to-cove-fort` builds into a schema-5 sharded package,
loads in the game and passes the headless smoke and the chunk-read probe.
The other eleven segments, the joined chain, the eastbound pair, junction
movements, endpoint connectors and the GeoPackage audit remain open.

## The command

```
python -m cannonball_map build-continental-package --segment i70-denver-to-cove-fort --output DIR
./scripts/run-continental-scenario.sh --smoke-test
./scripts/run-scenario.sh --fixture continental-i70 --distance-miles 20
```

`continental_package.py` reads the committed locks and writes through the
same `write_sharded_package` the fixture build uses, so the ADR-0019
ceilings, the content-version derivation and the runtime verification are
the ones already in force.

| Writer input | Source |
|---|---|
| centreline (EPSG:5070) | `.tools/continental/carriageway/<segment>.json`, admitted only when its geometry sha256 and vertex count reproduce `westbound-carriageway-lock.v1.json`, then the lane lock's corner refinement through the collision stage's `_refined_line` |
| elevation | `corridor-elevation-lock.v1.json` conditioned by `conditioned-profile-lock.v1.json`, lane-eased, sampled through the collision stage's `_elevation_at` |
| samples and chunks | the collision 25 m station grid and 2 km chunk grid: 32,184 samples and 403 chunks, equal to the collision host record |
| lane sections | `lane-topology-lock.v1.json` sections with their stable lane ids and AASHTO widths |
| speed | the lane lock's 70 mph design speed |
| identity | I-70 westbound from the directed route lock's anchors |
| provenance | the NHPN I-70 snapshot `features_sha256` and the continental route lock digest; the 3DEP product family and the elevation profile digest for the spatial reference |

Two authoring decisions are recorded in the package's own provenance
strings: the lane lock's sections span the traveled way between the head
and tail the junction movements own, so the single-segment package
extends the first section to 0 and the last to the edge length; and the
edge ships as `one_way_roadway`, because the divided-carriageway pair
requires the eastbound edge, which has no eased profile or lane sections
of its own yet.

Every input lock digest, the cache geometry digest and the measured sizes
are written beside the package as `continental-package-provenance.json`.

## Measurements

| Quantity | Value | Ceiling |
|---|---|---|
| length | 804,567.2 m (499.93 mi) | |
| samples / chunks | 32,184 / 403 | |
| root `.cbrg` | 1,126,504 bytes | 64,000,000 |
| largest chunk `.cbck` | 4,736 bytes | 16,000,000 |
| all chunks | 1.9 MB | |
| metadata `.json` sidecar | 15.9 MB (uncapped, not shipped) | |
| build time | 31 s | |
| two builds | byte-identical across 406 files | ADR-0019 |

Extrapolated from these per-mile costs, the 2,792-mile canonical path is
roughly a 6 MB root and 10.5 MB of chunks: the whole route fits ADR-0019
with about tenfold headroom.

Runtime, official Godot 4.7.1 headless on Windows: `CANNONBALL_ROUTE_START_OK`
on `i70-denver-to-cove-fort--westbound--lane-000`, `CANNONBALL_SMOKE_OK`
with `max_collision_build_ms=1.997`, and the `--distance-miles 20` probe
reporting `unique_route_miles=499.934884 verified_chunk_reads=403
chunk_failures=0` with the ground contract holding.

## Two things the owner should know

1. **The build is not reproducible from the repository alone.** The
   centreline vertices exist only in the gitignored carriageway cache
   (`.gitignore` excludes `.tools/`), by AGENTS.md policy against committing
   continental downloads. The command refuses a cache that does not match
   the lock and names `derive-continental-westbound-carriageway` as the
   regeneration path, and the repository-segment test skips when the
   cache is absent, so the `continental-i70` fixture cannot join
   `scripts/check.sh`. Committing the digest-locked geometry (about 1 MB
   per segment) or regenerating it offline in CI is an owner decision.
2. **The known I-70 jitter site is in this segment.** The lane lock
   characterises a 13.78 m easing departure and the elevation lock a
   -43.979 % sustained grade over a 1,000 m window on this segment; both
   are upstream findings and will be visible when driven.

## Next

`--all-segments`, then the junction movements and endpoint connectors so
the twelve packages join into the chain, the eastbound pair, the
GeoPackage audit artifact, and the continental runtime scenario the
ledger reserves.
