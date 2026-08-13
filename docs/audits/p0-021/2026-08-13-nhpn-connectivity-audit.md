# P0-021 NHPN endpoint snapping and connectivity audit

Date: 2026-08-13

Task: P0-021; stage `exact-westbound-path-solve`

Artifact: `data/routes/continental/edge-path-lock.v1.json`

Related: [continental route selection](../2026-07-31-continental-route-selection.md),
[NHPN candidate lock](2026-08-03-nhpn-candidate-lock.md),
[transfer node lock](2026-08-03-transfer-node-lock.md)

## Scope

The candidate lock declares its own next stage as `exact-westbound-path-solve`,
requiring a transfer-node coordinate lock, an NHPN endpoint snapping and
connectivity audit, and a westbound directed-edge selection. The coordinate lock
landed on 2026-08-03. This audit delivers the second requirement and establishes
why the third cannot be a shortest-path solve.

Everything here is computed offline from checksum-locked inputs: the candidate
lock, the transfer lock, and the ignored response cache whose per-page hashes
both locks already pin. No network access and no new acquisition.

## Method

For each of the 12 NHPN-backed segments, every locked line is projected to
EPSG:5070, its endpoints are snapped onto a shared node when they coincide within
1 metre, and the resulting graph is audited for components and for a path between
the segment's two locked transfer nodes.

The 1 metre tolerance absorbs floating-point noise between records the source
authors to share an endpoint. It is deliberately far too small to bridge a real
gap, because a wider tolerance would invent connectivity NHPN does not assert,
which ADR-0018 forbids. The artifact records the largest snap distance actually
used per segment so the margin is auditable rather than assumed; the observed
maximum across all segments is 0.94 m.

## Finding: NHPN carries these Interstates as paired directional carriageways

Between **77% and 97%** of each segment's locked lines share a linear-reference
extent — the same `LRSKEY` with the same begin and end mileposts — with an
opposing-carriageway twin.

| Segment | Lines | Paired | Paired % | Components |
| --- | ---: | ---: | ---: | ---: |
| i10-ontario-to-i405 | 1,289 | 1,210 | 94% | 2 |
| i15-barstow-to-ontario | 1,187 | 1,157 | 97% | 1 |
| i15-cove-fort-to-barstow | 1,949 | 1,826 | 94% | 3 |
| i15-salt-lake-to-cove-fort | 586 | 503 | 86% | 3 |
| i40-i81-to-barstow | 6,656 | 6,367 | 96% | 5 |
| i405-west-la-to-ca107 | 771 | 736 | 95% | 1 |
| i70-denver-to-cove-fort | 703 | 633 | 90% | 3 |
| i76-big-springs-to-denver | 265 | 239 | 90% | 1 |
| i78-holland-tunnel-to-i81 | 275 | 214 | 78% | 2 |
| i80-big-springs-to-salt-lake | 793 | 610 | 77% | 2 |
| i80-new-jersey-to-big-springs | 2,105 | 1,673 | 79% | 3 |
| i81-i78-to-i40 | 966 | 774 | 80% | 2 |

This is the source's shape, not a data defect, and it explains the component
counts directly: each carriageway forms its own chain, and the chains meet only
where NHPN authors a shared endpoint.

## Consequence: connectivity is evidence, not a selection

Six of twelve segments have an undirected path between their locked transfer
nodes; six do not, because the two nodes land on different carriageway
components.

**Neither outcome is a westbound selection, and the artifact does not claim
one.** Where a path was found it is a shortest undirected traversal that may
cross between opposing carriageways at an interchange, which would be a route no
vehicle can drive. The artifact records `westbound_selection_validated: false`
at the top level and `direction_validated: false` on every segment, and the
validator rejects any lock that claims otherwise.

The six unconnected segments are recorded with their failure, both component
sizes, and both transfer-node snap distances rather than being dropped:

| Segment | From-node snap | To-node snap | From component | To component |
| --- | ---: | ---: | ---: | ---: |
| i80-new-jersey-to-big-springs | 253.0 m | 0.0 m | 1,453 | 206 |
| i70-denver-to-cove-fort | 0.0 m | 0.0 m | 324 | 231 |
| i15-salt-lake-to-cove-fort | 0.0 m | 0.0 m | 332 | 255 |
| i78-holland-tunnel-to-i81 | 381.2 m | 0.0 m | 167 | 110 |
| i40-i81-to-barstow | 0.0 m | 0.0 m | 589 | 486 |
| i10-ontario-to-i405 | 8.0 m | 12.5 m | 1,099 | 167 |

Two of those transfer nodes snap hundreds of metres from any graph node, which
is a second finding worth carrying forward: a transfer anchor derived against
one carriageway need not sit on the carriageway the westbound path will use.

## What this does not establish

No authoritative distance. The 1,773 miles across the six connected segments is
the length of an undirected traversal over coarse topology and is not a route
distance; ADR-0024 and the candidate lock both already forbid claiming one at
this stage.

No lane geometry, no direction, no reconstruction gates, no 3DEP dependency, and
no completed path for the three authored-connector segments, which carry no NHPN
candidates at all.

## Next

Westbound directed-edge selection needs a carriageway rule derived from the
linear-reference direction rather than from graph distance, and it must handle
the transfer anchors that do not sit on the selected carriageway. Both are P0-021
work and neither is a product question: ADR-0024 already locks which route is
canonical, and the rule follows from the source's own linear referencing.
