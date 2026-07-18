# ADR-0011: Lane topology, route context, and authoritative trip map

- Status: Accepted
- Date: 2026-07-17

## Context

The locked game design requires continuous highway lanes, meaningful exits,
highway transfers, alternate route families, and understandable route choices.
The current schema stores one lane count per edge, the fixture pipeline emits
two lanes for every edge, and the graybox renderer draws fixed lane markings.
It does not yet represent lane additions or drops, lane-level junction
connections, exit metadata, route-reference mile markers, or a full-screen map.

The authoritative route position must remain an edge ID plus distance along the
edge, lane, and local offsets. NHPN remains a coarse public-domain topology
backbone and must not be presented as observed lane geometry. New route
semantics therefore need deterministic derivation or authored overrides with
recursive provenance and machine-checkable validation.

## Decision

### Lane topology

- Keep stable route edges as the global navigation and save-state unit. Model
  lane-count changes as ordered, non-overlapping distance-bounded lane sections
  within an edge instead of splitting the global graph at every paint change.
- Give every lane section a stable ID, start and end distance, ordered lanes,
  lane widths, lane roles and allowed maneuvers, shoulder information,
  direction, and provenance or authored override ancestry.
- Model junction movement with explicit lane-to-lane connectors between
  incoming and outgoing edges. Connectors declare continuation, merge, split,
  exit, entrance, or highway-transfer behavior.
- Require deterministic lane remapping when a save resumes across a compatible
  content migration. Reject ambiguous or impossible remaps with an actionable
  error instead of silently moving the vehicle.
- Derive road width, markings, shoulders, gore areas, barriers, collision, and
  branch geometry from the lane sections and connectors. Authored interchange
  overrides must preserve the same graph and validation contracts.

### Route context, exits, and mile markers

- Add versioned route identity and concurrency records for route system,
  number, shield, signed direction, and local name.
- Add stable exit records for number and suffix, signed destinations, services,
  connected node or ramp, and source or authored provenance.
- Represent mile markers as route-reference markers tied to a route identity,
  signed direction, edge, and distance along edge. Do not use trip completion
  distance as the displayed mile-marker number.
- Preserve official discontinuities, direction-specific numbering, state or
  jurisdiction resets, and concurrent-route identities when the locked source
  supports them. If exact marker information is unavailable, use explicitly
  labeled deterministic authored or derived metadata; never infer false
  precision from NHPN linework.
- Generate roadside mile-marker meshes and exit or transfer signs from semantic
  records so rendering can change without changing navigation or save data.

### Full-screen trip map

- Add an engine-independent trip-map projection in `Cannonball.Core` backed by
  simplified immutable graph geometry and authoritative run state. The map must
  not depend on loaded Godot road chunks or scene-node transforms.
- Store content-addressed simplified map geometry with stable node and edge
  associations, deterministic levels of detail, and a measured root/package
  size budget.
- Show the start, destination, current position, traveled path, planned path,
  route alternatives, selected service stops, upcoming exits and highway
  transfers, real distance completed, real distance remaining, and mode-aware
  time or compression estimates.
- Keep trip progress distinct from route-reference mile markers. Progress is
  measured across the selected graph path; mile markers describe the signed
  local highway reference system.
- Implement the full-screen presentation in Godot with stable semantic
  automation IDs, keyboard and controller navigation, bounded pan and zoom,
  and deterministic screenshot states. Core model tests and headless scenarios
  remain authoritative; modern PlayGodot may exercise semantic rendered UI
  after its adoption gate is satisfied.
- Treat whether the simulation pauses while the map is open as a product
  decision recorded in the open-question register, not an implicit UI detail.

## Consequences

- The route FlatBuffer schema requires a versioned migration before variable
  lanes, exits, mile markers, or transfers ship.
- Lane geometry, interchange rendering, navigation, traffic, signs, saves, and
  the map share one semantic contract instead of reconstructing topology from
  meshes independently.
- Continental packages must include simplified map geometry, but that geometry
  is presentation data and cannot become the authoritative route state.
- Representative fixtures must cover lane additions and drops, merges and
  splits, divided highways, ramps, overpasses, parallel edges, route
  concurrency, exit numbering, mile-marker resets, and at least two highway
  transfer forms.
- Human review remains required for geographic plausibility, route-choice
  comprehension, accessibility usability, and driving readability.

## Rejected alternatives

- **One lane count per edge:** cannot model mid-edge additions, drops, or
  auxiliary lanes without excessive graph fragmentation.
- **Split the global edge at every lane change:** makes route identity, saves,
  telemetry, and map progress unnecessarily unstable.
- **Infer transfers from nearby splines at runtime:** is ambiguous and cannot
  guarantee deterministic lane continuity or branch prewarming.
- **Use cumulative trip distance as mile-marker text:** produces incorrect
  signs across direction changes, jurisdictions, route resets, and concurrent
  highways.
- **Build the map from loaded scene geometry:** makes continental navigation
  incomplete, streaming-dependent, and unsuitable for deterministic tests.
