# P1-018 interactive showroom

The user requested an interactive car viewer in addition to the existing sedan
production work. This scope extends the already claimed P1-018 slice in draft
PR #144. The lead owns `game/Vehicle/Showroom/`, the narrow inspection/Main entry
hooks, this document and ledger/evidence updates. Runtime/QA agents own the
showroom test and reports they are explicitly assigned. Blender source and
exports retain their single writer and their existing acceptance gates.

The showroom uses the project-owned vehicle wrapper and its existing opening,
lamp, instrument and wiper presentation. It does not simulate another drivetrain.
A frozen display vehicle lives in a private Godot viewport/world. Standalone
launch needs no route package; parked inspection can open the same viewer as a
modal, pausing the current run and preserving its route, rigid body, input and
elapsed-time state. Closing returns to the parked inspection panel. No save
format, starter speed, driving physics or asset budget changes are part of this
extension. No Forza branding, assets or interface artwork are copied.

Acceptance for this extension:

- Smooth full orbit, zoom and pan; front, rear, both sides, top, underside,
  cockpit, rear cabin, engine-bay and luggage viewpoints; reset and automatic
  orbit. The floor cannot block underside inspection.
- Six independently operable existing hinges and open/close-all, plus lights,
  hazards and wipers. Entering a compartment view opens its applicable panel.
- Mouse/keyboard and existing controller conventions, visible help, keyboard
  focus, responsive layout and a UI-free photo capture of the actual viewport.
- Neutral studio, daylight and night lighting using original procedural input;
  readable black paint and cabin, with the actual imported materials preserved.
- Native rendered/input tests verify camera travel, all six actual joint angles,
  lighting, photo output and modal enter/exit without run-state mutation. Actual
  screenshots are inspected independently. Headless checks alone are insufficient.
- Full local `scripts/check.sh`, existing sedan/Hero/graybox regressions and
  the applicable Windows/Linux/macOS rendered UI evidence remain required.
  Quantitative showroom costs are measured separately from driving budgets.

Evidence is recorded at `reports/p1-018/showroom29/` and summarized in
`evidence/M5/P1-018.json`. The installed production34 asset remains visibly a
work in progress while the newer Blender geometry is corrected. This viewer
does not close existing geometry, source rights, visual or usability gates.

The 2026-09-13 native review identified camera framing, rear-seat obstruction,
underbody illumination and controller focus/recovery defects. These are viewer
corrections; original vehicle materials and geometry stay bound to the installed
asset. A local underside inspection light and rearward cabin camera provide
useful inspection views without hiding the asset's existing defects.
The native06 minimum-zoom capture also put the exterior camera inside the cabin.
Exterior orbit now requires conservative clearance from the current visible
display meshes' transformed local bounds. These are cached bounds, evaluated
at each opening's current transform; they are not triangle-level collision.
Each bound is expanded by a world-space camera sphere enclosing the near plane
with at least 10 cm radius, including nonuniform transforms. The camera's final
radial distance is separately reported from the requested zoom distance.
Interior preset cameras retain their separately authored inspection positions.

For renderer verification the lead owns an optional `rendering_method` argument
in the existing debug-only PlayGodot launcher. Its default remains Compatibility;
an explicit Forward+ run exercises the project's shipping renderer. The runtime
agent owns the associated launcher regression and native showroom tests. This
does not change CI's default rendering policy, engine, RPC or security boundary.
An optional bounded `window_size` tuple passes official engine window/resolution
flags before the application argument separator for native 1440p measurements;
the existing default launch receives no additional size flags.

An automation-only fixed-capacity frame buffer records monotonic frame intervals
after a two-second warmup for each view/lighting case, plus private viewport draw
costs and process/engine memory. Timing includes the debug observer and other
applications on this workstation. Overflow is reported. These measurements are
diagnostic; they do not substitute for the declared reference-PC driving suite.
Count, elapsed time and quantiles are published as one population snapshot;
working-set high-water is a one-second sampled maximum. The private 3D viewport
tracks the actual window pixel size, independently of logical UI scaling, so
photos and cost measurements report the resolution actually rendered.
The initial proposed showroom target is stable 60 FPS at 2560×1440 Forward+;
acceptance of that separate product budget remains unresolved until the measured
candidate and its machine/renderer settings are reviewed.

Studio shadow tuning follows the documented distinction between depth bias and
normal bias: too little produces self-shadow artifacts, too much detaches
shadows. Native comparisons determine the local setting rather than changing
the vehicle's imported normals. Reference: [Godot Light3D](https://docs.godotengine.org/en/stable/classes/class_light3d.html#class-light3d-property-shadow-bias).
The native07 underside also exposed a bright lighting card in the background.
The original softboxes now contribute only to the radiance cubemap, preserving
their reflections against a neutral background. This uses the official
[sky shader cubemap pass](https://docs.godotengine.org/en/stable/tutorials/shaders/shader_reference/sky_shader.html).

Native11 passes the full Windows Forward+ control/return scenario. Its actual
night capture still loses broad door detail, and the full photo path can overlap
the right controls in daylight. The next bounded viewer correction raises the
night's cool fill and ambient/reflected base illumination, and confines transient
messages to a dark, ellipsized panel clear of the controls. Imported vehicle
materials, cameras, joint behavior and the measured lighting comparison poses
remain fixed. A short actual comparison precedes acceptance of these settings.

The lighting14 originals confirm the notice correction but still lose broad
night door detail. The next comparison adds a low, smooth cool horizon fill to
the night reflection cubemap only; the visible background and studio/daylight
settings stay fixed. The native07 full-UI cockpit also clips the lower steering
wheel behind the controls. Its default view will look further downward from the
same occupant anchor, with unchanged field of view, so the controls can be
inspected with the interface visible. Actual full-UI captures must verify this
composition at their declared resolution. These changes do not approve the
vehicle's material response or driving camera.
