# P0-014 directed-carriageway adversarial review

## Outcome

The directed-carriageway and marking contract passes its local machine gates.
Route schema 5, Python packaging, C# loading, the in-memory route graph, Godot
streaming, and procedural road rendering now agree on one model:

- one `RouteEdge` carries one direction of travel;
- a divided highway is a reciprocal pair of directed edges with opposite signed
  directions and one stable carriageway-group ID;
- ramps and true one-way roads are unpaired;
- the median/left edge is yellow, while same-direction lane dividers, the right
  edge, and right-side channelization are white.

P0-014 does not invent undivided two-way support. That product scope remains
Q-026, with divided mainlines plus one-way ramps as the working default.

## Adversarial findings and dispositions

### A nearby reverse spline was not a contract

The previous representative fixture included `opposing-carriageway`, but it was
only a spatially parallel edge. No package field related it to the active edge,
so a traffic system would have needed to guess from proximity. Schema 5 now
serializes roadway kind, group ID, and reciprocal opposing edge ID. Both Python
and C# reject missing, self-referential, asymmetric, differently grouped, or
same-signed pairs. Proximity inference is explicitly prohibited by ADR-0014.

### The right-side yellow segment encoded the wrong meaning

`RoadChunk` previously combined both roadway edges into a white mesh and used a
yellow `Gore` material for partial entrance/exit lanes. The renderer now emits a
separate yellow `MedianEdgeMarking`, retains white same-direction dividers and
the white right edge in `LaneMarkings`, and uses a white channelization material
for the partial-lane treatment. The semantic snapshot fails unless those nodes
use their declared shared materials.

### Data pairing alone did not make the second roadway visible

The world streamer previously loaded only route-plan and probable-branch chunks.
It now adds the longitudinally corresponding chunk range from a validated
opposing edge to the visual set, while leaving that opposing roadway outside the
player collision set. The official-engine road-visual scenario observed nine
visual chunks, one opposing-carriageway chunk, and one active collision chunk at
the final paired-road review point.

### Loading an entire opposing edge would not scale

The first implementation candidate could have loaded every chunk on a paired
edge. The final implementation reverses the active manifest's normalized
distance interval onto the opposing edge and loads only overlapping chunks.
This remains bounded when a paired edge contains multiple chunks or the two
alignments have slightly different measured lengths.

### Old packages needed an explicit compatibility result

Schemas 1 through 4 load with `RoadwayKind.Unclassified` and no fabricated
pair. Schema 5 requires a recognized roadway kind and validates every declared
pair before constructing the graph. Existing route/lane migration behavior is
unchanged.

## Verification

- `DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --no-restore`: 72 passed.
- `uv run --project tools/map_pipeline --frozen pytest tools/map_pipeline/tests -q`:
  78 passed.
- Official Godot 4.7.1 road-visual scenario:
  `CANNONBALL_ROAD_VISUAL_OK`, 9 visual chunks, 1 opposing-carriageway chunk,
  622 reflectors, 198 barrier segments, 198 guardrail segments, 0 chunk failures.
- Full `scripts/check.sh`: doctor, .NET build/tests, Ruff, map-pipeline tests,
  PlayGodot unit tests, and official-engine smoke passed.
- The refreshed P0-012 aggregate corpus covers 3 legal fixtures, 12 invalid
  mutations, all 4 legal interchange plans, 12 save/resume checks, and one
  parallel-carriageway pair. Its separate Q-025 human gate remains pending.

## Review artifact

[Six-view paired-carriageway and marking sheet](../images/p0-014-carriageway-markings-review.png)
shows the continuous yellow left edge, white right edge and same-direction lane
paint, transfer approach, and the separately streamed opposing roadway at the
I-25 review point.

## Remaining work

- P0-015 owns moving same- and opposing-direction traffic, traffic LODs,
  high-relative-speed collision behavior, and the human fairness/readability
  gate.
- P1-009 retains final highway-art quality, night rendering, exact signage,
  bridge/overpass assets, budgets, and rights approval.
- Q-026 decides whether an explicit undivided two-way cross-section becomes an
  early corridor requirement or remains a later road family.
