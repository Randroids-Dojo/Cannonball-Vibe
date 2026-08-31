# Q-034 per-site ADR-0018 disposition of the continental break sites

Date: 2026-08-31

Task: P0-021. Performs the per-site disposition the two
[2026-08-30 probes](2026-08-30-geometric-break-probe.md) prescribed
([census](2026-08-30-spatial-break-probe.md)), with the two evidence inputs
that were still missing gathered first: the bounded interior sweep of the four
break-pair interiors wider than the census windows, and scoped probes of the
ADR-0026 supplementary NHS source at every bounded site and swept interior.

Status: evidence acquisition plus an authored disposition record. **No lock is
modified, nothing is bridged, no direction is selected, and the 1 m endpoint
tolerance is unchanged.** The dispositions are recorded in the new validated
artifact `data/routes/continental/break-disposition.v1.json`
(`43fd75072b69cc9fa33ffdf3a77ae7c9407ea384caf13bbd3e3bd557554141fe`), whose
status — `dispositions_recorded_lock_revision_pending` — says exactly what it
is: the decision record the lock revision must implement, not the revision.

## What was still unknown, and what closed it

The census named its own evidence hole: the four break-pair interiors wider
than its 500 m windows (~10.5 km). A new command,
`probe-continental-gap-interiors`, tiles each such interior with overlapping
unfiltered envelope windows using the same snapped-graph builder, break-end
selection, pairing, envelope helper, and paging/checkpoint/page-hash/
drift-refusal discipline as the census (the break-end selection and pairing
were factored into shared helpers so the two artifacts cannot disagree).
Pairs separated beyond 5 km are recorded as `beyond_sweep_limit` rather than
swept: those pairings (27.3 km, 13.6 km, and the multi-hundred-km spur
pairings) measure fragment isolation, not candidate mainline breaks, and their
milepost interiors were already characterised by the
[2026-08-27 whole-key probe](2026-08-27-large-gap-probe.md).

ADR-0026 adopted NTAD NHS but nothing had yet acquired from it. A second new
command, `probe-continental-nhs-breaks`, adds that capability under the
catalog entry: it refuses a service URL outside the catalog
`allowed_url_prefixes`, refuses a service whose identity or 17 U.S.C. § 101
public-domain declaration changed, optionally refuses a metadata hash drift
against a caller-named expected snapshot, and acquires with the exact
paging/checkpoint/page-hash/retry discipline of the NHPN acquisition. It
probed all 14 bounded sites (250 m-padded envelopes) and the four swept
interiors (the same tiled windows).

## Interior-sweep findings (NHPN, unfiltered)

```
4 gap interiors swept (10.5 km), 23 windows, 184 unique unlocked features
classified, 0 retries; semantic replay identical on a full re-run
```

| Gap interior | Separation | Classification | What is there |
| --- | ---: | --- | --- |
| Los Angeles, downtown pairing 1 | 2,491.563 m | mainline candidate on axis | 10 on-axis records — but they are **I-5** records (key `000000000501037`, mileposts 133.5–135.1), plus US-101/S-60/S-10 records crossing or near the chord. The straight chord between the break ends runs through the East Los Angeles interchange, not along I-10. |
| Los Angeles, downtown pairing 2 | 3,116.620 m | mainline candidate on axis | 2 on-axis US-101 records; S-10 records cross the chord at 77–82°, showing the mainline curves away from the straight reference chord. |
| Albuquerque Big-I | 1,854.000 m | aligned facilities off axis only | Zero on-axis records anywhere in the interior; 21 aligned frontage-road records 300+ m off the chord. The mainline void spans the whole gap. |
| I-78 Delaware River | 3,021.991 m | crossings only on axis | Only PA S-611 and unsigned crossing records (48–76°); the mid-river window returns **zero** NHPN features, so it has no pages to resume — the one intentionally re-fetched window in the replay. |

The sweep therefore closes the interiors question: NHPN carries no unlocked
mainline continuation inside the Albuquerque or Delaware River gaps, and what
it carries inside the Los Angeles gaps is the downtown freeway tangle
(I-5/US-101/S-60/S-10), not a clean I-10 mainline on the chord.

