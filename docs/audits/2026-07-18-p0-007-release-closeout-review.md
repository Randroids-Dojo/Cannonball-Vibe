# P0-007 Release Closeout Review

## Outcome

P0-007 satisfies its M1 contract for reproducible, unsigned, fixture-scoped
Linux and Windows exports. Each target was built twice from a clean source
archive with pinned tools and exact Release-mode RID locks. Both pairs were
byte-identical, both packages passed structural verification, and the shipping
PCK contained no PlayGodot resources.

This does not claim public release readiness or representative long-route
content inside the package. P0-006 verifies the separate 500-mile deterministic
route contract.

## Adversarial finding and recovery

The first clean-source closeout run failed before export. Gameplay automation in
the shipping Godot project directly imports `Google.FlatBuffers`, but the root
project did not declare that package. The root lock recorded it transitively
through `Cannonball.Core`, but that did not make its compile API available to
the root project's source files. A populated developer checkout concealed the
defect through stale build state.

The fix declares `Google.FlatBuffers` directly in `Cannonball.csproj` and records
it in the root dependency locks. A second negative condition appeared when the
RID locks were generated without the exact export build properties: they
retained editor-only packages that are absent from a Release export restore.
The Linux and Windows locks were therefore regenerated with `Configuration` set
to `Release` and the corresponding `GodotTargetPlatform`.

The clean exporter then completed twice for each target:

| Target | Reproducible archive SHA-256 | Result |
| --- | --- | --- |
| Linux x86_64 | `6e3a97a193ca264f95bddd1a320e85490d8d2d3c646781e8f1f88e268c7bc748` | passed |
| Windows x86_64 | `d64ab6dfce649a0882bb9afd5bc1aef3e0a1a4fa6f1b1ebd0956a10e218b81a7` | passed |

Both manifests identify source revision
`606f8eeba201292dee9660425e21551ffcd638c1`, Godot
`4.7.1.stable.mono.official.a13da4feb`, .NET SDK `10.0.102`, runtime
`8.0.29`, Node `22.22.1`, Python `3.13.11`, and locked restore mode.

## Review checks

- Clean source archives cannot borrow untracked build products or dependency
  caches from the working checkout.
- The root project now owns every package it imports directly.
- RID lockfiles describe the exact Release export restore, not an editor build.
- Archive names are content-addressed and both same-builder rebuilds are
  byte-identical.
- Package manifests, checksums, SBOMs, source revision, tool versions, content
  root, and chunk hashes are present and verified.
- PCK inspection reports five resources and zero PlayGodot resources.
- Fixture-only and unsigned status remain explicit in the manifest and release
  documentation.

No unresolved actionable finding remains from the local adversarial review.
Protected remote export and clean-machine smoke results are recorded in
`evidence/M1/P0-007.json` and will be refreshed after the completion pull
request finishes.
