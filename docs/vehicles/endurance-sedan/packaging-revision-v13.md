# Meridian S8R packaging revision13

2026-09-11. Revision12 and all failed candidates remain retained. These are
original local construction corrections. Vehicle dimensions, hardpoints,
occupant envelopes, tank capacities, physical mass, steering, suspension and
Starter/HighSpeedValidation policies remain fixed. No geometry budget increases.

Actual rear views expose upper and side cavities around the old projecting
lamp boxes. Every rear optical layer now follows the same pre-cut body Y(X,Z)
surface, sampled from (X,-3,Z) toward +Y. Each aperture is a planar box centered
at (side*.65,-2.4225,.868), size (.423,.320,.127) m. The simple closed cutter
preserves the corrected trunk sill; the earlier nonplanar cutter was rejected
for four open edges and increased geometry cost.

The clear cover and backplate share a .414 by .116 m envelope at Z=.868 m.
Their depths behind the original outer contour are 0/.003 m and .081/.087 m.
Top/bottom walls retain width .418 m, thickness .004 m and centers Z=.928/.808.
Two separately editable side returns per lamp close the frame: width .002 m,
height .116 m, centers X=side*.65 plus/minus .208 m, depth 0/.087 m. Guides and
emitters retain their X/Z layout and use depth .018/.023 m. Actual triangle
measurements rejected smaller inward offsets for crossing or submillimeter
clearance behind the tessellated clear cover.

The upper interior forms downward by
`Znew = Zold - .010*(depth/.087)*clamp((Zold-.868)/.058,0,1)`.
The outward face at depth zero stays unchanged. The 10 mm back-edge relief
clears the unchanged moving trunk hem. Housing/cover use16 X by4 Z intervals;
other surfaces use16 by1, and side returns1 by4. The upper walls use the
17 common cover/backplate X stations plus the two outer margins, giving18
intervals. This removes a real nonplanar seating overlap without increasing
the existing numerical guard. Native v4 internal checks cover231 pairs;
unrelated surfaces have at least1.881516 mm separation. The exact24 frame
seats have separately proved planes, rather than a blanket contact exemption.
Continuous opening and initial containment checks support this recipe; the
complete rebuilt source must independently pass again.

Static packaging inspection also found rigid auxiliary-tank strap returns
crossing the tank and the pump outlet entering its lower corner. The returns
now use Y=-2.171/-1.669 m and bottom Z=.409 m, preserving their8 mm radius,
four-sided section, top Z=.702 and the existing top straps. The6 mm outlet
line runs through (.49,-1.99,.460), (.47,-1.99,.400),
(.401333333,-1.997333333,.364), (.35,-1.99,.210),
(.35,-1.36,.210), (.43,-1.27,.210), in meters. It rejoins the unchanged
floor-gland axis. The pump outlet bore has7.5 mm radius,12 sides and extends
12 mm inward opposite the first line tangent, preventing an internal cap lip.
Tank envelopes, capacities, the pump's nominal outer box dimensions/position,
floor passage, gland and main-tank endpoint remain fixed. The locked
specification's phrase "pump exterior" refers to that nominal envelope; the
changed outlet Boolean may alter evaluated bevel clamping and tessellation.
It does not assert that every exterior pump vertex is unchanged.
Intended strap welds and plumbing endpoints require
individual bounded interface checks. Modeled plumbing does not implement
fluid transfer, electrical pumping or mechanical simulation.

Research's native four-fixture reconstruction matches actual source29 triangle
positions at0.1 micrometer quantization. Its candidate checks4,786 static pairs
and adds92 triangles. The accepted rear recipe saves160 triangles, giving a
provisional combined reduction of68 before full-source LOD generation. Final
counts, export correspondence, normals, visual appearance and motion domains
must be measured from the new checkpoint; component deltas are not final
acceptance. Failed candidates, source hashes and commands remain under
`reports/p1-018/research/rear-lamps-29/` and
`reports/p1-018/research/packaging-interfaces-29/`, with independent records
under `reports/p1-018/qa/`. Human visual, driving, usability and rights gates
remain open.