## NHS probe findings (ADR-0026 supplementary source)

```
14 sites and 4 gap interiors probed; 14 of 14 sites have NHS geometry within
the 80 m lens of both ends; 297 site features and 148 interior features;
0 retries; pinned re-run against the recorded metadata hash resumed all site
pages and reproduced identical semantics
```

NHS carries the declared route with **continuous state-LRS measures across
every site**, including every NHPN void:

| Site | NHS route (state/route ID) | Signed | Measure span | Largest gap |
| --- | --- | --- | --- | ---: |
| LA downtown | 06/`SHS_010._P` | I-10, S-10 | 15.824–17.572 | 0.0 |
| Payson 88 m | 49/`0015PM` (+`0189PM`) | I-15 (+U-189) | 263.07–265.59 | 0.0 |
| I-15 fragment 27.3 km | 49/`0015PM` | I-15 | 244.838–265.59 (62 records) | 0.0 |
| Topock 14 m | 04/`I 040` | I-40 | 0.23–3.222 | 0.0 |
| ABQ Big-I 1.85 km | 35/`I40P` | I-40 | 157.995–159.61 | 0.0 |
| ABQ fragment 13.6 km | 35/`I40P` | I-40 | 159.149–168.85 | 0.0 |
| Memphis 228 m | 47/`79I0040001` | I-40 | 1.45–2.54 | 0.0 |
| Rifle 320 m | 08/`070A` | I-70 | 81.364–86.984 (one feature) | 0.0 |
| Denver 5.8 m | 08/`070A` (+`270A`) | I-70 (+I-270) | 279.395–280.498 | 0.0 |
| I-78 anchor 381 m | 34/`00000078__` | I-78 | 66.339–67.16 | 0.0 |
| Delaware River 3.0 km | 42/`6 48 48B3 - 86216` | I-78 | 0.0–2.669 | 0.0 |
| I-80 anchor 253 m | 34/`00000080__` | I-80 | 42.57–43.27 | 0.0 |
| Omaha 1.011 m | 31/`080` | I-80 | 445.05–445.48 | 0.0 |
| Quad Cities 9.19 m | 17/`037  10080 000000` (+I-74 key) | I-80 (+I-74) | 3.91–5.52 | 0.0 |

The 80 m lens is a reporting device grounded in the catalog's documented NHPN
horizontal error; nothing is snapped, joined, or selected at that distance.

## The dispositions

Recorded, validated, and pinned in `break-disposition.v1.json`; the validator
(`validate-continental-break-dispositions`) enforces the structure, the class
vocabulary, the input-hash pins, full unconnected-segment coverage, the
already-locked-OBJECTID exclusion for acquisition candidates, and the 30 m
bounded-exception ceiling. It now runs inside
`scripts/validate-continental-route.sh`.

