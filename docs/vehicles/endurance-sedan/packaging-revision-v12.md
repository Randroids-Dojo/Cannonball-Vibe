# Meridian S8R packaging revision12

2026-09-11. Revision11 and its source24/25 construction failures remain
preserved. This refinement addresses actual closed-trunk fit and preview/runtime
instrument consistency. Global dimensions, brake sizes, occupant hardpoints,
driving physics, speed policies and all existing budgets remain unchanged.

Actual source23 rays show an approximately45 mm open slot behind the closed
trunk lid. The upper rear body ends at Y=-2.430 m while the lid ends at
Y=-2.385 m. The large interior cutter rises above the rear sill and perforates
it; this is not the declared3.5 mm panel seam. The corrected interior must
retain an upper sill to the existing aperture boundary Y=-2.3885 m, with the
unchanged lid and3.5 mm gap. The accepted cavity is a concave Y/Z prism
extruded over X=-0.790..0.790 m. Its outline is (-2.430,.295), (-1.500,.295),
(-1.500,.945), (-2.3885,.945), (-2.3885,.880), (-2.430,.880), in meters.
This preserves the full lower cavity for the existing tool bag and carpet.
The adjacent tail optical cuts retain X/Y and their lower Z=.8055 m; their
upper Z rises1 mm to .9315 m, giving center Z=.8685 and height .126 m.
This provides a guarded1 mm gap to the unchanged upper lamp walls.

Independent candidate08 uses the actual source23 geometry. The restored
122-triangle region is valid, has no contacts with other source components,
and passes guarded1 mm fixed clearances. All six opening assemblies clear
it over their full angle domains, including a refined trunk lower bound of
1.2858 mm. The complete rebuilt body, export, and visible rear seam must
still pass; the earlier failed union diagnostic is not accepted geometry.
No simulated latch or fuel-transfer mechanism is claimed.

Source26 stopped before LOD generation because its new evaluated-triangle
copy retained dependency-graph material IDs. These are temporary IDs; clearing
the evaluated mesh invalidated the copied slots. The corrected copier retains
each original persistent material datablock while preserving triangle corners,
UVs and normals. The failure, source checkpoint and input modules are retained.

Source27 exposed a new triangulation sliver on a floor face behind the front
splitter. Its vertex was only22.47 nm from the opposite edge, but it was an
original protected vertex at that stage. The correction freezes the exact
post-floor evaluated triangles before the next splitter Boolean. It does not
delete protected vertices or weaken the degeneracy/surface-distance limits.

Source28 constructs successfully but exceeds the active geometry ceiling by
36 triangles (150,036 against150,000). The four inner brake hats are reduced
from40 to32 radial segments, preserving their43/106 mm radii,36 mm width,
positions and materials. This saves256 triangles. The largest ideal-circle
chord deviation is0.511 mm; the actual old/new surface difference and fixed
wheel-detail views must be measured. Tire, rim and friction-disc tessellation
stay fixed. This is a representation choice, not a brake-dimension change or
a raised content allowance.

Blender's low-fuel preview changes from10 L to the runtime's actual20 L
threshold. Four bounded source inspection properties expose damage, cooling
condition, tire condition and handbrake. The six warning labels use the
existing runtime priority and thresholds: fuel below20 L, damage above0.05,
cooling below0.4, tires below0.3, any opening above0.001, then handbrake
above0.02. Damage/handbrake default to0; cooling/tires default to1. Source
opening controls directly set a posed fraction, while runtime considers both
current and target fractions during its animation. These are explicitly
source-only display previews; they do not implement mechanical condition
simulation in Blender. All labels share the corrected upper warning strip.

The native76-case source test exposed float representation errors exactly at
damage=.05 and opening=.001. Blender converts driver inputs to float32;
comparing those values with unquantized decimal literals crossed the nominal
boundaries. Source preview thresholds now use their exact float32 values and
direct complementary priority predicates. Runtime condition fields remain
double precision, and runtime opening/input fields remain float32. The source
preview therefore has float32 display precision; it does not claim bitwise
equivalence to every possible double-precision condition value.

The source-only PARK BRAKE label had two font contours welded along one edge.
Separating their vertex indices by connected closed shell adds two vertices
while preserving all680 oriented triangles at exactly the same positions,
plus their materials, UVs and corner normals. This removes the nonmanifold
edge without changing the visible lettering or exported art.

The expanded official-engine presentation verification covers all six existing
warning states, including actual glyph visibility and missing-state/glyph
negative controls. Rear brake/reverse spill is separately corrected in the
project-owned presenter to keep light from passing through opaque bodywork;
semantic anchors, lens emission and source geometry stay fixed. Neither
machine evidence nor a passed display check closes the required human driving,
visual, rights or usability gates.
