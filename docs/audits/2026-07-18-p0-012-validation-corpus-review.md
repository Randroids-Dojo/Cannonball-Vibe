# P0-012 representative validation corpus adversarial review

- Review date: 2026-07-19 UTC
- Investigation started: 2026-07-18 UTC
- Reviewed implementation: `ca4e511623d6b059d29d4a34b6f9b6e887819738`
- Result: machine acceptance passed; required geographic-plausibility and
  route-choice-comprehension human gate remains open as Q-025
- Runtime: official Godot 4.7.1 .NET

## Scope and truth boundary

The corpus locks three legal fixtures and one invalid-mutation catalog to the
approved public-domain NHPN/3DEP representative-corridor ancestry. The lane,
interchange, sign, exit, and milepoint semantics are deterministic authored
regression overlays. They are not presented as observed NHPN lane geometry or
regulatory sign plans.

The legal set covers divided highway, two-to-four lane additions and drops,
merge, split, exit, entrance, a grade-separated crossing, parallel
carriageways, concurrency, milepoint changes, and two highway-transfer forms.
Four plans traverse every selected connector: through, diamond exit/entrance,
directional transfer, and semi-directional transfer.

## Findings resolved during review

1. The existing interchange fixture passed a precomputed list of Bézier samples
   into a builder that treated the list as a new cubic and sampled only its
   first four points. The double-sampling distorted ramp endpoints and concealed
   high curvature. The builder now preserves pre-sampled curves, while genuine
   four-control-point edges retain cubic sampling.
2. The diamond entrance's original control points produced a near-cusp after
   the corrected sampling path became visible. The rejoin was lengthened and
   control points were conditioned until the declared grade, curvature, and
   sightline gates passed.
3. The first semi-directional transfer turned too sharply at the gore and left
   the vehicle unsupported. Its entry tangent now aligns with the incoming
   highway, and lane continuity is preserved through a three-lane transfer
   fixture into its receiving highway. The directional-transfer plan observed
   at most one consecutive unsupported physics frame; the later full-plan pass
   measured a maximum of eight on the semi-directional transfer.
4. The aggregate verifier initially requested the undocumented profile name
   `route-context`; the established CLI contract names that profile `signs`.
   The corpus and verifier now use the public CLI spelling and reject a missing
   success marker.
5. Scenario output was not sufficient on its own to establish corpus coverage.
   The checked-in lock now hashes every legal contract, invalid-mutation catalog,
   semantic contract, source fixture, source manifest, and recursive source
   lock. Tests recompute every byte hash and verify ancestry and coverage.
6. CodeRabbit found that the northbound I-25 edge inherited the fixture's eastbound
   fallback direction. The edge now resolves `route-i25-north` to `north` from the
   same route identity used by its markers and milepoint.
7. The semi-directional ramp declared three lanes while only its rightmost lane
   had endpoint connectors. It is now a single connected lane, and its authored
   centerline is offset to preserve exact alignment with the incoming and
   receiving rightmost lanes. The full four-plan traversal remains supported.
8. Grade used three-dimensional sample distance as its denominator. It now uses
   horizontal run, so vertical change cannot dilute the declared grade gate.
9. Sightline validation now traces the driver-eye-to-target elevation ray and
   rejects any candidate whose intervening road surface breaches the clearance
   envelope. Missing or blocked candidates force the aggregate sightline result
   to zero instead of disappearing from the minimum.
10. Runtime geometry gates now load their limits from the checksum-locked
    `legal-interchanges.json` contract, removing a second hardcoded threshold
    authority from `Main.cs` and the fixture validator.
11. Evidence generation now runs and records the full M0 gate, requires every
    declared review capture, records the actual uv version, and reports measured
    zero-retry execution rather than replaying the development-session repair
    narrative. The historical repairs remain here in the audit.
12. Provenance verification now follows every repository-local JSON and GeoJSON
    parent transitively and checks normalized structured records against the
    prohibited ancestry denylist. Every invalid-mutation selector is also
    resolved against its owning Python or C# test source.
13. The ledger now owns the modified open-question register and records Q-025's
    pending status and stable reference explicitly.
14. CodeRabbit suggested giving the semi-directional merge the same 15-meter,
    8 m/s transition as the diamond and directional merge. A direct scenario
    comparison raised unsupported physics frames from the accepted single-digit
    result to 245, so that suggestion was rejected with runtime evidence and the
    established 70-meter, 20 m/s traversal was retained.
15. Elevated review exposed an actual horizontal-alignment defect rather than a
    renderer-only seam. Endpoint snapping moved a final near-duplicate NHPN
    vertex past its predecessor and manufactured a 151.98-degree reversal at a
    continuation boundary. Removing the near-duplicate reduced the worst source
    boundary deflection to 22.237 degrees, but that still left source feature
    cuts as visible angle points. The importer now reconstructs one conditioned
    centerline across the full unbranched corridor before splitting it back into
    semantic edges. This also absorbs a 28.284-meter source sliver that pairwise
    smoothing could not handle correctly. A 50-meter design-guide tolerance
    removes short source doglegs before curve conditioning, matching the civil
    design sequence of choosing the alignment before staking road sections. All
    44 continuation pairs now remain below the locked 1-degree sampled-boundary
    limit; the measured maximum is 0.846 degrees, and runtime chunks share the
    exact alignment tangent. The tightest sampled curve radius is 360.715 meters.
