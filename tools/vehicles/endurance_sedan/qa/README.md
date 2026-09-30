# Independent Meridian S8R source QA

Run from the repository with Python and the pinned official Blender 5.1.2.
Select the actual source-generation project produced by the source builder:

```powershell
$sedanBlender = 'C:\Program Files\Blender\blender-5.1.2-windows-x64\blender.exe'
$sedanCandidate = (Resolve-Path 'reports/p1-018/reconstruction/project').Path
python tools/vehicles/endurance_sedan/qa/run.py `
  --source "$sedanCandidate/data/assets/vehicles/sources/endurance-sedan.blend" `
  --source-binding "$sedanCandidate/data/assets/vehicles/sources/endurance-sedan.source-binding.json" `
  --construction-root $sedanCandidate --blender $sedanBlender `
  --output reports/p1-018/qa/final-source-NEW
```

The source, its binding and the constructor closure must agree. Choose a new
output directory for every attempt. This command opens the source read-only;
it does not save it, export shipping assets or install a runtime package.
It snapshots the QA Python/JSON inputs, hashes the source and executable,
retains every command and transcript, and checks inputs and prior outputs
throughout execution. A zero exit accompanied by a driver, Python,
missing-image or native-fatal diagnostic fails acceptance.

## Required inventory

The validated binding selects the exact ordered inventory in [gate.py](gate.py):
21 stages for historical v1, 24 for base v2, 25 with either repeated-detail or
valance-cover policy, and 26 with both. The current specification declares both.
Neither a selected prefix nor a manually shortened list can pass. The current
complete sequence is:

```text
extraction
historical-extraction
historical-shoulder-field
current-front-field
distance-fields
self-intersections
self-controls
lod-self-intersections
lod-self-controls
source-controls
source-lights
opening-drivers
motion-drivers
repeated-detail
optical-seats
finish-interfaces
cupholder-interfaces
valance-cover
static-interfaces
openings
opening-containment
tires
wiper-glass
wiper-interassembly
wiper-containment
negative-controls
```

Native extraction checks evaluated topology, all LODs, preview geometry,
poses, budgets and raw corner normals. Historical shoulder, current front
and distance-field checks bind their actual construction checkpoints and
reopened final fields separately. Exact self checks distinguish crossings
from indexed shared edges and vertices; disconnected lower-LOD shells are
also checked without welding away their identities.

Control stages exercise actual saved driver expressions, pivots, descendants,
instrument and warning states, lamp emission and beam bindings. Repeated-detail
verification consumes the actual pre-detail checkpoint. Valance-cover
verification binds its pre-cover source and requested fields, checks complete
physical sections and finite joints, and requires deliberate corruptions to
reject. Static QA consumes those finite joint results; the later opening stages
still cover all five cover members throughout the required motion domains.

Optical, finish, cupholder and static stages check their declared complete
interfaces and neighbors. Continuous opening, tire and wiper bounds follow
local interface checks. Initial containment is checked separately in both
directions: disjoint surfaces can still enclose a solid. Samples alone or an
exhausted search do not prove continuous clearance. Each report records its
actual member and control counts, domains and limitations.

Unrelated rigid geometry requires 1 mm clearance and tires 5 mm, with the
existing 1 micrometer numerical guard. Named bearings, compressible closed-stop
seals and fitted joints retain their own finite rules. Diagnostic fragments
cannot weaken the original 1e-12 square-meter source triangle threshold, and
small area does not excuse an uncovered interface. Required negative controls
include malformed topology, hidden containment, intermediate-pose collisions,
invalid drivers, changed fields and incomplete inventories.

These selected interfaces do not certify every internal upholstery, brake,
floor or drivetrain contact. Newly found assembly defects remain open until
their affected domains pass. The engine bay is modeled geometry; source
display and driver checks do not establish a mechanical simulation.

## Delivery boundary

Record the completed run's actual duration; finite per-command watchdogs
remain enforced. Do not overlap these CPU proofs with accepted idle-host
performance measurements. Preserve failed attempts and use fresh retry paths.

This gate does not replace two-export shipping-byte comparison, clean import,
wrapper validation, actual renders and runtime media, platform/performance
tests, or human art, rights, usability and driving-feel approvals. Follow the
[complete source and runtime staging instructions](../../../../docs/vehicles/endurance-sedan/README.md#reproduce-and-verify).
The task remains open until its full ledger definition of done is satisfied.
