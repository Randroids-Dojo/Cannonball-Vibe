# Windows workstation readiness audit

Date: 2026-07-19
Task: P0-016
Platform: Windows 10.0.26200 x64 (`MINGW64_NT-10.0-26200`)

## Result

The repository builds, tests, and runs on this Windows workstation. The complete
M0 front door passed from Git Bash, and an additional renderer-backed smoke ran
with the project's Forward+ renderer through Vulkan on an NVIDIA GeForce RTX
3080 Ti.

## Findings and corrections

1. Git for Windows, Git LFS 3.7.1, Bash, and Perl were already installed, but
   the active process had inherited a stale PATH. A fresh Git Bash receives the
   installed tools normally.
2. The pinned .NET SDK 10.0.102, uv 0.9.24, and Godot 4.7.1 .NET editor were
   missing. Exact WinGet packages were installed and the README now documents
   the same setup.
3. A non-administrator WinGet Godot install cannot always create the `godot`
   command alias. `scripts/godot.sh` now discovers the exact console executable
   in WinGet's per-user package directory while retaining the existing
   `GODOT_BIN`, repository-local macOS/Windows, and command-PATH precedence.
4. `SymbolicLinkChunkPathFailsClosed` assumed that Windows granted symbolic-link
   creation. The first complete gate failed while constructing that fixture
   with Win32 error 1314 (`ERROR_PRIVILEGE_NOT_HELD`). The test now treats only
   that specific Windows error as an unavailable fixture; all other I/O errors
   still fail, and systems with the privilege still exercise the production
   symbolic-link rejection.

## Verification

- `./scripts/doctor.sh`: passed with zero failed checks.
- `dotnet build Cannonball.sln --nologo`: passed with zero warnings and zero
  errors.
- `DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --no-build --nologo`:
  72 passed, 0 failed.
- `./scripts/check.sh`: passed all seven steps. Ruff passed; map-pipeline pytest
  passed 78 tests; PlayGodot unit pytest passed 12 tests; the official-engine
  headless smoke loaded four chunks and wrote a save.
- Renderer-backed smoke: exited 0 using Godot 4.7.1 .NET, Vulkan 1.4.329, and
  Forward+. It loaded four packaged chunks, wrote a save, and completed at 72.1
  meters with no reported chunk failure.
- `git diff --check`: passed.

The final structured local reports are under `reports/m0/`. That directory is
intentionally ignored and is recreated by every gate run; durable hashes and
the initial failure/recovery record are preserved in `evidence/M0/P0-016.json`.

## Boundary

This closes local Windows workstation readiness for the M0 slice. It does not
replace the already-required remote Linux/Windows CI, long-route stress,
rendered UI automation, target-hardware performance gates, or human driving-feel
approval belonging to other delivery tasks.
