# Revision 23 distance detail and brake mesh repair

This source construction lock adopts the independently reviewed 22 component
omissions at LOD1 and LOD2, and the existing per-component simplification method
for the two far front-wheel metal groups. The exact names are locked in
`specification.json` under `original_packaging.distance_lod_revision23`.
All LOD0 components remain available for cockpit and opening inspection. Runtime
transition distances remain 28 m and 65 m; neither geometry ceiling changes.

The saved candidate is `reports/p1-018/lod-budget35-pilot02/source.blend`,
SHA-256 `5194381886b52fcbf0288f22823e7dbd8900f6835077f55da03a569f67b0b4e6`.
The frozen independent report is
`reports/p1-018/runtime/lod-budget35-validation01/review.json`, SHA-256
`2d315ba03074ca7697f599936b685313f439a486e92da1ff7272749dc3009fd8`.
The review binds 236 retained local files and all three trial source hashes.
These reports must be included in the next retained delivery evidence archive.

The original and first omission trial both had 13 self-intersection pairs in
the far front brake faces. Applying the established per-component method at
the unchanged 0.065 ratio repairs those two semantic groups. They contain 46
triangles each. All 208 lower-LOD batches and their 804 indexed shells pass
the native self, closed-mesh and raw-normal checks. Cross-shell assembly
contacts remain a separate domain: 45,439 broad-phase candidates are not
certified by the indexed-shell test.

The saved candidate contains 146,444 / 30,664 / 17,640 triangles, plus 24
collision triangles: 194,772 total and 24 production materials. Its 1,093
LOD0 meshes retain exact raw geometry. Complete omission accounting identifies
44 removed shells, 791 retained exact shell geometries and 13 retained shells
retessellated by whole-batch simplification. The latter are mirror stalks,
window belts, the LOD1 headliner and rear center belt. Their largest bounding
box endpoint change is 5.754 mm; that is not a surface-distance bound.

The independent reviewer inspected all 12 corrected 2560 by 1440 neutral
renders at 28 m and 65 m with a 45 degree vertical field of view, finding no
conspicuous new silhouette or reflection loss. Native replay verifies the
actual visible mesh lists and camera metadata. Earlier renderer failures and
source-preview glyph leakage remain recorded with their corrected retries.

This permits constructing the next review source. It does not accept the
shipping asset or close the original trial's required native transition,
cockpit and opening checks. Those checks run on the final exported asset
before delivery acceptance. Source regeneration, remaining assembly repairs,
export correspondence, reproducibility, performance, platform evidence and
human approvals remain open. No historical source or failed trial is replaced.
