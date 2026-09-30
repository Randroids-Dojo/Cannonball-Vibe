# Revision 22 wheel mesh density

This lock adopts the independently verified wheel trial: 60 radial tire
divisions, 36 rim-barrel divisions and 36 divisions on each friction face.
The previous values were 64, 48 and 48. The original cross-section profiles,
wheel width, rolling radius, brake sizes, pivots, shoulder cuts, materials and
runtime physics parameters remain the construction references.

The exact trial source is `reports/p1-018/wheel-budget35-pilot01/source.blend`,
SHA-256 `beaa44316bc8ac949f8ad62b2835a88ad54b7e7b4e6a5032606e72eadeebf37a`.
The independent aggregate is
`reports/p1-018/runtime/wheel-budget35-validation01/review.json`, SHA-256
`58832d54b6429107a6cbbdd7aabd7f46819be08fcc45dd7b84b02dd27cab3eff`.
Its verified inventory contains 167 files and retains six reviewer/runner
failures and their bounded recoveries. These local reports require retention
with the next deliverable evidence archive.

The actual 16-mesh change saves 2,736 LOD0 triangles. The maximum tire radius is
0.343300043 m and full width is 0.254999995 m. The complete tire/body motion
certificate retains at least 5.000338207 mm clearance after its 1 micrometer
guard; internal caliper clearances also pass. Every changed surface has a
bidirectional conservative comparison bound below 1 mm to the previous mesh.
That comparison is distinct from engineering source uncertainty, exact rolling
radius, sampled nearest distances and ideal-circle faceting error.

All other 1,077 LOD0 meshes retain exact evaluated positions and oriented
topology, with bounded native normal/UV re-evaluation drift. All 16 changed
meshes pass native self/normal/profile checks. The lead and independent agent
inspected the original matched wheel and whole-car renders without observing
conspicuous new loss. The same 52 inherited bead/spoke/hat contact pairs remain
explicitly outside a new blanket mechanical-interface approval.

The surface-only trial does not approve regenerated lower LODs, final export
bytes, native driving transitions or human visual/handling/rights/usability
gates. Those checks still apply to the completed vehicle. The 150,000 LOD0 and
200,000 total triangle ceilings remain unchanged. Small-cabin distance-LOD
omissions and all floor/seat repairs remain separate candidates.

The new specification metadata uses revision 22 to match this lock's label.
The retained v21 checkpoint carried numeric revision 20; its historical bytes
are preserved rather than rewritten.
