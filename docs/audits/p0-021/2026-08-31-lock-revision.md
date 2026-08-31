# Q-034 continental lock revision

Date: 2026-08-31

Task: P0-021. Implements the lock revision the
[per-site disposition](2026-08-31-per-site-disposition.md) prescribed, as one
coherent change: a supplementary-acquisition extension of the candidate lock,
NHS acquisition locks for the five fills, and the transfer/edge-path
re-derivations, all landing together. Two of the four Q-034 sub-items
(Q-034a, Q-034b) resolved analytically under the methods the register
prescribed and are folded into the scoped acquisitions; the two anchor
sub-items (Q-034c/d) stay open with their mechanism space cut in half by a
measure review.

Status: **locks revised**. The candidate, transfer, and edge-path locks moved
together; the new NHS fill lock and the disposition record's implemented
status landed in the same change. The 1 m endpoint tolerance and the 25 m
anchor snap limit are unchanged; nothing was bridged outside what a source
asserts; no direction is selected and no authoritative distance is claimed.
The two ADR-0018 micro-gap overlays are **not** authored here — they wait for
the reconstruction gates.

## What entered each lock

### Candidate lock — supplementary acquisitions (`data/sources/continental-route-lock.json`)

A new `nhpn.supplementary_acquisitions` section extends the lock without
rewriting history: the twelve 2026-08-04 segment snapshots are byte-identical,
each supplement carries the full acquisition discipline (exact `OBJECTID IN`
predicate, page hashes, checkpoint cache, SHA-256 at ingest, acquisition
timestamp), and the live service was verified byte-identical to the locked
metadata hash (`5150b91e…`, `dataLastEditDate` 1720466290444) before anything
was fetched — a drifted service refuses the acquisition. The candidate union
grew 15,525 → 15,553 (28 records across 5 sites, acquired
`2026-08-31T07:03:57Z`):

| Site | Records | Features SHA-256 (prefix) |
| --- | --- | --- |
| i10-ontario-to-i405--component-00-01 | 23 (S-10/U-101 downtown LA set) | `ac33bb96fe500507` |
| i15-salt-lake-to-cove-fort--component-00-01 | 43839, 43841 (U-189 Payson) | `43b3023ad639a484` |
| i40-i81-to-barstow--component-00-01 | 38597 (Topock junction sliver) | `9731919bf5212583` |
| i40-i81-to-barstow--component-02-04 | 218838 (unsigned Memphis) | `333e6de024b8a058` |
| i70-denver-to-cove-fort--component-01-02 | 59709 (I-270/U-36 Denver) | `1493492f28811d32` |

Validation (`validate-continental-lock`) now enforces the supplement
discipline: site scoping to a locked segment, Q-034/disposition ancestry,
exact predicate reconstruction, the shared page/hash/timestamp contract, no
overlap with the base union or another supplement, and the recomputed
candidate union over base plus supplements.

Revised lock SHA-256:
`cbdaaa3710e2b2e9409628f32fb1ef16228ec2256c5b8f1428d3363618e73900`.

### NHS fill lock — new artifact (`data/routes/continental/nhs-fill-lock.v1.json`)