| Site | Separation | Disposition | Named records / boundary |
| --- | ---: | --- | --- |
| i10-ontario-to-i405--component-00-01 | 2,491.563 m | **ambiguous → Q-034a** | Mainline continues as S-10 on the segment's own key; exact record set needs a directed whole-key milepost review of `000000001001037` |
| i15-salt-lake-to-cove-fort--component-00-01 | 88.176 m | **NHPN scoped acquisition** | OBJECTIDs 43839, 43841 (U-189, exact joins, 0.4°/44°) |
| i15-salt-lake-to-cove-fort--component-00-02 | 27,347.243 m | **NHS fill** | 49/`0015PM`, 62 records, no measure gap |
| i40-i81-to-barstow--component-00-01 | 14.069 m | **ambiguous → Q-034b** | The ~88° Topock tee: acquire the S-95 slivers, NHS-fill, or a bounded exception — evidence does not force the mechanism |
| i40-i81-to-barstow--component-01-02 | 1,854.000 m | **NHS fill** | 35/`I40P` through the Big-I; NHPN interior confirmed void on axis |
| i40-i81-to-barstow--component-02-03 | 13,571.622 m | **NHS fill** | 35/`I40P`, no measure gap |
| i40-i81-to-barstow--component-02-04 | 228.362 m | **NHPN scoped acquisition** | OBJECTID 218838 (unsigned concurrency, 3°, mileposts exactly filling) |
| i70-denver-to-cove-fort--component-00-01 | 320.000 m | **NHS fill** | 08/`070A` single spanning feature; NHPN void is one-sided (west) |
| i70-denver-to-cove-fort--component-01-02 | 5.819 m | **NHPN scoped acquisition** | OBJECTID 59709 (I-270/U-36-signed junction pavement, 1.1°) |
| i78-holland-tunnel-to-i81--anchor-from | 381.157 m | **ambiguous → Q-034c** | Anchor re-derivation vs approach-record acquisition; transfer-lock-affecting |
| i78-holland-tunnel-to-i81--component-00-01 | 3,021.991 m | **NHS fill** | 42/`6 48 48B3 - 86216` across the Delaware River |
| i80-new-jersey-to-big-springs--anchor-from | 253.027 m | **ambiguous → Q-034d** | Same class as Q-034c |
| i80-new-jersey-to-big-springs--component-00-01 | 1.011 m | **bounded ADR-0018 exception** | Authoring micro-gap; boundary = the two probed end coordinates, length 1.011 m |
| i80-new-jersey-to-big-springs--component-01-02 | 9.190 m | **bounded ADR-0018 exception** | Authoring micro-gap replicated across two route families (I-74/I-280 records 229625/229626 join both ends yet carry the same 9.190 m gap); length 9.190 m |

Counts: 3 NHPN scoped-acquisition candidates, 5 NHS fills, 2 bounded
exceptions, 4 ambiguous (each a named Q-034 sub-item, never forced). All 31
census break ends are reconciled in the record's `census_ends` section: 22
covered by a site disposition, 4 fragment ends embedded in other routes'
pavement, and 5 spur/beyond-corridor ends (Tremonton, Knoxville, Fremont
Junction, Kanorado, Chicago).

Scope limits, stated because they are easy to overread:

- A scoped-acquisition candidate names records that may enter the **candidate
  superset**; the westbound directed edge selection remains a later solve and
  may reject any of them. No direction is validated here.
- An NHS-fill disposition names the evidence that NHS carries the corridor; it
  does not acquire, conflate, or lock NHS geometry. That is the deferred lock
  revision.
- The two exceptions are bounded to their probed end coordinates and lengths
  (1.011 m and 9.190 m, both far under the 30 m ceiling the validator
  enforces); authoring the actual overlays goes through the ADR-0018
  generation gates when the reconstruction stage exists.

## Provenance and replay

- Base revision: `241b876` (main) on branch
  `agent/p0-021-per-site-disposition-20260831`; platform: macOS 26.7 arm64.
- Runtime: uv 0.9.24, Python 3.13.11, GeoPandas 1.1.4, NetworkX 3.6.1,
  PyProj 3.7.2, Shapely 2.1.2.
- The live NHPN service metadata is byte-identical to the locked canonical
  hash (`5150b91e…`, `dataLastEditDate` 1720466290444). The locked response
  cache was regenerated from the live service on this machine and reproduced
  the committed candidate lock exactly modulo acquisition timestamps, and
  `derive-continental-edge-paths` from that cache reproduced the committed
  edge-path lock's `segments_sha256` exactly.
- NHS service: item `dce9f09392eb474c8ad8e6a78416279b`, Version 2025.08.08,
  canonical metadata SHA-256
  `a29f96df0512d0748d0c243cf15867d432439f6df5927d9b9d682e167410c027`,
  `dataLastEditDate` 1778183346545, public-domain declaration verified.
- Interior sweep artifact SHA-256:
  `849c5db967f0b8503aab6d034419d38f1cd4d3f7b324d681cb2a5698f9fc7f69`
  (final acquisition UTC `2026-08-31T06:00:04Z`); a full re-run resumed 22 of
  23 windows from checkpoints (the 23rd is the zero-feature mid-river window,
  which has no pages to resume) and reproduced identical semantics after
  excluding `acquired_at` and the retry/resume counters.
