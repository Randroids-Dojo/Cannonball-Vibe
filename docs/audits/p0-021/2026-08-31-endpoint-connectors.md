# Endpoint connectors, conflated-span replacement, and the portal-to-portal run length

Date: 2026-08-31

Task: P0-021. Executes the slice the
[westbound carriageway model](2026-08-31-westbound-carriageway.md) prescribed:
the authored ADR-0024 endpoint connectors plus the conflated-span replacement
of the three traversed NHS fill chords, through the same gate battery —
culminating in the first published ADR-0024 **portal-to-portal westbound run
length**.

Status: **both landed.** The three traversed fill chords (Big-I, Rifle,
Delaware River) now ride their conflation-lock NHS spans, seam-registered
onto the pinned chord endpoints and conditioned vertically per ADR-0017; the
two ADR-0024 endpoint connectors are authored, evidence-linked ADR-0018
records joining the locked portals to the corridor ends; and the canonical
NY→LA run measures **4,546,552.503 m = 2,825.10 mi** GRS80 geodesic,
portal to portal (East 31st Street portal → Portofino Way portal). The
northern alternative publishes at 2,891.68 mi; the southern figure honestly
stays unpublished until its Holland Tunnel connector is authored.

## Conflated-span replacement

The westbound carriageway lock is revised in place to schema 2
(`derive-continental-westbound-carriageway` →
`data/routes/continental/westbound-carriageway-lock.v1.json`), superseding —
never rewriting — the v1 lock, whose digest and status are recorded verbatim
in the new `supersedes` block
(`4607550702f6042412f99c45e12008a7a5c299c817deb62bb70cf29cde570c5b`).

Mechanism, per traversed fill site:

