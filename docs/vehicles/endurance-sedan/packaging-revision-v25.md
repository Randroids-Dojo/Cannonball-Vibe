# P1-018 packaging revision25: distant brake-hat topology

The v24 full09 source passed its LOD0 geometry checks, but its four far brake-hat
meshes each contained three exact self-crossing triangle pairs after ordinary
batch simplification. Their closed edges alone did not establish valid surfaces.

Revision25 applies the existing per-component exact-check fallback to the four
`(LOD2, Wheel_FL/FR/RL/RR, Material_Alloy)` groups. The measured pilot increases
each affected mesh from18 to24 triangles:24 additional lower-LOD triangles in
total. All1299 other native mesh position, topology, corner-normal, UV, parent
and material-name digests match the original. Every final indexed lower-LOD
shell in the repaired pilot passes the independent native checker.

The root-owned pilot and failed predecessor evidence live at
`reports/p1-018/brake-lod25-pilot01/` and `reports/p1-018/source35-full09/qa20/`.
They must be included in the next retained evidence package. The pilot's source
SHA-256 is `d2cd4d3e6f9cda6cd92a9677e741b1af193b2f6e29f1e0ce742213aa683ae439`.

This is a construction correction. Full-detail geometry, brake dimensions,
controls, LOD distances, collision and existing budgets are unchanged. It does
not establish export correspondence, transition quality, runtime performance,
platform completion or human approval. P1-018 remains in progress.