16. The large black bars visible beside otherwise connected road surfaces were
    long shadows from cone-shaped placeholder scenery. Shadow casting is now
    disabled only for those placeholders, and the runtime review-geometry gate
    asserts that setting. Road lighting, collision, and real barrier shadows are
    unchanged.
17. Adversarial review found that imported route samples stored signed heading
    change in the schema's `curvature` field without dividing by sample length.
    The importer now emits curvature in inverse meters using adjacent horizontal
    segments, matching the independent acceptance calculation and the authored
    interchange fixture. A regression test recomputes every curved test sample.

## Horizontal-alignment design basis

The correction follows Federal Highway Administration guidance rather than
treating GIS linework as render-ready road design. FHWA describes road
alignments as tangents connected by curves, requires tangency at curve and
spiral connections, and explicitly says not to provide an angle point at those
locations. FHWA also describes transition spirals as the means of avoiding an
abrupt radius change. Cannonball's deterministic alignment conditioner is not
a civil-engineering certification or a replacement for final surveyed assets;
it is the procedural-game equivalent: one smooth corridor alignment is derived
before source-record boundaries are reintroduced. It does not claim to emit
survey-grade parametric spirals; acceptance is based on sampled tangent and
curvature limits.

- <https://flh.fhwa.dot.gov/resources/design/pddm/Chapter_09.pdf>
- <https://highways.fhwa.dot.gov/safety/speed-management/speed-concepts-informational-guide/chapter-4-engineering-and-technical>
- <https://www.fhwa.dot.gov/bridge/pubs/hif22034.pdf>

## Quantitative result

- 3 legal fixtures, 4 route plans, 14 unique selected connectors, and 2
  highway-transfer forms.
- 8 invalid mutations rejected with actionable expected errors.
- 12 save/resume comparisons across before, inside, and after plan state.
- Maximum absolute grade `0.037581`; maximum absolute curvature `0.065185/m`;
  minimum measured 120-meter-lookahead chord `99.929 m`.
- One grade-separated crossing with `8.000 m` clearance, one parallel
  carriageway pair, zero self-intersections, zero invalid shortcuts, and zero
  chunk failures.
- Variable topology reached 2–4 lanes, four transitions, gore and transition
  collision, six local-origin rebases, and `161.1 mph`.
- The source-backed corridor contains 44 physical continuation pairs. Maximum
  sampled boundary deflection is `0.846 degrees` against the locked `1-degree`
  limit, down from the original `151.98-degree` reversal. The minimum sampled
  alignment radius is `360.715 m`.
- Route context produced four mile markers, one exit sign, two transfer signs,
  two concurrent markers, four distinct mile values, and seven stable
  automation nodes.
- The corrected single-lane semi-directional ramp completed with eight maximum
  consecutive unsupported physics frames, below the declared 30-frame render
  integrity boundary; the rejected tight-transition experiment produced 245.

## Visual candidate

The tracked [contact sheet](../images/p0-012-validation-corpus-review.png)
contains six elevated topology checkpoints followed by six frames sampled from
the four-plan driving capture.

| Artifact | SHA-256 |
| --- | --- |
| `/tmp/p0-012-topology-review.avi` | `a970770d77beba46ad6a52fb4f8b4cfacc916d314b71eb1246374bf091ca654c` |
| `/tmp/p0-012-route-choice-driving.avi` | `2c97d46678f237082509c240226634c221c92ac34a07a175d5fc7f053fdb930e` |
| `docs/images/p0-012-validation-corpus-review.png` | `575f3006c63b0f49fc69e832cf2ba7c4a4e9f862e990d1abd45b317233d85004` |

## Remaining boundary

The owner must choose Q-025 before P0-012 becomes `complete`. Until then this
work is a machine-verified review candidate and P0-013 remains dependency
blocked. Production terrain, exact observed lane placement, final sign quality,
traffic, vehicle art, and release rights remain separate tasks and gates.

## Verification reviewed

- `GODOT_BIN=/Users/randroid/Documents/Dev/Cannonball-Vibe/.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot ./scripts/validate-route-topology.sh --all-fixtures --evidence evidence/M2/P0-012.json`
- `./scripts/capture-scenario.sh /tmp/p0-012-topology-review.avi --fixture variable-lanes --topology-review`
- `CANNONBALL_CAPTURE_FRAMES=7200 ./scripts/capture-scenario.sh /tmp/p0-012-route-choice-driving.avi --fixture representative-interchanges --route-choice-profile`
- `GODOT_BIN=/Users/randroid/Documents/Dev/Cannonball-Vibe/.tools/godot-4.7.1/Godot_mono.app/Contents/MacOS/Godot ./scripts/check.sh`
- `git diff --check`
