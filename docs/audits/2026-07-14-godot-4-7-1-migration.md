# Godot 4.7.1 migration validation

- Date: 2026-07-14
- Engine: `4.7.1.stable.mono.official.a13da4feb`
- SDK: `Godot.NET.Sdk/4.7.1`
- Platform: macOS Apple Silicon
- Decision: [ADR-0004](../decisions/ADR-0004-godot-4-7-1.md)
- Automation: [ADR-0005](../decisions/ADR-0005-official-engine-agentic-automation.md)

## Result

The M0 prototype migrated from 4.6.3 to 4.7.1 without source changes to Godot
gameplay APIs. Build, unit, content, smoke, all-assist stress, version guards,
workflow lint, shell lint, and renderer-backed visual capture passed.

## Evidence

- Official macOS .NET archive SHA-256:
  `92cac516baa8ddc7756eeaa38a6d007778a968bfbf188db7c5d6e6ec21c5d52c`.
- Godot editor import completed on 4.7.1.
- C# build: zero warnings and zero errors.
- xUnit: 8 passed.
- pytest: 6 passed.
- Ruff, ShellCheck, actionlint, JSON parsing, and whitespace checks passed.
- The exact-version wrapper rejected the installed 4.6.3 editor.
- 4.7.1 headless smoke:
  - save written;
  - approximately 46 m traveled;
  - three chunks loaded;
  - approximately 79 mph peak;
  - clean process exit.
- Balanced stress:
  - 203.6 mph peak;
  - approximately 1.91 km traveled;
  - six chunks loaded;
  - one origin rebase;
  - approximately 245 MB maximum resident memory.
- Accessible stress:
  - 203.6 mph peak;
  - approximately 1.91 km traveled;
  - six chunks loaded;
  - one origin rebase;
  - clean process exit.
- Raw stress:
  - 203.6 mph peak;
  - approximately 1.91 km traveled;
  - six chunks loaded;
  - one origin rebase;
  - clean process exit.
- Renderer-backed Movie Maker capture:
  - 60 frames at 60 FPS;
  - 1280x720 MJPEG plus PCM audio;
  - one-second artifact;
  - completed in approximately one second.

## Shutdown finding and fix

An Accessible stress run printed `CANNONBALL_SMOKE_OK` but did not terminate.
The earlier GitHub 4.6.3 smoke showed the same symptom. The cause was a possible
deadlock when `_ExitTree` synchronously waited for telemetry disposal while
telemetry continuations retained the Godot synchronization context.

Telemetry I/O and disposal now use `ConfigureAwait(false)`. Repeated stress runs
exit cleanly. Scenario scripts also enforce an external 120-second watchdog,
and CI Godot jobs have a 10-minute hard timeout.

## Visual capture finding

Combining `--write-movie` and `--headless` on macOS selected Godot's dummy
renderer and crashed in `texture_2d_get`. The crash handler did not produce a
useful movie. Re-running without `--headless` through the compatibility renderer
produced the expected artifact.

Visual capture is therefore a renderer-backed automation layer. It must not be
conflated with headless simulation or used as the sole semantic test result.

## Remaining limitations

This migration preserves the original short M0 test scale. It does not close
the ledger requirements for 500-mile traversal, exact resume, real route chunks,
exports, physical wheel testing, or human handling approval.
