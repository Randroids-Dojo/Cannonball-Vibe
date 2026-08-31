# Lane topology, corner refinement, and the deferred design gates

Date: 2026-08-31

Task: P0-021. Executes the first half of the slice the
[junction geometry audit](2026-08-31-junction-geometry.md) prescribed: the
ADR-0011 lane model over the locked westbound carriageway and
junction-transfer model, the speed-designed corner refinements the
carriageway, junction, and endpoint-connector locks deferred, the ADR-0013
transition design, the eased vertical-curvature census, and the authored
grade separations — the deferred ADR-0018 design gates this stage owns.
Collision ribbons, chunking, and the ADR-0019 package build are the
recorded next slice (their gates stay deferred with reasons).

Status: **lane topology locked.**
`derive-continental-lane-topology` →
`data/routes/continental/lane-topology-lock.v1.json` (337 KB,
self-contained refinement geometry), validated cache-independently by
`validate-continental-lane-topology` as the fifteenth
`scripts/validate-continental-route.sh` stage. **257 of 257 gates passed**
across 31 corner refinements, 12 segment lane plans, 12 movement lane
models, 2 shared-pavement measurements, and the census and
grade-separation coverage gates.

## The lane-default census: zero locked miles, all defaults recorded

The derive censuses every cached NHPN candidate page (46 distinct fields
over 17,545 features, pinned by the candidate lock's canonical page
hashes): **the locked schema carries no lane-count attribute** (checked
against LANES, LANE_QTY, NUM_LANES, THROUGH_LA, THROUGH_LANES,
THRU_LANES; a hit would refuse — the default may not shadow locked
attribution). Zero corridor miles therefore carry locked lane
attribution, and the entire lane model is the recorded authored default
per ADR-0014 roadway kind, never claimed as observed lane geometry:

