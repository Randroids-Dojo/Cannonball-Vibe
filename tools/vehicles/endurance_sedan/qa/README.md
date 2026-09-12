# Independent Meridian S8R source QA

Run from the repository with Python and the pinned official Blender5.1.2:

```powershell
python tools/vehicles/endurance_sedan/qa/run.py --blender 'C:\Program Files\Blender\blender-5.1.2-windows-x64\blender.exe' --source data/assets/vehicles/sources/endurance-sedan.blend --output reports/p1-018/qa/final-source-01
```

Supply the actual delivered `.blend` path if it differs. The output directory
must be new. This command opens the source read-only and never saves it or
creates a shipping export. It snapshots the QA Python/JSON inputs, hashes the
source and executable, retains every command and transcript, and checks those
inputs and previous outputs throughout execution. `evidence.json` begins with
zero completed stages and fails at the first unsuccessful stage. Only the exact
complete ordered inventory can pass. A successful process with a driver,
Python, missing-image or native-fatal diagnostic fails acceptance.

The nineteen stages are:

1. Native evaluated topology and all three LOD inventories, including editable
   preview geometry validity;645 actual source poses and provisional Q044 caps.
   Every raw native corner normal must be finite, nonzero and unit within1e-6
   before Blender's exporter can substitute or normalize it.
2. Exact self-intersection checks of every original LOD0 authored mesh. Integer
   separation certificates and rational triangle clipping distinguish strict
   crossings from indexed shared edges/vertices; the existing1um guard remains.
3. Native self-check rejection controls and exhaustive enumeration/predicate
   fixtures, including source binding, malformed input and incomplete coverage.
4. Final LOD1/2 indexed connected-shell closure, winding and exact self checks.
   Cross-shell candidates are counted explicitly as a separate assembly domain;
   coincident vertices are not welded and stale component ranges are not used.
5. Twenty native lower-LOD controls, including connected folds, disconnected
   crossings, missing LODs, malformed topology and incomplete report coverage.
6.109 source instrument, steering/pedal, wiper, indicator, warning-priority and
   exact float32 threshold states.
7.12 head/tail/brake/reverse preview states, actual emitter bindings, and four
   beam pivots, directions and powers. These explicit source controls do not
   simulate engine, gear or braking physics.
8. All six saved opening driver expressions, axes, pivots and descendants.
9. Actual saved wheel, wiper and cockpit-control driver contracts.
10. All231 rear optical internal pairs and24 finite shared interface seats.
11. All42 finite finish interfaces: two complete A/header butt sections,
    four fitted latch flanges, eight recessed screw seats, and28 complete
    upholstery support domains. Eight shifted copies and an independently
    crossing second pad layer must reject. Every thread
    span needs continuous contact and bounded complete-surface penetration.
12.152 named fixed interfaces and selected packaging, cabin, mirrors, aero and
   rear optical assemblies versus every other LOD0 mesh. Revision14 includes
   the finite roof flange, crossover caps and sixteen complete cabin-tray pad
   faces. Three deliberately intruding copies must fail these constraints.
   Revision17 includes all28 stowed restraint parts against every other LOD0
   part,40 finite guide/cloth/rail attachments, six complete cloth self-contact
   checks and two full intersection bounds inside actual convex rear guides.
   Five further controls must reject tongue intrusion, an8mm disconnected
   tongue, coplanar and nonplanar cloth crossings, and a guide-region escape.
   The two new header joints require the successful source/payload-bound finite
   certificate from stage11 before being treated as mating interfaces.
   Two additional controls isolate clearance and region escape for the short
   header returns outside the roof projection.
13. Continuous all-angle clearance for each opening, including independently
   positioned adjacent openings. Whole-domain bounding boxes and adaptive
   projection bounds prove clearance; a sampled pose or exhausted search does
   not pass.
14. Initial solid containment in both directions for the exact opening pair
   inventory, using connected components and three agreeing unambiguous rays.
15. Actual tire/tread/sipe envelopes over all rolling angles, full32-degree
    steering, full suspension travel and independently positioned openings.
16. Analytic full wiper sweep against actual windshield planes and aperture.
17. Continuous cross-wiper, independent opening, cockpit-control, tire-envelope
    and fixed-mesh separation over the declared domains.
18. Initial solid containment for that exact wiper pair inventory.
19. Seventeen native positive/rejection controls: malformed topology, hidden
    containment, interface intrusion, collision occurring only at an intermediate
    opening angle, invalid/corrected drivers, wiper geometry and extrema, and
    a missing-stage inventory. Synthetic fixtures are identified as such.

Unrelated rigid geometry requires1 mm clearance and tires5 mm, with the
existing1 micrometer numerical guard. Individually declared pin/bearing,
compressible closed-stop seals and fitted joint regions retain their own finite
measured rules. Diagnostic Boolean fragments are checked over their complete
point sets and cannot weaken the original1e-12 m² source triangle threshold.
Roof/pad fragment coverage uses complete convex partitions; tiny area alone
does not excuse an uncovered region. Initial containment is an additional check
because disjoint surfaces alone could enclose a solid.

Each report describes its exact domain and limitations. Internal upholstery and
wheel/brake construction are separate assemblies; this is not an assertion that
every possible pair of decorative parts has a mechanical clearance simulation.
The editable engine bay is modeled geometry, with no mechanical simulation
claim. Source display thresholds reflect Blender's float32 driver precision.

Allow roughly15 minutes on the reference workstation; hard per-command
watchdogs stop an unresolved job. Do not overlap these CPU proofs with accepted
idle-host performance measurements. Historical failures remain retained in
separate evidence directories; a retry uses a fresh output.

This is one required source gate. It does not replace two-export shipping-byte
comparison, clean import and wrapper validation, actual rendered and runtime
media, runtime performance/platform tests, or human art, rights, usability and
driving-feel approvals. The task remains open until its full ledger definition
of done is satisfied.
