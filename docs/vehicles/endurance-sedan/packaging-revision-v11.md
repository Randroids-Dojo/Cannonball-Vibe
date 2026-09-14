# Meridian S8R packaging revision 11

2026-09-11. Source23 has valid export geometry and three LODs, a clean official
Godot import, and passing sedan/Hero/graybox functional regressions. It is a
retained inspection candidate. Independent continuous and fixed-joint checks
exposed work that the earlier sampled tests did not establish. Specification10
and all previous evidence remain immutable.

The front folded hinge-arm knee moves 2 mm farther inboard, from an 87 to an
89 mm offset from its pin axis. The sleeve and door attachment endpoints stay
fixed. Continuous source23 witnesses showed 0.9896 and 0.9373 mm clearance near
full opening; the rebuilt arm must clear the unchanged 1 mm requirement.
The four hood/trunk offset-arm bores increase from 5.0 to 5.3 mm radius. Their
12-sided aperture has an inscribed radius above 5.119 mm, giving at least
1.119 mm against the 4 mm pin independently of its angular phase. The separate
4.5 mm bearing sleeve and its declared 0.5 mm radial working clearance remain
unchanged. This prevents applying a bearing exception to unrelated arm geometry.

The A-pillar lower feet need an explicit structural attachment and a shaped
separation from the independently removable front fenders. The upper roof butt
joint does not authorize lower fender penetration. Exact measured source23
witnesses are in `reports/p1-018/qa/production-23/fixed-positive-clearance.json`.

The accepted isolated joint splits each original ribbon at Z=1.05 m. Its lower
foot is joined into the structural body, forming a real upstand; the closed
upper ribbon retains an exact planar butt at that height. The original outer
surfaces and all glazing hardpoints remain fixed. A hull of the original foot
below Z=1.14 m supplies outward supporting planes offset3.5 mm to cut the
removable fender's relief. Actual candidate gaps are3.49819/3.49871 mm, inside
the existing2.5–4.5 mm panel-gap range. All202 front-door poses clear the
unchanged ribbon envelopes, and the planar joint has no positive Z overlap.
The raw candidate costs576 triangles; a tested plane-dissolve optimization is
rejected because it moved the evaluated surface. Rebuilt source verification
must confirm the joint, fender gaps and complete budget.

The new semantic split must also preserve the original exterior corner normals
across the unchanged sheet. Corresponding outer faces within2 micrometers of
their original surface, with aligned face normals, inherit its interpolated
corner normal. Newly created butt faces retain their own normals. The matched
native candidate shows that recalculating all smoothing creates an artificial
transverse stripe; retaining the unchanged surface normals removes it. This
changes shading continuity only and does not authorize geometric overlap.

The original front splitter and two undertray sheets also cross the lower body
and expose jagged outer corners. They need fitted contours and actual recessed
panel seats or body openings. Their corrected assembly must preserve the locked
135 mm clearance, wheel envelope and proper mounting interfaces. The observed
pixel-to-mesh identities and solid containment witnesses are in
`reports/p1-018/qa/front-aero-23/diagnostic.json`.

The accepted isolated floor recipe replaces each rectangular tray with a
stepped and wheel-cut 4 mm panel at Z=0.1355..0.1395 m. Its front outer corner
follows the available flat floor. An actual pocket has 2.5 mm perimeter clearance
and a Z=0.1455 m ceiling; four 12 by 12 by 6 mm spacers per side form individually
measured panel/body mounting faces. The wheel opening remains 64-sided with
448.3 mm panel radius and 445.8 mm pocket radius. Ground clearance stays135 mm.
Only newly introduced Boolean vertices within0.1 micrometer of their adjacent
triangle edge may be dissolved; original vertices are protected, and both
directions of the resulting vertex-to-surface check must remain below that
bound. The candidate has zero invalid triangles, zero unrelated contacts,
16 explicit mounting faces, nonmating gaps at least1.001 mm and166 fewer
triangles. These results require confirmation on the complete rebuilt source.

The splitter is a12 mm lip at Z=0.207..0.219 m, sampled across X=-0.83..0.83 m
at25 stations. Every front/back station follows the actual evaluated fascia;
the front extension tapers from20 mm to zero at the corners and never exceeds
the locked Y=2.4 m nose. The rear face sits10 mm behind the original fascia.
Its explicit recess has2.5 mm edge clearance and a back14 mm behind the fascia;
four separate4 mm supports form eight measured seating interfaces. The isolated
candidate has valid triangles, no unrelated contacts and nonmating gaps above
1.001 mm; its560 added triangles are included in the complete vehicle budget.

The remaining shoulder highlight is a real curvature issue in the original
cross profile. The evaluated and uncut-body normal experiment did not fix it.
A local profile refinement must preserve global dimensions and hardpoints;
the shared pre-cut body surface must continue to position the lamps and hood.
Matched fixed-lighting renders, changed geometry costs and complete rebuilt
fit checks determine acceptance. No geometry or performance budget is raised.

Caliper cheeks and bridges use eight arc segments over their unchanged56-degree
sweep, down from twelve. All end points, inner/outer radii, thicknesses, brake
dimensions and modeled components remain present. The largest219.5 mm radius
has a circular chord error below0.410 mm. Actual evaluated cost and matched
wheel-detail renders must confirm that this bounded reduction preserves the
inspection silhouette while reserving triangles for real body/panel joints.

Unchanged-source light isolation supersedes the earlier interpretation of the
shoulder's two bright bands as a doubled surface reflection: the lower band
comes from the Key emitter and the upper band from TopStrip. Independent QA
found one connected highlight per emitter and no substantive fold in those
crops. The measured C1 curvature variation remains documented, and all rejected
normal/profile trials remain retained. No tested profile change is adopted.
The final full-car lighting and turntable review still applies.

The low-fuel warning moves to the display's unused top strip. Native source21
inspection showed the steering rim hiding the lower half of the original
warning. The runtime's 512 by 192 display places its existing 20 pixel warning
row at Y=0..28; the Blender preview centers its warning at local U=0,
V=0.061 m with the existing 9 mm lettering. Display and eye hardpoints, normal
speed/gear/RPM/fuel positions and warning thresholds stay fixed. Actual fixed-eye
captures must verify readability after this change.

These are original construction refinements. They do not change benchmark
factory claims, vehicle dynamics, the starter/validation speed policies or the
separate required human art, rights, handling and usability reviews.

The first complete revision11 construction (source24) stopped at the LOD gate:
the exact Boolean solver had added null cutter-material slots to new recess
faces. Its failed source, input snapshot and logs are retained. The correction
assigns those new faces the assembly's existing declared coating and rejects
any unexpected real second material. The single-material batching gate is
unchanged; no failed source is promoted.

Source25 then exposed a duplicate evaluated fan triangle in the structural
body after joint cutting. Per-component native validation reproduced it, and
the LOD gate rejected even the unsimplified candidate. The fit operations now
begin with exact evaluated loop triangles and preserve their corner normals,
material indices and all UV layers. This matches the successful isolated
candidate's geometric input and prevents an ambiguous nonplanar n-gon from
being retriangulated by the next Boolean. The topology gate remains strict.