- NHS probe artifact SHA-256:
  `db2c70de279bc551512d8cffb7ceb39739a697ae6de5bb263b7e224fd9d695ef`
  (final acquisition UTC `2026-08-31T06:02:25Z`); the re-run was pinned with
  `--expected-metadata-sha256 a29f96df…`, resumed all 14 site pages, and
  reproduced identical semantics under the same exclusions.
- Zero retries across both probes. All probe responses stay in the ignored
  `.tools/continental/nhpn-interior-sweep` and
  `.tools/continental/nhs-break-probe` caches; nothing continental is
  committed.
- Input pins recorded in the disposition artifact: route selection
  `00ac4df3…`, candidate lock `5c35de08…`, transfer lock `37cf05ee…`,
  edge-path lock `a0d4e791…` (the current post-ADR-0026 pin chain; the
  2026-08-30 audits recorded the pre-re-bless hashes that were true at their
  verification time).

## Commands and status

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-nhpn --output .tools/continental/route-lock-repro.json
# exit 0: reproduces the committed lock modulo timestamps

uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-edge-paths \
  --output .tools/continental/edge-path-repro.json
# exit 0: 6/12 connected; segments_sha256 identical to the committed lock

uv run --project tools/map_pipeline --frozen cannonball-map \
  probe-continental-gap-interiors \
  --output .tools/continental/interior-sweep.json
# exit 0: 4 gap interiors swept (10.5 km), 2 with an on-axis aligned feature,
# 0 with nothing beyond the locked records
# re-run: 22/23 windows resumed; semantic replay identical

uv run --project tools/map_pipeline --frozen cannonball-map \
  probe-continental-nhs-breaks \
  --output .tools/continental/nhs-break-probe.json
# exit 0: 14 sites and 4 gap interiors probed, 14 sites with NHS geometry
# within the lens of both ends
# re-run with --expected-metadata-sha256 a29f96df…: all site pages resumed;
# semantic replay identical

uv run --project tools/map_pipeline --frozen cannonball-map \
  validate-continental-break-dispositions \
  data/routes/continental/break-disposition.v1.json
# exit 0: 14 sites: ambiguous=4, bounded_reconstruction_exception=2,
# nhpn_scoped_acquisition=3, nhs_fill=5
```

```bash
GODOT_BIN=…/Godot ./scripts/check.sh
# exit 0: doctor; warning-free build; 145 xUnit; Ruff; frame-allocation scan;
# continental lock, transfer, edge-path, and break-disposition validation;
# 187 map-pipeline tests; 13 PlayGodot unit tests; official Godot 4.7.1
# save-writing smoke (80.7 mph peak, save at 56.1 m, 11.257 ms max chunk
# build, 1.223 ms max collision build)
```

The gate summary SHA-256 is
`622fb07ccc1cd667d21ef41124eb853071efcf36858821b6c3287f9bcec552ba`; the
doctor report SHA-256 is
`33cb1935e7bc974bbc4cc89452ab1f85a6648768cd2301f08b7df88be56e1dca`. One
repository-root `pytest` invocation failed by collecting PlayGodot tests with
the map-pipeline environment — the same known invocation trap the 2026-08-30
audit recorded — and the scoped `pytest tools/map_pipeline` invocation was
used instead; no test was changed.

New unit tests cover the window tiling, the chord-metric tier ladder, the
sweep's covered/beyond-limit routing and checkpoint resumption, the shared
break-end selection (via the unchanged census suite), NHS metadata identity
and public-domain validation, catalog URL-allowlist enforcement, NHS
route-group/spanning classification and void reporting, expected-hash drift
refusal, and the disposition validator's pins, coverage, exception ceiling,
and already-locked-OBJECTID exclusion — all through fake transports and
fabricated payloads in the existing test style.

## Next bounded decision

The lock revision that implements the unambiguous dispositions, in one
coherent slice: extend the candidate-lock machinery with a validated
supplementary-acquisition section, acquire OBJECTIDs 43839, 43841, 218838,
and 59709, re-derive the transfer and edge-path locks against the revised
candidate lock, and record the NHS acquisition locks for the five NHS-fill
sites. Separately, Q-034a–d stay open as named sub-items; none of them blocks
the unambiguous subset.
