# Meridian S8R packaging revision14

2026-09-11. This original local fit revision preserves revision13 and its actual
failed static-interface reports. Global dimensions, fuel capacities, mass,
ground clearance, suspension/contact/camera anchors and gameplay policies stay
fixed. The 150,000/200,000 triangle ceilings and numerical guards are unchanged.

Native source31 inspection found approximately1.11945 liters of solid intrusion
between each cabin undertray and the body floor. These are corrected with real
fitted recesses. Each tray retains center X=`side*.446`, Y=`-.271`, XY size
`.386 x 1.72` meters and1 mm bevel. Its top lowers0.1 mm to Z`.1399`; the bottom
stays at Z`.1350`, giving center`.13745` and thickness`.0049` meters.

After existing front-floor and A-pillar operations, validate and freeze the
actual evaluated body loop triangles with their original corner normals, UVs
and materials. Subtract left then right box pockets centered
`(side*.446,-.271,.0212)`, size`(.389,1.723,.2424)` meters. Their ceiling is
Z`.1424`, giving1.5 mm perimeter and2.5 mm overhead clearance. Protect original
vertices while applying the existing bounded new-sliver cleanup; coat new cut
faces with the body material. This adds no broad normal recalculation or bevel.

Four separately editable12 mm-square mounting pads per side span
Z`.1399.. .1424`, at absolute X/Y`(.628,-.90)`, `(.628,-.20)`, `(.35,.45)` and
`(.56,.45)` meters. They use trim material and LOD0 only. Each complete lower
face seats on the tray and upper face on the actual recess. Only these sixteen
finite planar interfaces permit contact. Complete footprint and initial
containment checks reject intrusion; no body-wide exception is allowed.

Eight additional small corrections retain their existing topology:

- Both top tank straps move up0.1 mm, center Z`.7041`; their dimensions and
  the individually bounded strap-return welds stay fixed.
- Only each trunk offset arm's terminal center lowers1.2 mm. Its formula is
  `closure_z(...)-.0114`; the fixed centers, terminal Y,9 mm tube radius,
  eight sides and5.3 mm bearing bore stay fixed. The arm still joins the lid hem.
- The vent bulkhead union outer radius changes10 to9.7 mm, retaining8 mm inner
  radius, endpoints and12 sides. Its wall is1.7 mm. The flange and body passage
  retain their geometry.
- Only the rear mirror screen shifts source Y by`-.0001` meters. Its housing,
  camera, stalk, mount and semantic anchor stay fixed.

The roof reinforcement is a specific formed welded flange within the skin,
not a zero-volume seat. Its complete native intersection must remain within
`|X| .592.. .741`, `Y -1.230.. .100` and between actual evaluated inner and outer
roof facets. On source31, the measured intersection is13.990/7.798 mL left/right,
maximum penetration from the inner skin is0.602298/0.458956 mm and remaining
outer thickness is at least0.599820/0.742814 mm. These are observed candidate
measurements. The declared final limits are at most0.65 mm penetration and at
least0.55 mm remaining outer skin, with the existing1 micrometer encoding guard.
There must be no visible outer protrusion. Final shading review is separate.

The main-tank crossover bridge's two butt seats remain on nominal X`+/-.100`,
with9 mm-radius cap footprints centered at Y`-.745`, Z`.421`. Actual complete
meshes occupy opposing halfspaces and the coplanar10-gon caps contact over
232.081 mm2. This declares only the two finite seats. It does not simulate fuel
transfer or allow arbitrary plumbing intersections.

Research candidate03 covers12,055 tray/pad-versus-all pairs and all sixteen
pad footprints, including a deliberately intruding negative control. Its
composed LOD0 count is149,880, an increase of168 triangles. The source writer
must rebuild and verify this count, every LOD, all motion domains, normals,
export correspondence and actual views. These component results do not accept
the final asset. Recipes, immutable hashes and failed attempts are retained in
`reports/p1-018/research/static-fit-31/HANDOFF-candidate03.md`; independent QA
records remain under`reports/p1-018/qa/`. Human gates remain open.
