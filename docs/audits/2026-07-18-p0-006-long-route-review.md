# P0-006 deterministic long-route adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `3dadeb13cf99bf177da0d1db8a7d5b656d8f62fd`
- Result: no unresolved actionable finding; local acceptance passed

## Scope

The review traced scenario inputs from the shell front door into the authored
distance fixture, checksum-verified memory source, Godot world streamer,
local-origin rebases, collision windows, save/reconstruction checkpoints,
per-assist physics segments, percentile and memory aggregation, JSON evidence,
and the Linux/Windows CI matrix.

The distance fixture has recursive provenance to the locked representative
corridor package. Its geometry is an automation input, not an assertion that
the source dataset describes a 500-mile road.

## Findings resolved during review

1. The old distance option only repeated verified chunk reads from a
   0.226102-mile fixture. Supplying an evidence path now selects a
   distance-complete route with 65 directed edges, 455 chunks, and 500 actual
   route miles through the real Godot streamer.
2. A large route made by repeating edge IDs cannot form an authoritative
   directed plan. The fixture creates unique stable edges, nodes, chunks,
   lanes, connectors, and exact FlatBuffer payload hashes from a fixed seed.
3. The first three-profile sweep changed and persisted the assist enum but did
   not exercise live vehicle physics. Every profile now completes a
   180-grounded-physics-frame autopilot segment before its full stream sweep.
4. A resumed review checkpoint could reconstruct the exact saved stream and
   then immediately shrink its lookahead during the streamer's ready hook.
   Resume state is now preserved through scene readiness, verified before
   advancement, and refreshed normally on the first process tick.
5. A save point that differed from a chunk midpoint only in floating-point
   residue ran twice. Checkpoints are normalized to micro-meter precision
   before deduplication; the final contract performs exactly nine comparisons.
6. An exception raised from the long-route process callback could leave Godot
   alive until the watchdog fired. The profile now reports the original error
   and exits nonzero immediately.
7. Seam continuity previously had only visual review. Junctions now report
   their pre-bridge endpoint gap, while the fixture independently checks every
   chunk endpoint. Both maxima are included in evidence.
8. A single worst-case build time obscured distribution and memory behavior.
   Evidence now reports sample counts, p50/p95/p99/maximum frame, visual-build,
   and collision-build times plus starting, peak, and growth working set.
9. Review teleports could place the vehicle hundreds of kilometers from the
   local origin. Review placement now applies the same 1,000-meter rebase
   contract before positioning and reports the maximum resulting coordinate.

## Residual boundaries

- The 500-mile route is a deterministic authored systems fixture, not observed
  highway geography and not the representative interchange corpus owned by
  P0-012.
- The full-distance pass is a deterministic chunk-by-chunk sweep, not a
  multi-hour real-time drive. Each assist receives a short live physics segment;
  the ledger's 30-minute keyboard and controller handling sessions remain a
  separate human gate.
- Headless frame timing and process working set are machine- and
  operating-system-specific observations. The protected Linux and Windows
  artifacts are retained separately rather than asserted to be identical.
- The runner requires zero missing chunks, hash failures, road gaps, collision
  misses, and save divergence. It reports memory growth and timing percentiles
  without inventing an unapproved product budget.

## Verification reviewed

- `./scripts/run-scenario.sh --distance-miles 500 --platform current --evidence
  evidence/M1/P0-006.json`: three 500-mile profiles, 455/455 verified chunks,
  64/64 transitions, 1,362 rebases, 884.279-meter maximum local coordinate,
  nine exact runtime resumes, and zero missing chunks, hash failures, road gaps,
  collision misses, or save divergence.
- Accessible, Balanced, and Raw each completed 180 grounded physics frames,
  approximately 38.068 meters of live travel, and zero unsupported frames.
- `./scripts/check.sh`: passed; 54 C# tests, 66 map-pipeline tests, 12 PlayGodot
  unit tests, Ruff, doctor, build, and official Godot 4.7.1 smoke.
- Representative interchange route-choice regression: three plans, 12
  connectors, nine navigation save comparisons, and zero chunk failures.
- `bash -n scripts/run-scenario.sh`, workflow YAML parsing, and
  `git diff --check`: passed.
