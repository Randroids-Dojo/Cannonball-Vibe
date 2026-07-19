# P0-012 representative validation corpus adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `6a5cab8c176691901d24ba0c00a76f2a622af443`
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
   fixture into its receiving highway. The final bot pass observed at most one
   unsupported physics frame across all plans.
4. The aggregate verifier initially requested the undocumented profile name
   `route-context`; the established CLI contract names that profile `signs`.
   The corpus and verifier now use the public CLI spelling and reject a missing
   success marker.
5. Scenario output was not sufficient on its own to establish corpus coverage.
   The checked-in lock now hashes every legal contract, invalid-mutation catalog,
   semantic contract, source fixture, source manifest, and recursive source
   lock. Tests recompute every byte hash and verify ancestry and coverage.

## Quantitative result

- 3 legal fixtures, 4 route plans, 14 unique selected connectors, and 2
  highway-transfer forms.
- 8 invalid mutations rejected with actionable expected errors.
- 12 save/resume comparisons across before, inside, and after plan state.
- Maximum absolute grade `0.037555`; maximum absolute curvature `0.065160/m`;
  minimum measured 120-meter-lookahead chord `99.929 m`.
- One grade-separated crossing with `8.000 m` clearance, one parallel
  carriageway pair, zero self-intersections, zero invalid shortcuts, and zero
  chunk failures.
- Variable topology reached 2–4 lanes, four transitions, gore and transition
  collision, six local-origin rebases, and `161.1 mph`.
- Route context produced four mile markers, one exit sign, two transfer signs,
  two concurrent markers, four distinct mile values, and seven stable
  automation nodes.

## Visual candidate

The tracked [contact sheet](../images/p0-012-validation-corpus-review.png)
contains six elevated topology checkpoints followed by six frames sampled from
the four-plan driving capture.

| Artifact | SHA-256 |
| --- | --- |
| `/tmp/p0-012-topology-review.avi` | `74678c83c9100f09af5e77d22615ec6420652e6d61aeb8ddb323aa99f215871f` |
| `/tmp/p0-012-route-choice-driving.avi` | `6e4f9a9ba41a8fa9a1a4695027a80ca19441ebf82ea741ad64d048cd69181134` |
| `docs/images/p0-012-validation-corpus-review.png` | `49a3b417d9dad42f96ee7c3626490f315e21ef837325b459e7a239a5c764bcea` |

## Remaining boundary

The owner must choose Q-025 before P0-012 becomes `complete`. Until then this
work is a machine-verified review candidate and P0-013 remains dependency
blocked. Production terrain, exact observed lane placement, final sign quality,
traffic, vehicle art, and release rights remain separate tasks and gates.

## Verification reviewed

- `./scripts/validate-route-topology.sh --all-fixtures --evidence evidence/M2/P0-012.json`
- `./scripts/capture-scenario.sh /tmp/p0-012-topology-review.avi --fixture variable-lanes --topology-review`
- `CANNONBALL_CAPTURE_FRAMES=7200 ./scripts/capture-scenario.sh /tmp/p0-012-route-choice-driving.avi --fixture representative-interchanges --route-choice-profile`
- `git diff --check`
