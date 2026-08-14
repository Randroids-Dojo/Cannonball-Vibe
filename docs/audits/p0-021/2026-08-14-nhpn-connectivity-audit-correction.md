# P0-021 connectivity audit: correction to the carriageway finding

Date: 2026-08-14

Task: P0-021; stage `exact-westbound-path-solve`

Supersedes the central finding of
[2026-08-13 NHPN endpoint snapping and connectivity audit](2026-08-13-nhpn-connectivity-audit.md),
which is retained as history.

Artifact: `data/routes/continental/edge-path-lock.v1.json`

## What was wrong

The 2026-08-13 audit reported that NHPN carries these Interstates as **paired
directional carriageways**, with 77% to 97% of each segment's lines sharing a
linear-reference extent with an opposing-carriageway twin, and explained the
graph's component structure by that pairing.

**That finding is withdrawn. It was an artefact of the key the metric used.**

The metric grouped records by `(LRSKEY, BEGMP, ENDMP)`. Those mileposts are not a
per-record extent — they describe the LRS *section* a record belongs to, so every
consecutive piece of one section shares them. The per-record extent is
`BEGIN_POIN` and `END_POINT`.

The two records offered as an example pair are consecutive, not opposing:

| Field | First record | Second record |
| --- | ---: | ---: |
| `BEGIN_POIN` | 16.505 | 17.078 |
| `END_POINT` | 17.078 | 17.241 |

The first ends exactly where the second begins, and its final coordinate is the
second's first coordinate. Grouped by the correct per-record extent, duplicates
across all twelve segments fall from thousands to between 0 and 38, and
duplicate geometric endpoints fall to between 0 and 10. There is no carriageway
pairing in this candidate set to speak of.

## What is actually true

Each locked segment is a **near-linear chain**, not a network. Between 97% and
100% of endpoints join exactly two records:

| Segment | Degree histogram | Chain ends | Interior | Smallest chain-end separations (m) |
| --- | --- | ---: | ---: | --- |
| i80-new-jersey-to-big-springs | 1:7, 2:2093, 3+:3 | 7 | 99.5% | 1.011, 9.190 |
| i76-big-springs-to-denver | 1:2, 2:261, 3+:2 | 2 | 98.5% | — |
| i70-denver-to-cove-fort | 1:7, 2:697, 3+:1 | 7 | 98.9% | 5.819, 320.0 |
| i80-big-springs-to-salt-lake | 1:4, 2:791 | 4 | 99.5% | 1.011 |
| i15-salt-lake-to-cove-fort | 1:7, 2:581, 3+:1 | 7 | 98.6% | 88.176, 423.271 |
| i78-holland-tunnel-to-i81 | 1:6, 2:269, 3+:2 | 6 | 97.1% | — |
| i81-i78-to-i40 | 1:4, 2:963 | 4 | 99.6% | 562.292 |
| i40-i81-to-barstow | 1:11, 2:6643, 3+:1 | 11 | 99.8% | 14.069, 228.362 |
| i15-cove-fort-to-barstow | 1:8, 2:1928, 3+:2 | 8 | 99.5% | 88.176, 423.271 |
| i15-barstow-to-ontario | 1:3, 2:1170, 3+:1 | 3 | 99.7% | — |
| i10-ontario-to-i405 | 1:5, 2:1258, 3+:3 | 5 | 99.4% | 661.136 |
| i405-west-la-to-ca107 | 1:3, 2:764, 3+:1 | 3 | 99.5% | — |

The components arise where consecutive records **do not share an endpoint within
the 1 metre snapping tolerance**. Those breaks are small: 1.0 m, 5.8 m, 9.2 m,
14.1 m, 88.2 m, 228.4 m, 320.0 m, 423.3 m, 562.3 m, 661.1 m. They are endpoint
discontinuities of metres to hundreds of metres, not missing corridor. The very
large separations in the data are the corridor termini and are not defects.

## Why this matters more than the retraction

The withdrawn finding implied the westbound selection needed a **carriageway
rule** to choose between two parallel chains. That work is not needed, because
there are not two parallel chains.

What the corrected evidence shows is a different and smaller problem: a handful
of endpoint discontinuities break an otherwise linear corridor. The next stage
has to decide, with evidence, whether each break is an authoring artefact that
may be bridged or a genuine gap in the candidate set that must be acquired or
authored. A 1.011 m break and a 661 m break are unlikely to warrant the same
answer, and neither can be bridged silently: ADR-0018 forbids inventing
connectivity the source does not assert.

The unchanged conclusions from the superseded audit still hold. Six of twelve
segments have no undirected path between their locked transfer nodes; no path
found is a westbound selection; no authoritative distance is claimed; and two
transfer anchors sit hundreds of metres from any candidate endpoint.

## How this was caught, and what it says about the first audit

It was found while continuing into the next stage: inspecting an actual record
pair to identify what distinguishes two carriageways showed the pair was
consecutive rather than opposing.

The first audit never made that check. It computed a pairing statistic, found it
high and consistent across twelve independent segments, and treated the
consistency as corroboration. Consistency was the wrong test — a mis-keyed metric
is consistently wrong. The check that would have caught it, reading two records
the metric called a pair, costs almost nothing and was skipped because the number
already agreed with the expectation that Interstates are divided highways.

The metric is now replaced by measurements that are structural rather than
inferential: an endpoint degree histogram, a chain-end count, and the distances
between chain ends. Each can be read directly against the graph rather than
believed.