- **Reassembly with a digest refusal.** The span is reassembled from the
  locked NHS fill cache through the conflation machinery (group records,
  recorded orientations, the exact projected seam measures — the first
  implementation clipped at the lock's 6-decimal rounded measures and was
  **refused by its own digest gate**, standing evidence the gate rejects;
  the recomputed measures must also reproduce the lock's rounded values).
  The mm-rounded reassembled geometry must reproduce the conflation lock's
  `geometry_sha256` exactly.
- **Seam registration, linear in arc length.** The span ends sit up to
  55.755 m laterally from the pinned NHPN break ends (the conflation lock's
  recorded seam offsets — characterised cross-dataset disagreement inside
  the catalog's ~80 m NHPN error class). The span is registered onto the
  chord endpoints by a correction interpolated linearly in arc length; the
  measured endpoint corrections must reproduce the recorded seam offsets
  within 0.02 m (measured agreement delta: **0.000 m at all six seams**),
  so chain joints stay exact and no seam jog or corner is invented.
- **ADR-0017 vertical conditioning.** Span vertical context is the
  conditioned profile over the chord's directed-walk station interval,
  re-parametrised by the span's arc length — a derived deck chord, never
  claimed as observed span elevation. The Delaware span carries its
  characterised `fill_span_terrain` conditioning record as evidence.

### Before/after per span

| Span | Chord (m, plan.) | Span (m) | Registered (m, plan.) | Registered geodesic (m) | Seam offsets from/to (m) | Span grade | Vertical evidence |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| i70 Rifle | 320.000 | 311.435 | 320.002 | 322.754 | 17.422 / 55.755 | +4.479 % | raw profile (no artifact record; real approach grade) |
| i78 Delaware River | 3,021.991 | 3,378.063 | 3,380.841 | 3,399.084 | 16.353 / 14.826 | +1.078 % | `fill_span_terrain` deck chord (conditioning-006) |
| i40 Big-I | 1,854.000 | 1,864.352 | 1,864.356 | 1,879.783 | 0.100 / 0.066 | −0.736 % | raw profile (no artifact record) |

Registered-length change stays inside the seam-correction envelope
(|registered − span| ≤ from + to offsets) at every site; each replacement
carries four passing gates (digest agreement, seam registration,
registration length change, span grade), lifting the battery from 84 to
**96 of 96 gates passed**.

Chain effects, recorded honestly:

- The corridor grows **+369.207 m planimetric** (12-segment westbound
  6,293.994 → **6,294.223 mi**): +0.002 m at Rifle (the registration
  stretches the shorter real span across the fixed chord endpoints),
  +358.850 m at the Delaware River (the real crossing bows), +10.355 m at
  the Big-I.
- **The v1 Delaware "route corner" was a chord artifact.** The v1 corner
  site at the river (peak 29.9°, station 107,550) disappears under real NHS
  road geometry — the i78 heading-gate measurement drops 29.9° → 0.0°, and
  the corner census counts 23 sites (was 24). No `conflated_span_corner`
  class site appears: the spans join the chain without a corner-class turn
  anywhere at the 25 m lens.
- Two i40 corner sites downstream of the Big-I record different peak/sum
  measurements (same coordinates): the +10.355 m upstream length change
  shifts the census's 25 m resampling phase through those curves. The i40
  reversal-excision stations shift by the same +10.355 m.
- The grade gate still adjudicates the conditioned profile (max sustained
  −6.939 % ≤ 7 %); junction backtracks are unchanged (reciprocity 0.000 m).

## Authored endpoint connectors (ADR-0024 / ADR-0018)

`author-continental-endpoint-connectors` →
`data/routes/continental/endpoint-connector-lock.v1.json`, validated by
**full re-derivation** (`validate-continental-endpoint-connectors`, the
thirteenth `scripts/validate-continental-route.sh` stage): the authoring is
a pure function of committed locks plus the authored registry, so a drifted
waypoint, dropped leg, widened envelope, or hand-edited gate cannot
validate.

Each connector joins exactly two **locked** coordinates — the
route-selection public-road portal (census address match; the historical
142 E 31st St and 260 Portofino Way reference addresses stay reference
anchors, never private-property claims) and the directed lock's
corridor-end node at the ADR-0024 anchor. Every metre between them is
**authored** (ADR-0017 authored class, declared ±250 m waypoint fidelity),
each leg justified by the ADR-0024 facility it travels; the travel-ordered
facility sequence must reproduce the route selection's `facility_sequence`
exactly. No locked or probed source geometry exists for these facilities —
the NHPN candidate lock is scoped to the twelve corridor segments — so the
authored-vs-sourced breakdown is: 2 locked endpoints + 0.0 m sourced,
100 % authored between them, recorded per connector.

| Connector | Facilities | Geodesic | Straight-line context | Detour ratio (bound) | Corner sites | Authored waypoints |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| `nyc-start-to-i80` (portal → corridor) | Manhattan connector, Lincoln Tunnel, NJ 495, NJ 3, US 46 | 43,588.805 m = 27.085 mi | 40,181.7 m | 1.085 (≤ 1.25) | 3 | 16 |
| `redondo-access-to-finish` (corridor → portal) | CA 107/Hawthorne Blvd, Torrance Blvd, Catalina Ave, Beryl St, Harbor Dr, Portofino Way | 10,045.233 m = 6.242 mi | 6,024.2 m | 1.667 (≤ 1.8) | 6 | 8 |

- The recomputed portal-to-anchor straight line must reproduce the directed
  lock's recorded context to 0.1 m (both do, exactly).
- Envelope bounds are justified per connector: the NJ corridor parallels
  the straight line (1.25); the Redondo sequence is a right-angle dogleg
  whose taxicab geometry alone measures ~1.57 (1.8).
- Gates per connector: endpoint continuity, heading discipline at the 25 m
  lens (city corners are recorded `connector_corner` sites — peak 98.76°
  turn-sum at the Portofino marina corner; reversal-class turns refuse),
  self-intersection, station monotonicity, length envelope, and
  geodesic-planimetric agreement — **12 of 12 passed**.
- Grade, curvature, sightline, collision, lane, and reciprocal-separation
  gates are recorded deferred with the reason: no locked elevation or lane
  source covers the connector facilities (ADR-0017 keeps unknown unknown),
  and the connectors are ADR-0014 `unclassified` roadway records — the
  undivided portions cannot claim a divided-carriageway pair, so no
  opposing edge is synthesized.
- The southern path's Holland Tunnel connector (`nyc-start-to-i78`) is
  recorded unauthored with its reason; it is not invented here.

## The published run length (ADR-0024)

The revised carriageway lock's `run_length` record composes, per locked
path: the directed lock's anchor-to-anchor corridor figure + the recorded
span refinement + the authored connectors. A path publishes only when every
one of its excluded connectors is authored and gated.

| Path | Corridor anchor-to-anchor | Span refinement | Connectors | **Portal-to-portal** |
| --- | ---: | ---: | ---: | ---: |
| central-rockies (canonical) | 4,492,918.463 m = 2,791.77 mi | +0.002 m (Rifle) | 43,588.805 + 10,045.233 m | **4,546,552.503 m = 2,825.10 mi** |
| northern-plains | 4,600,070.081 m | 0.0 m | same two | 4,653,704.119 m = 2,891.68 mi |
| southern-i40 | 4,691,103.623 m | +361.395 m (Big-I, Delaware) | `nyc-start-to-i78` unauthored | **unpublished**, reason recorded |

- Planimetric analog recorded per path (canonical 4,527,328.088 m).
- The relationship to the 2,791.77 mi anchor-to-anchor figure is recorded
  in the lock: portal-to-portal = anchor-to-anchor + span refinement +
  connectors, every component recorded. The canonical figure includes the
  971.876 m of doubled Barstow junction-approach travel the directed lock
  characterised (note carried verbatim).
- Precision is stated per component: the corridor is locked
  source-centerline fidelity; the ~53.6 km connector contribution carries
  declared authored-waypoint precision and refines when connector source
  geometry is acquired (recorded future refinement, not assumed).
- `source_policy.authoritative_distance_claimed` flips to `true` with an
  explicit scope statement;
  `fill_chords_replaced_by_conflated_spans` and
  `endpoint_connectors_generated` flip to `true`;
  `junction_transfer_geometry_generated` stays `false`.

## Provenance and replay

- Base revision: `f2689e9` (main), branch
  `agent/p0-021-endpoint-connectors-20260831`, PR #104; macOS 26.7 arm64;
  uv 0.9.24, Python 3.13.11, Shapely 2.1.2, PyProj 3.7.2, GeoPandas 1.1.4,
  NetworkX 3.6.1.
- The NHPN response cache (base plus supplements) and the NHS fill cache
  were regenerated from the live services before anything else and
  reproduced the committed candidate and fill locks exactly modulo
  acquisition timestamps; a fresh conflation derive against them reproduced
  the committed conflation lock exactly modulo acquisition timestamps.
- Endpoint connector lock SHA-256
  `2544063bc8494016268aab322ae443c91712ef14087dfa37c41888bac878a2c8`;
  revised westbound carriageway lock SHA-256
  `391b2b811fe68444f4c37958e43e1d0c3068bba2dd59ea6952ce0789687283f7`
  (supersedes v1 `4607550702f6042412f99c45e12008a7a5c299c817deb62bb70cf29cde570c5b`).
- Replay: re-running `author-continental-endpoint-connectors` and
  `derive-continental-westbound-carriageway` to scratch outputs reproduces
  both committed locks **identically except the top-level timestamp**
  (`authored_at` / `derived_at`).
- Nothing continental is committed beyond the two compact locks; the NHPN,
  NHS fill, conflation-margin, and carriageway caches stay in the ignored
  `.tools/continental/`; `data/sources/catalog.json` and every upstream
  lock are untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  author-continental-endpoint-connectors
# exit 0: 2 connectors, 53634.038 m authored, 12 gates passed, 9 corner sites

uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-westbound-carriageway
# exit 0: 12 segments, 12582 elements, 6294.223 westbound miles,
# 3 span replacements, 23 corner sites, run length 2825.1 mi

./scripts/validate-continental-route.sh
# exit 0: all thirteen stages green
```

## Verification

`ruff` clean; 258 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`; the repository-root bare `pytest` collection
trap is unchanged). New unit tests cover the connector corner census
(recording and the reversal refusal), the profile interpolation (terminal
leg included), the conditioned-elevation substitution and its mismatch
refusal, the deck-chord re-parametrisation, the run-length composition
(publish, withhold, and the canonical-must-publish refusal), the
conflated-span corner classification and overlay precedence, both
repository locks' recorded state, and both validators' semantic-tampering
rejections (connector: drifted waypoint, dropped leg, widened envelope,
drifted authored length, dropped unauthored record, summary drift;
carriageway: drifted supersedes, drifted span digest, dropped span
replacement, drifted registered length, drifted vertical context, drifted
run length, span corner without replacement, plus the standing v1 cases).

`GODOT_BIN` resolved to the official 4.7.1.stable.mono editor;
`./scripts/check.sh` passed every step: doctor (dotnet 10.0.102, uv 0.9.24,
git-lfs 3.7.1, official Godot), warning-free dotnet build, 145 xUnit tests,
Ruff, frame-allocation scan, the thirteen-stage continental validation, 258
map-pipeline tests, 13 PlayGodot unit tests, and the official-Godot
save-writing smoke (80.7 mph peak, save at 56.1 m, 12.028 ms max chunk
build, 1.419 ms max collision build). Gate summary SHA-256
`88a43a10a777be0fdeb71337b99f5ff29cf1d45612e5320ad3b6eae5389d1260`.

## What P0-021 still needs

1. **Transfer geometry** at the seven cross-segment junctions and the two
   junction-backtrack turn-arounds.
2. **Lane topology, ramps, and collision** over the carriageway model with
   the deferred ADR-0018 gates, then the GeoPackage/FlatBuffer package
   build (materializing the cached carriageway geometry) under ADR-0019
   budgets.
3. **The Holland Tunnel connector** (`nyc-start-to-i78`), which publishes
   the southern portal-to-portal figure.
4. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`.
5. **Double-build reproducibility and traversals** on both platforms.
6. **Human gates**: geographic plausibility and the coast-to-coast drive.

## Next bounded decision

Junction and transfer geometry: the seven cross-segment junction transfers
and the two backtrack turn-arounds, generated and gated over the carriageway
model — the last route-level geometry before lane topology and collision can
run the deferred gate battery.
