# Revision 24 primitive detail allocation

This construction lock adopts 90 independently measured component changes:
two fan-shroud paths use 24 stations, 36 hinge sleeves use eight radial sides,
four brake hats use 24 divisions, 12 caliper pieces use one segment on their
existing 2 mm edge bevel, and 36 cooling fins retain 0.7 mm long-edge chamfers
with flat octagonal end caps. Nominal radii, profiles, mechanical pivots,
materials and all geometry ceilings stay fixed. The measured LOD0 saving is
3,616 triangles. The exact parameters are in `primitive_detail_revision24`.

Root and independent QA inspected actual matched 2560 by 1440 wheel, engine,
hood-hinge, trunk-hinge and open-door frames. The separate turbo reduction
has a visible polygonal contour, so both original 20 by 10 housings remain.
The rejected 272-triangle saving is excluded from the adopted total. The
fitted-grille comparison exposes an existing plain radiator face, recorded
as a separate form/material defect; it does not approve obscured fin detail.

The independent hardware report is
`reports/p1-018/runtime/hardware-budget35-trial01/review.json`, SHA-256
`b2b5061a41db4748d7979550927886839b1fbd5f8dc12cd2aab85defbafc95ab`.
All 88 hardware meshes pass closed-surface, exact-self and raw-unit-normal
checks. The trial checks 84,260 static pairs and certifies 58 nearby opening
pairs plus 19,578 complete-sweep broad-phase exclusions. Continuous pin
clearance is at least 0.157391 mm. Caliper/rim clearance is at least
5.636177 mm. Four inherited fixed hood sleeve/mount proximities remain
explicitly unclassified as exact contact; no blanket assembly exception is
granted. Earlier failed assumptions and negative-harness retries are retained.

The separate shroud/turbo report is
`reports/p1-018/runtime/concealed-budget35-trial01/review.json`, SHA-256
`8178b67c197bf235884a571df030313522baff6b2f232bcb5936895f1ec6476d`.
Only its two shroud reductions, saving 192 triangles, are adopted. Its 30
inherited contacts remain separate from physical assembly approval.

The final root choice and all 12 original image hashes are bound by
`reports/p1-018/hardware-budget35-pilot01/lead-review.json`, SHA-256
`7c2a4adea00527b0883e956b25f6d9fc1b196a5b3b9c6a5b74e65ed2cd297e43`.
The independent ten-image review is SHA-256
`51ffaccc59e8b7de38328162c06495c323aafcec113bff07901bcc5b983ae517`.

This permits constructing a new review source. It does not approve fresh
lower LODs, unrelated assembly contacts, final exports, runtime performance
or human visual/rights/handling/usability gates. The rejected density trial
and unaccepted combined physical/seat pilot remain distinct evidence. No
mechanical, airflow or thermal simulation is added.
