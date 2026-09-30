# Revision21 original fascia and fender surface construction

The front cap now has a shallow 3.457 m vertical roll about Z 0.550 m, joined to the
existing original plan wrap at Y 2.400 m. Three internal radial rings at 25/50/75%
provide the evaluated surface for openings. A C2 fade starts at Y 2.230 m behind
the closed front face. The weighted upper perimeter uses a real 18 mm native
Bevel OFFSET with three segments; it is not a constant-radius certificate.
Only stations with identical native float32 Y encodings are deduplicated.

A finite C2 shoulder correction has a maximum 0.53125 mm height change and keeps
its endpoints and their first two derivatives. It resolves the measured small
nonmonotone dip without changing width or the engineering envelope.

The retained cap and its shared bevel corners receive the analytic field of
that original surface. Two separately identified side endpoints retain their
actual side-plane normals. The final front fenders recover the native field of
the wholly owned original body faces before Boolean cutting. The same-vertex
fan extension preserves existing sharp corner groups. Whole-face ownership is
bounded by 1 micrometer, corner lookup by 2 micrometers, and decoded native normal encoding by 0.025
degrees. Actual source13 rendered seam highlights are smooth under the same
cameras and lights; both root and independent runtime QA inspected the originals.

The attribute pipeline preserves the original FACE INT cap tag and native face
strength through triangle freezing. A diagonal flip cannot cross either value.
No arbitrary face indices or reports-only reference file are shipping inputs;
each construction captures its own actual precut native reference.

The research and human rights boundary remains unchanged: these are original
fictional design decisions, with measured modeling errors separate from factory
reference uncertainty. Wheel, occupant, light, opening and camera hardpoints,
geometry/material ceilings and gameplay physics stay unchanged. Rear wheelhouse,
floor/driveline and internal seat assembly repairs remain outside this lock.
Full regenerated LODs, complete source checks, byte-identical exports, clean
Godot import, runtime/platform/performance and human reviews are still required.