| Roadway kind | Extent | Default |
| --- | --- | --- |
| `divided_carriageway` | 6,294.223 westbound mi | 2 general lanes x 12 ft, 10 ft right / 4 ft left shoulder, 70 mph design speed (AASHTO Interstate standard cross-section) |
| `one_way_ramp` | 4,983.4 m through transfers + 102.9 m turnarounds | 1 lane x 16 ft (AASHTO single-lane ramp traveled way) |
| `unclassified` | 53,634.0 m authored connectors | 1 travel lane x 12 ft, no shoulder claim, no reciprocal pair (endpoint lock's standing reason) |

Lane index 0 is the leftmost (median-adjacent) lane; stable lane IDs
carry ADR-0013 lane identity across sections. The eastbound carriageway
mirrors the westbound model through the carriageway lock's reciprocal
pairing rule.

## Lane sections and ADR-0013 transitions

23 sections tile the 12 segments' traveled spans exactly, with 9
speed-designed transitions — every mainline lane add, drop, and
auxiliary taper carries the MUTCD 3B.12 high-speed length
L = W x S = 12 ft x 70 mph = 840 ft = 256.032 m with a linearly
interpolated controlled edge, and auxiliary lanes run 300 m at full
width (an authored default inside the AASHTO deceleration/acceleration
class, recorded as such):

- **Big Springs fork** (`i80-nj` → I-76 canonical / I-80 northern): the
  arriving segment gains a right-side `exit_only` auxiliary lane (taper
  then full width) ending at the exit gore — the refined ramp curve's
  entry seam, station 150.0 in the movement frame, side derived from the
  locked geometry. The fork ramp shares its head with the through
  movement (measured shared-pavement deviation 0.000 m against the 1 m
  bound) and expands 1→2 on `i80-big-springs-to-salt-lake` through the
  designed taper.
- **Cove Fort merge** (I-70 canonical into the I-15 trunk): `i70` drops
  2→1 before its movement window, rides the refined corner as a single
  ramp lane, and merges at the entrance gore (station 275.0, left side —
  the real I-70 W → I-15 S movement joins from the left) into a
  left-side `entrance_only` auxiliary on `i15-cove-fort-to-barstow`
  (full width then end taper). Shared-pavement deviation 0.000 m.
- **Turnarounds** (Barstow, Salt Lake City): the approach drops its
  right lane through the designed taper ending at the loop entry; the
  loop attaches on the median side to lane 0. `i15-salt-lake-to-cove-fort`
  (fed only by the loop) adds its right lane back through the designed
  taper; `i15-barstow-to-ontario` (also fed by the southern through
  movement) keeps two lanes from station 0 and the loop connects to
  lane 0 — one physical model consistent for every path.
- **Endpoints**: `i80-nj` begins as one lane at the Lincoln-approach
  connector seam and gains its second lane through the designed taper;
  `i405` mirrors that into the Redondo connector. The two portal
  terminals are the only open lane boundaries besides the recorded
  `i78-holland-tunnel-to-i81` head seam, which stays open until the
  Holland Tunnel connector is authored.

44 explicit lane connectors tie every seam (movement entries and exits,
the two gores, the loop attachments, the two endpoint attachments); the
validator rebuilds the entire plan from the committed locks and requires
record-for-record reproduction, so every lane boundary interior to the
traveled graph is connected by construction.

## Corner refinements: 31 sites, every recorded exception adjudicated

Every corner-class exception site the upstream locks recorded is now
either refined or dispositioned — none is silently ignored. The refined
corner is the sine-eased heading curve theta(u) = h_entry +
turn x (u − sin(2 pi u)/(2 pi)) whose arc length L = 2|turn|R pins peak
curvature at exactly 1/R for the achieved class radius, spliced between
straight tangent legs solved so the path closes exactly onto the seam
poses (closure ≤ 0.01 m; measured 0.000 m everywhere). Design classes carry the
AASHTO minimum radii at e_max 6 %: directional_80 (80 km/h, 252 m),
ramp_50 (50 km/h, 79 m), street_30 (30 km/h, 21 m); route and junction
corners take directional_80 at or below a 50 degree total turn and
ramp_50 above it, connector corners take street_30.

- **31 refinements**: 18 carriageway-chain sites (the route corners and
  the overlay corner), 4 junction-movement corners, 9 connector corners;
  by achieved class 6 directional_80, 14 ramp_50, 11 street_30.
- **7 gates per site** (plus the opposing re-measure on movement hosts):
  design radius, class floor, tangent fit, closure, lens discipline,
  heading monotonicity, and refinement departure (two-way, bounded by
  the catalog-documented ~80 m NHPN class; worst measured 74.4 m at the
  78.8 degree `i10-ontario-to-i405` route corner, and 38.1 m among the
  movement corners at Ontario's 90.7 degree transfer).
- **3 recorded step-downs**, each machine-verifiable: Big Springs' fork
  corner steps directional_80 → ramp_50 (the 356 m directional curve
  cannot fit the bounded 500 m movement window outside the 25 m seam
  lenses); West LA steps ramp_50 → street_30 (its 113.5 degree corner
  inside the zigzag-excised 485.8 m movement hosts no 50 km/h curve);
  Cove Fort steps directional_80 → street_30 — the ramp_50 candidate
  fit, but its deeper corner cut approached the I-70 eastbound
  carriageway at 6.2 m plan-view, inside the 10 m clearance, so the
  ladder stepped down and the street_30 curve holds 13.77 / 14.86 m.
- **Refined movement re-measure**: each refined movement is re-measured
  against both opposing carriageways over its full spliced geometry.
  West LA still crosses each opposing line exactly once (transversal);
  the other three movements hold ≥ 13.77 m everywhere.
- The 2 `junction_backtrack_approach` corners stay excluded with the
  recorded reason (their doubled travel was superseded by the authored
  turnaround loops).
- Total refined-length effect: −637.622 m across 6,294 corridor miles,
  a recorded fact inside the source fidelity envelope;
  `run_length_effect_claimed` stays false and the published ADR-0024
  figure remains the carriageway lock's record.

### Serpentine exceptions: three sites the locked source cannot refine

Three corner clusters carry mixed-sign flagged lens turns — winding
alignment, not single corners (`i70-denver-to-cove-fort--corner-000`,
turn sum 162.7 degrees with a ~2.9 degree net; `i40-i81-to-barstow`
corners 003 and 004): replacing them with one designed curve would erase
real winding road beyond the fidelity envelope, and the ~80 m-class NHPN
vertices cannot support a speed-designed multi-curve replacement. Each
is recorded as a reduced-design-speed zone at the fastest class its
measured lens geometry supports (all three: street_30 — minimum implied
lens radii 26.3 / 53.8 / 28.7 m), with per-sample signed turns and the
standing disposition: a designed replacement requires an ADR-0026
supplementary geometric source.

## Vertical: the eased profile and its curvature census

The 100 m DEM station quantum cannot adjudicate design vertical curves
(measured pre-easing: 1,449 station pairs above a 7.7 % grade change,
worst 23.9 % — the conditioned profile's standing artifact classes). The
lock therefore defines the deterministic vertical easing the collision
and package stage must sample: a symmetric 9-station (900 m) moving
average over each segment's conditioned profile with both boundary
stations re-pinned exactly (junction and connector seam elevations stand
unchanged; measured boundary deltas 0.000 m). Against the AASHTO metric
rate-of-vertical-curvature minima (crest/sag K = 74/55 at 110 km/h,
26/30 at 80 km/h):

- 101,657 of 101,725 station pairs sit inside the 110 km/h class;
- **68 pairs are recorded 80 km/h-class crest/sag exception sites**
  (per-site station, grade change, and implied K recorded — densest on
  `i81-i78-to-i40` with 20 and the two mountain segments with 15 each);
- zero pairs fall below the 80 km/h class (a below-class pair refuses);
- the easing departs the conditioned profile by at most **13.78 m**
  (bound 16 m), at the recorded 22 % station-scale jitter site on
  `i70-denver-to-cove-fort` — the same non-road artifact class the
  conditioning audit characterised.

## Authored grade separations

The refined West LA transfer's two transversal opposing-carriageway
crossings each carry an authored ADR-0018 grade-separation record: the
transfer passes over the opposing carriageway with at least the 16.5 ft
(5.03 m) standard freeway vertical clearance — no locked source asserts
interchange vertical geometry, so the declaration is recorded as
authored, and the collision stage must build the two levels at least
that far apart. This resolves the junction lock's deferred
`grade_separation_vertical_resolution` gate as an authored record; the
coverage gate requires exactly one declaration per recorded crossing.

## Gate disposition of the deferred battery

| Deferred gate (carriageway/junction/connector locks) | Disposition here |
| --- | --- |
| curvature_design_radius | Adjudicated: every recorded exception site refined at its achieved class radius (peak curvature pinned at 1/R) or dispositioned (serpentine zones, excluded backtracks); between sites the 20 degree lens census discipline stands (the standing NHPN-noise reason). |
| curvature_rate | Adjudicated by construction: sine-eased profiles enter and leave every refined corner at analytically zero curvature; lens discipline verified on the refined geometry. |
| vertical_curvature | Adjudicated over the eased profile: 110 km/h class everywhere except 68 recorded 80 km/h-class sites; zero below class. |
| grade_separation_vertical_resolution | Resolved as two authored clearance declarations at the recorded crossings. |
| lane_connection | Adjudicated: the full traveled graph's lane boundaries connect through 44 explicit connectors; the only open boundaries are the two portal terminals and the recorded Holland Tunnel head seam. |
| drivability | Adjudicated at the design level: every transition carries its MUTCD speed-designed length, every refined corner its class radius and design speed, every movement its recorded design speed. |
| sightline, clearance, collision | **Still deferred** to the collision/package stage with reasons recorded in the lock (they need the generated 3D ribbons; the authored grade-separation clearances are that stage's input). |
| endpoint connector grade/vertical/separation | **Still deferred** with the endpoint lock's standing reason (service-bubble build at the package stage). |

## Validation and tamper resistance

`validate-continental-lane-topology` is cache-independent: it
revalidates the full upstream battery (through the junction validator),
pins all sixteen input hashes, reconstructs every refinement exactly
from its recorded seam poses (and recomputes the poses, departures, and
lens measurements from the committed host geometry for movement and
connector hosts), recomputes the eased vertical census from the
committed profile locks, rebuilds the entire lane plan and requires
record-for-record reproduction, and reproduces the census, grade
separations, gates, digests, and summary. Chain-host seam poses and
departures, the movement opposing re-measures, and the NHPN field
census are recorded derive-time facts held to the locked thresholds,
pinned through the carriageway lock hash and the derive's cache and
census refusals.

## Cross-platform determinism correction (same day)

The first derivation of this lock passed every local macOS gate and was
**rejected identically by both required M0 platforms** (run 33415657230,
ubuntu and windows): `Lane refinement
'nyc-start-to-i80--corner-000--refinement' seam poses do not reproduce
from the committed host geometry`, with the tamper battery cascading
into the same refusal.

Root cause, confirmed: the endpoint connectors were the only refinement
host whose line the validator rebuilt from a **live PROJ projection**
(authored lon/lat waypoints → EPSG:5070) without quantization, then
compared 9-decimal seam headings exactly. PROJ's trigonometric
projection differs across platform libms in its final ULPs (~1e-9 to
1e-7 m per coordinate); over the 25 m heading lens that amplifies to up
to ~3e-7 degrees — hundreds of times the 5e-10 comparison quantum — so
the poses recorded on one platform cannot reproduce on another. The
diagnosis is corroborated in the negative: the 18 chain-host and 4
movement-host records, whose host geometry is millimetre-quantized in
the cache and the junction lock, reproduced exactly on both CI
platforms, including the full 2048-step eased-curve reconstructions;
only the first pyproj-rebuilt connector host failed.

Fix (representation, not tolerance): `_lane_connector_line` now
quantizes the projected waypoints to the millimetre **before any
derived quantity is measured, at derive and validate alike** — exactly
how every other host geometry in the corpus is stored. On identical
quantized inputs, interpolation and distance are IEEE arithmetic and
libm atan2's final-ULP spread (~1e-14 degrees) sits four orders below
the recorded heading quantum, so exact comparison is platform-stable by
construction; no epsilon was widened. The re-derived lock changes only
the nine connector-host refinements (headings by ≤ 5.4e-4 degrees,
coordinates and departures by ≤ 1 mm, total refined-length effect
−637.623 → −637.622 m); every gate, count, and census is unchanged, and
replay remains identical modulo `derived_at`. The residual class — a
projected waypoint landing within the libm spread of a millimetre
rounding boundary — is the same class the endpoint-connector lock's
full re-derivation validator already carries on CI, and a flip would
surface as a deterministic validation failure, never a silent drift.

Recorded lesson (ADR-0020): the local single-platform gate cannot prove
cross-platform determinism — the macOS run was green while both M0
platforms failed; the required Linux/Windows pair is the authority for
reproducibility claims, and exact-comparison validators must operate
only on quantized stored representations, never on live projection
output.

## Provenance and replay

- Base revision: `7468a08` (main), branch
  `agent/p0-021-lane-collision-package-20260831`, PR #106; macOS 26.7
  arm64; uv 0.9.24, Python 3.13.11, Shapely 2.1.2, PyProj 3.7.2,
  GeoPandas 1.1.4, NetworkX 3.6.1.
- The NHPN, NHS fill, and 3DEP caches carried over from the
  junction-geometry session; before anything else,
  `derive-continental-westbound-carriageway` over them reproduced the
  committed carriageway lock **identically except `derived_at`**,
  rebuilding the carriageway cache whose digests both the junction and
  lane derives refuse without.
- Lane topology lock SHA-256
  `1d64d6cf763fe84b9c60856697e058c568621bf71481e7f4a67583758237aa8f`
  (superseding the first derivation
  `8e8c4c80d61bdb18ad439ebe6acccaa7bcdc33ef6f519ca8599e681b5d532986`,
  rejected by both M0 platforms — see the cross-platform determinism
  correction below).
- Replay: two consecutive `derive-continental-lane-topology` runs
  produce identical locks modulo the top-level `derived_at` (every
  content digest stable).
- Nothing continental is committed beyond the compact lock; the caches
  stay in the ignored `.tools/continental/`; `data/sources/catalog.json`
  and every upstream lock are untouched.

## Commands

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-lane-topology
# exit 0: 23 sections, 9 transitions, 31 corner refinements,
# 44 lane connectors, 68 vertical sites, 257 gates passed

uv run --project tools/map_pipeline --frozen cannonball-map \
  validate-continental-lane-topology \
  data/routes/continental/lane-topology-lock.v1.json
# exit 0: cache-independent full recomputation

./scripts/validate-continental-route.sh
# exit 0: all fifteen stages green
```

## Verification

`ruff` clean; 271 map-pipeline tests pass under the scoped invocation
(`pytest tools/map_pipeline`). New unit tests cover the eased-corner
construction (exact reproduction, pinned peak curvature, and the
degenerate/reversal/fit refusals), the vertical easing (boundary
pinning, crest/sag site recording, and the below-class refusal), the
serpentine cluster classification and zone-class table, the movement
lane-class census on the repository lock, the repository lock's
recorded state, and the validator's semantic-tampering rejections
(failed gate, drifted refinement vertex, drifted seam pose, dropped
refinement, unauthorised step-down, same-sign serpentine, drifted
section, drifted vertical census, dropped lane connector, drifted
census, relaxed grade-separation clearance, drifted summary, drifted
input hash, drifted model, unclaimed source policy).

`GODOT_BIN` resolved to the official 4.7.1.stable.mono editor;
`./scripts/check.sh` passed every step on commit `56ebf70`: doctor,
warning-free dotnet build, 145 xUnit tests, Ruff, frame-allocation
scan, the fifteen-stage continental validation, 271 map-pipeline tests,
13 PlayGodot unit tests, and the official-Godot save-writing smoke
(80.7 mph peak, save at 56.1 m, 11.113 ms max chunk build, 2.290 ms max
collision build). Gate summary SHA-256
`764163518d17601e42abbbb65a132c320d19db1d009a0cfae7dcf30b236ededc`.

## What P0-021 still needs

1. **Collision ribbons, chunking, and the ADR-0019 package build**: the
   collision representation over the refined lane model (with the
   deferred collision/sightline/clearance gates and the declared
   grade-separation clearances), streaming-budget-aware chunking under
   ADR-0023, then the GeoPackage/FlatBuffer package built twice with
   every shipping byte compared and the 64 MB root / 16 MB chunk
   ceilings enforced and recorded.
2. **The Holland Tunnel connector** (`nyc-start-to-i78`) and its
   recorded open lane seam.
3. **Runtime integration**: `src/Cannonball.Core/Routes/Continental/`,
   `src/Cannonball.Core/Content/Continental/`, `game/World/Continental/`,
   `game/Automation/ContinentalRouteScenario.cs`,
   `scripts/run-continental-scenario.sh`.
4. **Double-build reproducibility and traversals** on both platforms.
5. **Human gates**: geographic plausibility and the coast-to-coast drive.

## Next bounded decision

Collision generation and chunking over the locked lane model, then the
ADR-0019 continental package build (GeoPackage audit artifact plus
FlatBuffer index and independently hashable chunks, double-built and
byte-compared, sizes recorded against the ceilings) — the stage that
runs the remaining deferred gates and turns the locked geometry into the
shippable route package the runtime consumes.
