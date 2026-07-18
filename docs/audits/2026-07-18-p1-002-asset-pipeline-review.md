# P1-002 deterministic asset-pipeline adversarial review

- Review date: 2026-07-18 UTC
- Reviewed implementation: `72d061627157d5d4ff29baf632bcd117e82b4043`
- Technical result: no unresolved actionable finding
- Promotion result: technical pipeline is ready; the Q-023 human rights-policy gate remains open

## Scope

The review traced the project-original Blender source through source-creation
ancestry, schema-1 manifest validation, two headless glTF exports, invalid-source
rejection, the pinned Godot import, the project-owned wrapper, semantic and
budget inventories, the validation and shipping PCK boundaries, the contact
sheet, Git LFS, documentation, and CI installation of the exact Blender
distribution. It did not treat the graybox fixture as production road art or
approve rights for future assets.

## Findings resolved during review

1. The first Blender script used an obsolete Eevee enum and assumed a default
   preview World. The generator now uses the verified 5.1 API and creates every
   render dependency explicitly.
2. Placing `.blend` source beside the runtime GLB made Godot try to import a
   build-time input and created editor sidecars and lockfile drift. Source art
   now lives under a `.gdignore` data directory, and Godot import, C# publish,
   and release-pack validation run in an isolated copy of the project.
3. Default Godot import settings generated extra LODs and imported animations
   despite explicitly authored LOD nodes and a static fixture. A tracked
   `.glb.import` now disables both behaviors and is checked field-by-field
   against the hash-locked Godot profile.
4. The first manifest validator verified hashes but did not exercise the
   checked-in schema. It now rejects unknown fields and validates manifest,
   authorship, license, artifact, transformation, semantic, and budget shapes
   against the schema identity before checking bytes.
5. Generated inventories originally retained temporary absolute paths. Blender
   inventory paths are now repository-relative or basename-only outside the
   repository, and the durable source, Blender, and Godot inventories are
   checksum-locked in the manifest.
6. The first nonportable-texture mutation created an unused generated image and
   did not survive reload as an external dependency. The mutation now links a
   real absolute-path texture into the material graph, and the linter rejects
   it alongside missing semantic nodes and unapplied transforms.
7. Scale and axis assumptions were implicit in exporter behavior. The glTF
   profile now declares Blender `-Y/+Z` to Godot `-Z/+Y`, the manifest records a
   one-meter unit and exact fixture bounds, and validation compares all three.
8. Merely loading the wrapper did not prove the release boundary. The gate now
   exports a PCK and parses its file table to require the wrapper and imported
   GLB while rejecting Blender source, data manifests, asset tools, test
   automation, encrypted directories, unsupported formats, and malformed path
   tables.
9. Cross-platform renderer bytes can vary even with fixed inputs. The gate
   requires exact repeatability for two renders on the current approved
   platform and keeps the tracked contact sheet hash as a review artifact;
   cross-platform pixel hashes remain diagnostic while semantic and budget
   checks stay authoritative, as required by ADR-0012.
10. The first Linux asset run aborted before rendering because Blender's
    background renderer still loads EGL. The workflow now installs the minimal
    `libegl1` runtime and keeps contact-sheet generation mandatory.
11. Three shared-runner starts varied between 53 and 68 ms against a hard 50 ms
    first-frame threshold, while the same functional gates and an unchanged
    Ubuntu rerun passed. Valid chunks now remain loaded and expose timing
    samples; explicit topology and streaming profiles still enforce their
    declared budgets after collection. The PlayGodot boundary was tightened to
    reject every nonzero normal-start exit instead of carrying a JIT exception.
12. The variable-lane profile exposed a precision drift between the map
    pipeline's one-decimal mile-marker copy and the runtime's three-decimal
    formatter. Runtime marker text now uses the same realistic one-decimal sign
    precision, materially false values still fail closed, and the 45-edge
    topology traversal passes with zero chunk failures.
13. A clean double export exposed nondeterministic node identifiers generated
    while Godot imports a raw glTF scene. The fixture is still pending rights
    review and therefore never belonged in a distributable build. Linux and
    Windows shipping presets now exclude all pipeline fixtures, the shipping
    PCK inspector rejects them, and a dedicated validation preset retains the
    imported GLB and wrapper checks without weakening the release boundary.

## Residual boundaries

- Q-023 must receive project-owner approval before P1-002 or M5 rights policy
  can be marked complete. The fixture manifest therefore remains
  `pending-human-review` even though it is project-original and declares CC0.
- The fixture proves the pipeline with 36 graybox triangles, not the visual
  quality, rig, textures, damage zones, or runtime budgets of P1-008 through
  P1-010.
- A newly saved `.blend` can contain Blender application metadata. The
  checked-in `.blend` is the checksum-locked source of record; deterministic
  promotion begins from that exact source and requires identical derived GLB
  bytes.
- Final art direction, asset rights, target hardware, and visual quality remain
  human gates. Computer Use may supplement those reviews but is not an export
  or promotion dependency.

## Verification reviewed

- Asset gate: two byte-identical GLBs, two byte-identical current-platform
  contact sheets, three invalid-source rejections, five semantic nodes, three
  imported meshes, 36 total triangles, two materials, zero textures, and zero
  build-time dependencies in the nine-file validation PCK.
- Shipping boundary: the distributable PCK contains five files and no pipeline
  fixture; two clean Linux exports produced the identical archive SHA-256
  `ce942ccc41d19aa3224acb0b2db4961bb211c941535bc6e11a16d0e3191b6cc3`.
- Full repository gate: 62 C# tests, 66 map-pipeline tests, 12 PlayGodot unit
  tests, Ruff, doctor, build, and official Godot 4.7.1 smoke passed.
- PlayGodot boundary: normal startup exited zero with no listener, rendezvous,
  or transcript, followed by 16 passing automation tests.
- Variable-lane profile: 45 edges, 12 checkpoints, two-to-four lanes, four
  transitions, entrance and highway-transfer traversal, and zero chunk
  failures; maximum local visual build was 16.283 ms.
- Toolchain: Blender 5.1.2 build `ec6e62d40fa9`, official Linux archive SHA-256
  `aaccb355f50183979b698bcce7467103a76261b5fa59f4972295842662a285fb`,
  and official Godot `4.7.1.stable.mono.official.a13da4feb`.
- `git diff --check`: passed.

Review artifact:
[graybox road-module contact sheet](../../data/assets/pipeline-fixtures/graybox-road-module-contact-sheet.png).
