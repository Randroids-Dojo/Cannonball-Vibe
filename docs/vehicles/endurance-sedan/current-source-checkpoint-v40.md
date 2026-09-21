# Current source integration checkpoint

P1-018 remains in progress. This checkpoint adds source-generation support for
the revised front and upper assemblies. Their specification/profile selectors
remain unselected pending physical fit, budget, and final artifact verification.
The installed vehicle is still the previously retained prototype.

The current front uses a continuous guide field across the fascia and fenders,
including the manufactured intake and arch surfaces. The upper stage preserves
the existing moving parents and independently binds the formed backlight and
its complete geometry, UV, normal, and material fields. Source generation records
the actual saved predecessor, requested construction, reopened current source,
and helper bytes. Export validation consumes that same chain.

Three measured lower-detail repairs avoid folded meshes: the two front-door
paint groups retain their evaluated original frames before component reduction,
and the rear-left rubber group uses the existing component simplifier. Final
batching still uses the existing rigid parent. The absent-selector path remains
unchanged.

## Recorded Windows verification

The following local evidence is under `reports/p1-018/finish-branch40/`.
These are diagnostic fixtures, not a completed final vehicle generation.

| Evidence | Result and boundary |
| --- | --- |
| `front-native-chain108.json.gz` | Current front900 source, three panels, 17,442 corners, saved/reopened observations and six corruption checks pass. |
| `front-cost127.json.gz` | All six current front lower panels pass; 6,156 triangles total, with 1,108 original mesh fields unchanged. |
| `front-controls117.json.gz` | Full 37 corruption checks and exact restoration pass on the earlier front874 fixture. |
| `upper-native-chain100.json.gz` | Upper883 source observation, regeneration, and seven corruption checks pass. |
| `upper-bake-shell101.json.gz` | All 28 upper components pass before and after their actual rigid-parent bake. |
| `upper-whole-lower-cost122.json.gz` | All lower indexed shells pass; the whole upper fixture exceeds the triangle budget. |
| `m0-129/summary.json` | All 13 `scripts/check.sh` steps pass: 169 xUnit tests, 345 map tests plus one skip, 216 automation host tests, and the official native probes. |

Blender is 5.1.2 `ec6e62d40fa9`; Godot is official 4.7.1 .NET `a13da4feb`;
.NET SDK is 10.0.102 and uv is 0.9.24. Exact commands, UTC times, input hashes,
exit statuses, and failure/retry logs are retained beside the reports.

Independent QA inspected all 48 actual fixed-camera moving-light front images
in `reports/p1-018/research/upper-junction30-proposal01/front-strip911/`.
The current front softens the earlier jagged lamp-corner reflection and preserves
the visible arch outline. The clustered highlights and enlarged late-sweep lobe
remain subject to full-resolution review; three studio strips contribute to the
reflection. This cropped sequence does not establish whole-vehicle art approval.

## Remaining delivery gates

The measured upper fixture adds 6,866 / 2,476 / 2,754 triangles across LOD0/1/2.
Combining those measured deltas with the current front and the unchanged final
tire replacement predicts 150,412 LOD0 and 206,912 total triangles. Both exceed
the 150,000 / 200,000 limits. This is a composed estimate; a complete corrected
generation remains authoritative. Intermediate ratio trials have not been adopted.

Complete roof skin, reinforcement stock, C-to-backlight clearance, finite gasket
seats, and continuous opening clearance still require corrected combined-source
proof. Native mirror diagnostics also remain incomplete: the corrected camera
pose progressed through three moving stages, then the optical test marker failed
its absolute chromaticity requirement through privacy glass. That failure is
retained; it is not a mirror pass.

Final source generation, deterministic double export, clean import, all required
media, performance runs, and final platform checks follow those corrections.
Human art, rights, usability, and driving/physical-control gates remain pending.
PR #144 stays draft; no source promotion or merge eligibility is asserted here.

## Hosted managed diagnostic

The pushed `6107f01` checkpoint passes Linux and Windows M0, all three
PlayGodot platforms, both deterministic long-route jobs, and the unsigned
exports and packaged smoke jobs. Downloaded sedan asset logs from run
`35592892686` confirm that both platforms stop at the first export because
the installed source lacks its current source-generation binding. Remote main
was refreshed to `827bb146` on 2026-09-21; this branch contains that revision.

The revised optical marker test requires each RGB channel to independently
decode the same six-bit pattern. It keeps the existing component, visibility,
pose, and pixel-error guards. Both private builds and 213 source/Python checks
pass, but local Windows Application Control denies loading the test assembly
before any managed cases execute. Those checks are not a managed or native pass.

Scope139 adds a separate, path-limited diagnostic workflow and an immutable
source recipe at `tools/vehicles/diagnostics/p1-018-optical12.zip`. Windows and
Linux runners build the exact sources and execute the existing helper's 66
cases and 100 assertions. Root and independent QA verified all 123 archive
members, 122 manifest inputs, and 112 base Git blobs before publication.
The workflow records its actual runner, revision, commands, and assembly hashes.
Its result does not resolve local Windows trust or establish final rendering,
mirror usefulness, or performance. Existing required workflows and merge gates
are unchanged.

The full Windows `scripts/check.sh` front door passed again after this scoped
workflow addition (`reports/p1-018/finish-branch40/m0-144/summary.json`, all
13 steps). This verifies the current canonical project; the private compiled
helper still needs its own hosted execution result.

Scope146 separately permits a bounded correction to the two lower stamped-C
inner bands, where complete finite footprints measured original stock below
1.2 mm. The exterior, fixed boundaries, topology, and physical tolerances stay
fixed. This correction and the new distant-lid budget trials remain unpromoted.