`acquire-continental-nhs-fills` acquires the five `nhs_fill` disposition
sites from the ADR-0026 NTAD NHS source under catalog entry
`usdot-ntad-national-highway-system`, with the exact NHPN discipline: catalog
URL-prefix enforcement, service identity and 17 U.S.C. § 101 public-domain
validation, `--expected-metadata-sha256 a29f96df…` drift refusal (the live
service matched the disposition evidence's hash exactly), envelope paging with
checkpoints and page hashes, SHA-256 at ingest, and acquisition timestamps
(`2026-08-31T07:06:45Z`). Every site's fill route group reproduced the
disposition evidence exactly — zero state-LRS measure gap at all five:

| Site | NHS route | Fill records | Measure span |
| --- | --- | --- | --- |
| i15…component-00-02 | 49/`0015PM` (I-15) | 62 | 244.838–265.59 |
| i40…component-01-02 | 35/`I40P` (I-40, Big-I) | 10 | 157.995–159.61 |
| i40…component-02-03 | 35/`I40P` (I-40) | 25 | 159.149–168.85 |
| i70…component-00-01 | 08/`070A` (I-70, Rifle) | 1 | 81.364–86.984 |
| i78…component-00-01 | 42/`6 48 48B3 - 86216` (I-78) | 2 | 0.0–2.669 |

The lock records the ADR-0026 dual ancestry (NHPN backbone + NHS
centerlines, each with role and pin), per-record `YEAR`/`VERSION`/`UPDATE_DAT`
(all fill records are vintage 2020), the source policy
(`nhs_role: supplementary_centerlines_only`, `nhpn_remains_route_authority`,
no lane geometry, no authoritative distance, `conflation_performed: false`),
and a `chain_connectivity` section: anchor-to-anchor connectivity of each
unconnected segment once every locked fill bridges its pinned break ends
(each fill endpoint must land on a locked chain-end node within the unchanged
1 m tolerance). `validate-continental-nhs-fills` validates all of it
cache-independent, and `scripts/validate-continental-route.sh` gained the
stage.

Fill lock SHA-256:
`c552ae0aef9621b0905faf84480cee44538947158e3ff6f513e71c25929015d5`.

### Transfer and edge-path locks — re-derived together

`derive-continental-transfers` against the revised candidate set left **all
12 anchors byte-identical** (coordinates, evidence records, page hashes);
only the input pin and timestamp moved. `derive-continental-edge-paths`
re-solved every segment over base-plus-supplement lines (every derivation and
probe now consumes candidates through one shared loader, so none can disagree
about what the lock contains). Transfer lock `b267282a1d48…`, edge-path lock
`846da2e3727a…`.

### Disposition record — implemented status

`break-disposition.v1.json` moved to
`lock_revision_implemented_sub_items_pending`
(`09c6b79d060e…`): pins updated to the revised artifacts plus the fill lock's
hash, `locks_modified: true`, and the validator now proves implementation
instead of pendingness — every scoped site must be matched by a candidate-lock
supplement with exactly its OBJECTIDs, every `nhs_fill` site by a fill-lock
site, with exact coverage both ways. In the recorded status the already-locked
exclusion now tests the full union (base plus prior supplements), so a future
disposition round cannot re-propose an implemented record.

## Q-034 sub-item outcomes

**Q-034a — resolved and included.** The prescribed directed whole-key
milepost review of S-10 key `000000001001037` (417 records, no sign or state
filter) plus an unfiltered exact-join walk across the void: the S-10 San
Bernardino chain is milepost-contiguous 16.24–17.012 and joins the locked
component-0 start (546553, mp 17.012) at 0.0 m, but the key's milepost space
jumps one source quantum (16.239 → 16.24) across 2,112.6 m of pavement the
key does not carry. That stretch is the signed I-10/US-101 downtown
concurrency: US-101 key `000000010101037` begins (mp 0.0, record 546519)
exactly at the locked Santa Monica Freeway chain end (546512, mp 16.239),
runs milepost-contiguous 0.0–1.28 with exact joins throughout, and meets the
S-10 chain start at 0.0 m at the San Bernardino junction (records
546569/546559). The 23-record set (9 S-10 + 14 US-101) is the unique
exact-join freeway chain between the locked ends; the alternates through the
interchange are I-5/S-60/local-street records that do not carry the signed
I-10 routing. Included as the fourth scoped acquisition; acquiring it
**connected i10-ontario-to-i405 end-to-end in pure NHPN (54.41 mi)**.

**Q-034b — resolved and included.** The 14 m sliver was acquired and
examined: OBJECTID 38597 (S-95 key `MOHAVEVAHW08015`, mp 0–0.015, 14.1 m)
runs exactly from one locked I-40 chain end to the other with 0.0 m endpoint
and line offsets at both — the record's whole extent *is* the gap pavement at
the S-95 terminus. Its neighbour 38596 tees away north (that tee is what the
census's ~88° grading measured). Of the three listed mechanisms, sliver
acquisition is exact and minimal; NHS fill would substitute a supplementary
source where NHPN itself asserts the pavement, and a bounded exception would
author what the source already carries. Included as the fifth scoped
acquisition (the Denver junction-pavement class).

**Q-034c/d — open, mechanism space halved.** A measure review of both
anchors' unfiltered 500 m envelopes: each anchor lies exactly on a locked
record's interior (i78: 433412 Holland Tunnel, 381.157 m from its nearest
endpoint; i80: 431704 I-80, 253.027 m), and **no record — locked or unlocked —
has an endpoint within the 25 m anchor snap limit** (nearest unlocked
endpoints 381.2 m and 266.6 m). Approach-record acquisition therefore cannot
resolve either site; the remaining mechanisms are anchor re-derivation onto a
candidate endpoint (moves a locked ADR-0024 transfer coordinate) or an
edge-split-at-anchor solve semantics, both needing their own reviewed slice.
The findings are recorded on both disposition sites.

## Connectivity: before and after

| Metric | Before | After |
| --- | ---: | ---: |
| Segments with an undirected NHPN path anchor-to-anchor | 6 of 12 | **8 of 12** (+i10 54.41 mi, +i15 174.949 mi) |
| Segments chained end-to-end with locked NHS fills | — | **10 of 12** (+i40, +i70) |
| Continuously locked/chained corridor mileage | 1,773.4 mi | **4,594.5 mi** |

- NHPN-connected (8): i76 185.951, i80-big-springs-to-salt-lake 578.154,
  i15-salt-lake-to-cove-fort 174.949, i81 525.617, i15-cove-fort-to-barstow
  398.4, i15-barstow-to-ontario 72.891, i10 54.41, i405 12.388 mi.
- Chained with fills (2): i40-i81-to-barstow 2,091.83 mi (3,364,630.9 m NHPN
  + 1,854.0 m Big-I fill chord), i70-denver-to-cove-fort 499.94 mi
  (804,256.9 m NHPN + 320.0 m Rifle fill chord). Chain lengths are shortest
  undirected mixed-ancestry chains — fill spans contribute chord length only —
  and are not an authoritative distance or a westbound selection.
- The i15 Payson acquisition alone connected that segment: the 27.3 km
  pairing was fragment isolation (a 0.267-mile fragment embedded in US-6
  pavement beside a continuous mainline), exactly the class the census
  warned about. Its NHS fill is still locked — NHS carries the span with 62
  zero-gap records — for the conflation stage to weigh.
- Not chained (2): i78-holland-tunnel-to-i81 (Delaware River fill locked; the
  only blocker is the Q-034c anchor), i80-new-jersey-to-big-springs (Q-034d
  anchor plus the two un-authored ADR-0018 micro-gap overlays).

## What remains

1. **Q-034c/d**: anchor re-derivation vs edge-split-at-anchor, per the
   mechanism review above (transfer-lock- or solver-affecting).
2. **ADR-0018 micro-gap overlays** (Omaha 1.011 m, Quad Cities 9.190 m):
   authored only through the reconstruction gates when that stage exists.
3. **NHPN↔NHS geometry conflation** over the locked fill spans (the fill lock
   records what NHS asserts; nothing is conflated yet).
4. **3DEP product lock** over the chained corridor, then the westbound
   directed edge selection and the runtime layer
   (`src/Cannonball.Core/Routes/Continental/`, `game/World/Continental/`,
   `scripts/run-continental-scenario.sh`).

## Provenance and replay

- Base revision: `63c72f2` (main), branch
  `agent/p0-021-lock-revision-20260831`; macOS 26.7 arm64; uv 0.9.24,
  Python 3.13.11, GeoPandas 1.1.4, NetworkX 3.6.1, PyProj 3.7.2,
  Shapely 2.1.2.
- The NHPN response cache was regenerated from the live service before
  anything else and reproduced the committed candidate lock exactly modulo
  acquisition timestamps (all page and feature hashes identical, union
  identical), and `derive-continental-edge-paths` from that cache reproduced
  the pre-revision edge-path lock's `segments_sha256` — the 6-of-12 baseline
  was re-verified on this machine before the revision.
- Live NHPN metadata: byte-identical to the locked hash (`5150b91e…`). Live
  NHS metadata: byte-identical to the disposition evidence hash
  (`a29f96df…`, Version 2025.08.08, `dataLastEditDate` 1778183346545,
  public-domain declaration verified); the fill acquisition was pinned with
  `--expected-metadata-sha256`.
- Replay: re-running both acquisition commands resumed every page from
  checkpoints (5/5 supplement pages, 5/5 fill site page sets, zero retries)
  and reproduced the revised locks exactly modulo acquisition timestamps;
  the fill lock's `chain_connectivity_sha256` is identical on replay.
  Re-deriving transfers and edge paths reproduced `transfer_nodes_sha256`
  and `segments_sha256` exactly.
- All probe and acquisition responses stay in the ignored
  `.tools/continental/` caches (`nhpn/<hash>/supplementary/`, `nhs-fills/`,
  and the Q-034a/b/c-d analysis caches); nothing continental is committed.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-nhpn --output .tools/continental/route-lock-repro.json
# exit 0: reproduces the pre-revision lock modulo timestamps

uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-nhpn-supplements
# exit 0: 5 sites, 28 records, 15553 unique candidates

uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-transfers data/routes/continental/transfer-node-policy.v1.json
# exit 0: 12 nodes, all anchors identical to the committed lock

uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-edge-paths
# exit 0: 8/12 connected (was 6/12)

uv run --project tools/map_pipeline --frozen cannonball-map \
  acquire-continental-nhs-fills \
  --expected-metadata-sha256 a29f96df0512d0748d0c243cf15867d432439f6df5927d9b9d682e167410c027
# exit 0: 5 fill sites, 2 of 4 unconnected segments chain with fills

./scripts/validate-continental-route.sh
# exit 0: candidate, transfer, edge-path, NHS fill, and disposition
# validation all green against the revised artifacts
```

## Verification

`GODOT_BIN` resolved through `scripts/godot.sh` (official 4.7.1.stable.mono);
`./scripts/check.sh` passed every step: doctor, warning-free dotnet build,
xUnit suite, Ruff, frame-allocation scan, the five-stage continental
validation (candidate, transfer, edge-path, NHS fill, break dispositions),
195 map-pipeline tests (scoped `pytest tools/map_pipeline` — the documented
invocation; the repository-root bare `pytest` collection trap is unchanged),
13 PlayGodot unit tests, and the official-Godot save-writing smoke (80.7 mph
peak, save at 56.4 m, 12.035 ms max chunk build, 1.924 ms max collision
build). Gate summary SHA-256
`9b711bb1b2e4acbc2669db15de136132332e401caba5e9bb740798231ca971f1`; doctor
report SHA-256
`33cb1935e7bc974bbc4cc89452ab1f85a6648768cd2301f08b7df88be56e1dca`.

New unit tests cover the supplement acquisition (history preserved,
checkpoint cache layout, union reconciliation), its drift and relocking
refusals, the route-lock validator's supplement tampering rejections
(predicate, ancestry, duplicate OBJECTIDs), the repository supplements'
exact site-to-OBJECTID map, the NHS fill lock's repository validation and
semantic tampering rejections (measure gap, dual ancestry, missing blockers,
claimed westbound selection), and the disposition validator's implemented
status (fill lock required, unimplemented scoped sites rejected) — all
through fake transports and fabricated payloads in the existing test style.

## Next bounded decision

Resolve Q-034c/d by choosing between anchor re-derivation and an
edge-split-at-anchor solve (the approach-record path is closed by measure),
then take the corridor to the reconstruction inputs: the ADR-0018
reconstruction gates (which unlock the two micro-gap overlays), the NHPN↔NHS
conflation model over the locked fill spans, and the 3DEP product lock over
the 10 chained segments.
