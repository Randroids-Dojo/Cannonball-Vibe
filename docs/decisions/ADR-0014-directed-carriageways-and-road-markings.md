# ADR-0014: Directed carriageways and road-marking semantics

- Status: Accepted
- Date: 2026-07-19

## Context

The rendered variable-lane fixture exposed a yellow marking on the outside of a
right-side lane taper. The renderer had placed both roadway edge lines in one
white mesh, then used a yellow material for every partial entrance or exit lane.
That made a same-direction right-side transition read like an opposing-traffic
boundary. Separately, the route contract represented every edge as directed but
did not say whether an edge was one carriageway of a divided highway, an
unpaired ramp, or an unclassified legacy roadway. The representative
interchange happened to contain a parallel reverse edge, but nothing required a
reciprocal pair or allowed a future traffic system to identify it safely.

Real divided highways do not merge opposing flows into the same lane ribbon.
They construct two separately aligned carriageways divided by a median or
barrier. Under the MUTCD, yellow longitudinal markings separate opposing
traffic or mark the left edge of a divided or one-way roadway, while white
markings separate same-direction lanes and mark the right edge. Exit and
entrance channelization on the right is therefore white.

## Decision

- A `RouteEdge` remains a single direction of travel. Lane indexes and lane
  sections never contain opposing traffic.
- Route schema 5 adds `roadway_kind`, `carriageway_group_id`, and
  `opposing_edge_id` to every edge.
- A `divided_carriageway` edge must identify a distinct opposing edge. The pair
  must be reciprocal, must share one stable carriageway-group ID, and must be
  present in the same validated graph.
- `one_way_ramp` and `one_way_roadway` edges are intentionally unpaired and may
  not declare an opposing edge. `unclassified` preserves older or incomplete
  source truth without inventing a pair.
- The offline pipeline accepts explicit source or authored-override pairing and
  rejects missing, ambiguous, self-referential, and nonreciprocal pairs. It does
  not synthesize an opposing carriageway from nearby geometry.
- The renderer uses a continuous yellow left/median edge marking, white broken
  same-direction lane dividers, a continuous white right edge marking, and white
  right-side gore or channelization markings.
- The future `TrafficDirector` may place same-direction traffic only on the
  active directed edge and opposing traffic only on its validated reciprocal
  edge. Physical proximity alone is never sufficient to infer traffic flow.
- Undivided two-way highways are not represented by the current one-direction
  lane-section model. Supporting them requires a later explicit bidirectional
  cross-section contract, centerline-marking rules, traffic-lane direction, and
  collision/route validation. They must not be approximated by putting opposing
  agents into an existing edge.

## Consequences

- Divided highways can stream, render, navigate, save, and simulate each
  direction independently while retaining an exact relationship between them.
- Ramps and true one-way roads remain first-class without fake reverse lanes.
- Source packages that do not establish roadway kind remain usable but cannot
  claim paired-carriageway or opposing-traffic coverage.
- Schema-4 and older packages load as `Unclassified`; schema-5 packages carry
  and validate the explicit contract.
- Production corridor authoring must provide or deterministically derive pairing
  from an approved source/override rather than guessing from line proximity.

## Design basis

- [MUTCD 11th Edition, Part 3](https://mutcd.fhwa.dot.gov/pdfs/11th_Edition/part3.pdf)
  defines yellow and white longitudinal-marking meanings.
- [FHWA freeway exit marking example](https://ops.fhwa.dot.gov/freewaymgmt/publications/frwy_mgmt_handbook/fig6_3_longdesc.htm)
  shows a yellow left edge and white right-side exit/gore channelization.
- [FHWA freeway entrance marking example](https://ops.fhwa.dot.gov/freewaymgmt/publications/frwy_mgmt_handbook/fig6_4_longdesc.htm)
  shows white same-direction entrance channelization.

## Rejected alternatives

- **Put both traffic directions on one route edge:** conflicts with directed
  navigation, lane indexing, save position, ramps, and independent streaming.
- **Assume every highway edge has an opposing edge:** false for ramps, one-way
  facilities, incomplete sources, construction variants, and discontinuities.
- **Pair nearby parallel lines heuristically at runtime:** can pair frontage
  roads, ramps, or unrelated grades and silently spawn head-on traffic.
- **Keep all edge markings white:** fails the visual language for the left edge
  of a divided carriageway.
- **Use yellow for a right-side taper:** falsely signals an opposing-flow
  boundary where traffic is moving in the same direction.
