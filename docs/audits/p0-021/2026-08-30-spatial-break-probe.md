# What NHPN asserts at the six unconnected segments' break ends

Date: 2026-08-30 (reconciled 2026-08-31)

Task: P0-021. Performs the spatial probe that
[the large-gap probe](2026-08-27-large-gap-probe.md) prescribed after closing
the acquisition-predicate question: continuity across LRS key boundaries is
geometric, so the joining evidence has to be gathered geometrically, at the
actual break locations.

Status: diagnostic acquisition. No bridging is performed, no lock is changed,
no route is selected, and no direction or authoritative distance is claimed.
Probe responses stay in the ignored `.tools/continental/nhpn-break-probe`
cache.

## Relationship to the geometric break probe

Two sessions independently performed the slice the ledger prescribed, and
their results merged the same day. The
[geometric break probe](2026-08-30-geometric-break-probe.md)
(`probe-continental-geometric-breaks`) answers a **path question**: it selects
14 bounded sites — a minimum spanning tree over component pairs plus the two
transfer-anchor mismatches — and tests whether an unfiltered local NHPN graph
supplies an undirected path across each. It found paths at 5 of 14 sites, and
[Q-034](../../OPEN_QUESTIONS.md) records the per-site ADR-0018 disposition
those facts require.

This census (`probe-continental-break-ends`) answers the **identity question**
that remains at the other nine sites and everywhere the site selection does
not look: what does the source assert at every individual chain end — which
features join it, under which keys, signs, and states, at what measured
endpoint offsets, geometry distances, and bearing alignments. The two commands
share the snapped-graph builder and the envelope helper, so they cannot
disagree about where a segment's graph separates. Their findings are
consistent everywhere they overlap; the per-site reconciliation below states
each agreement and extension explicitly.

## Method

The command validates the candidate, transfer, and edge-path locks, refuses a
live service whose metadata hash has drifted from the locked one, and rebuilds
each unconnected segment's snapped endpoint graph from the checksum-locked
response cache with the same 1 m tolerance the connectivity audit used,
through the shared graph builder.

**Break ends.** A segment's graph separates at its degree-1 chain ends. Two of
them per segment are not breaks: the chain end of each transfer anchor's
component **farthest from the opposite anchor** is where that chain
legitimately continues beyond the corridor — past the anchor toward the next
segment, or past the declared jurisdictions. The naive alternative, excluding
the chain end *nearest* each anchor, was tested and rejected during
development: on `i15-salt-lake-to-cove-fort` it would have excluded the
corridor-critical 88 m break end, because that end is nearer the mid-chain
anchor than the chain's far end at the Idaho line. The two excluded ends are
recorded in the artifact as `anchor_side_ends` rather than dropped. Everything
else — 31 chain ends across the six segments — was probed.

**Probe.** For each break end, every NHPN feature intersecting a 500 m window
around the end coordinate is fetched with **no sign, state, or key filter**
(`where=1=1` plus an envelope built by the shared helper), using the same
paging, checkpoint, page-hash, and retry discipline as the candidate
acquisition; re-runs resume from checkpoints. 500 m is grounded in the
observed data: the largest endpoint discontinuity the audits measured between
nearby chain ends is 661 m, so the two sides of such a break each see well
past their midpoint.

**Classification.** The segment's own locked records in a window are counted;
every other feature is reported with its state, LRS key, signed routes, record
mileposts, and three measured quantities in EPSG:5070: the offset from the
break end to the feature's nearest endpoint, the distance to the feature's
geometry anywhere, and the acute angle between local bearings at the closest
approach (25 m chords). Tiers over those numbers — endpoint within the 1 m
snap tolerance, endpoint within 30 m, aligned within 20 degrees passing within
30 m, unaligned within 30 m, elsewhere in the window — are **reporting lenses
for this audit, not bridging tolerances**. The 30 m lens sits just above the
24.401 m within which the transfer lock reconciled paired facilities. Nothing
is joined and ADR-0018 is untouched.

Break ends are also paired with the nearest probed end in a different
component — observed geometry, not asserted adjacency — and a feature seen
within 30 m of both ends of a pair is reported as spanning it.

The census ran against a live service byte-identical to the locked metadata
(`5150b91e…`, `dataLastEditDate` 1720466290444), after the locked response
cache was regenerated from the live service and reproduced the committed lock
exactly modulo acquisition timestamps: identical page hashes and the identical
15,525-candidate union.

## What the census found

```
6 segments, 31 break ends probed, 25 with an asserted endpoint join,
0 with nothing beyond the locked records
```

**The chains do not dangle. At 25 of 31 break ends, NHPN authors an exact
shared-coordinate endpoint join — all 30 such joins have an offset of exactly
0.0 m — with a record the acquisition predicate excludes.** The joining
records carry other signed routes (US-6, US-22, US-189, I-74/I-280, I-270,
I-275, I-294, AZ S-95, CA S-10/S-60, US-101, UT S-72, historic US-66), no
signs at all (unsigned inventory keys in Tennessee, New Mexico, New Jersey,
Pennsylvania), or the declared route in an undeclared state (Kansas I-70 at
the Colorado line). None of them is locked under any other segment either:
this corridor material is entirely outside the lock.

The six remaining ends see only features farther than 30 m: the two sides of
the 1.011 m Omaha micro-gap, both sides of the Albuquerque I-40/I-25
interchange gap, the west side of the 320 m Rifle break, and the New Jersey
side of the Delaware River crossing.

### Reconciliation with the geometric probe's 14 sites

Site separations are the common key between the two artifacts, since the two
probes index components differently. Census additions in bold.

| Site (separation) | Geometric probe | Break-end census |
| --- | --- | --- |
| LA, 2,491.6 m | Path: 22 unacquired S-10/U-101 records | Agreement. Both western ends join U-101 and S-60 records exactly; the eastern end continues as an S-10-signed record **on the same LRS key**. **Adds the third end (`546481`, exact S-60 join, aligned 0.3°).** |
| Payson UT, 88.176 m | Path: `43841`, U-189 | Agreement. **Adds `43839` as a second exact U-189 join and the bearing grades (0.4° at one end, 44° at the other — a curving connector).** |
| I-15 fragment, 27,347.2 m | No local path | Consistent: no path across 27 km was possible. **Adds that the isolated 0.267-mile fragment's two ends join US-6 records (`42098`, `42792`) exactly — it is embedded in US-6 pavement, not floating.** |
| Topock AZ, 14.069 m | Path: `38597`, S-95 | Agreement. **Adds `38596`, and that both joins meet at ~88° — a tee with the crossing route, not a continuation, which corridor-fit review needs.** |
| Albuquerque, 1,854.0 m | No local path | Agreement: mainline void. **Adds what is there instead: I-25 crossing at ~67° and unsigned frontage-road records running aligned 440–650 m away; nothing joins either end.** |
| ABQ fragment, 13,571.6 m | No local path | Consistent. **Adds that the 6-mile fragment's ends join an unsigned record (`588344`) and historic US-66/S-337 records (`591107`, `591110`, `591111`) exactly.** |
| Memphis, 228.362 m | Path: `218838`, unsigned | Agreement. **Adds that the join is aligned within 3° and that `218838`'s mileposts (2.227–2.378) exactly fill the space between the two ends' records across two different keys — the unsigned concurrency the large-gap probe hypothesised, confirmed in both identity and linear referencing.** |
| Rifle CO, 320.0 m | No local path | Agreement, refined: **the east end (`60295`) joins a US-6 record (`60293`) exactly, aligned 0.0°; only the west end (`60300`) joins nothing, with US-6 records running parallel 74–89 m away. The void is one-sided.** |
| Denver, 5.819 m | Path: `59709`, I-270/U-36 | Agreement. The census probed the eastern side (`63225`: `59709` exact join, aligned 1.1°); the western side is the from-anchor component's far end, recorded as anchor-side. |
| I-78 from anchor, 381.157 m | Anchor outside source graph | Not covered — anchors are outside a chain-end census. The geometric probe's evidence stands alone here. |
| Delaware River, 3,021.99 m | No local path | Agreement. **Adds per-end detail: the NJ end joins nothing (PA S-611 sits 300+ m across the river); the PA end joins only an unsigned crossing record (`427293`, ~85°).** |
| I-80 from anchor, 253.027 m | Anchor outside source graph | Not covered — as above. |
| Omaha, 1.011 m | No local path, no third feature | Agreement. Milepost-contiguous, joined by nothing; the nearest other features are a US-275/S-92 crossing ~470 m away. A pure authoring micro-gap within the 1.61 m milepost quantum. |
| Quad Cities, 9.190 m | No local path | **Both facts stand, and together they say more than either alone. I-74/I-280 records `229625`/`229626` join the two I-80 ends exactly (0.000 m each), yet sit 9.190 m from each other — the identical gap, replicated through the joining pavement. Both record pairs are milepost-contiguous on their own keys. The break is one authoring discontinuity shared by two route families, which is why the local source graph finds no path even though the source asserts joins at both ends.** |

The census also covers spur and beyond-corridor ends no site selection
visits, and they behave the same way: the Chicago end joins I-294
(`261170`), the Knoxville end joins I-275 (`247816`), the Tremonton end joins
I-84/S-30 (`42752`), the Kanorado end joins the Kansas I-70 key (`70438`, the
declared route in an undeclared state), the Fremont Junction end joins S-72
(`42510`), and the two I-78 interior ends join US-22 (`427523`) and an
NJ-139-key record (`434168`).

## What this evidence adds to Q-034, and what it does not decide

Q-034 already frames the per-site disposition: validate direction and
corridor fit for positive paths, and choose acquire, alternate-source, or
bounded reconstruction exception per site. This census sharpens that work in
three ways, deciding none of it:

1. **Named joining OBJECTIDs beyond the five path sites.** Exact
   source-asserted joins exist at 25 of 31 chain ends, including at four
   sites the path test reports as unconnected (Quad Cities, Rifle east, the
   I-15 fragment, the ABQ fragment). A disposition can therefore consider
   scoped acquisition of named records at more sites than the path facts
   alone suggest.
2. **Geometry grades for corridor-fit review.** A 0.0 m join at 88° (Topock)
   and a 0.0 m join at 3° (Memphis) are different situations; the recorded
   alignments separate tees and connectors from continuations before any
   direction-aware review starts.
3. **The micro-gap class is now two members.** Omaha (1.011 m) and Quad
   Cities (9.190 m, replicated across two route families' records) are
   authoring discontinuities the source asserts adjacency across in linear
   referencing while authoring no joining geometry. They are candidates for a
   different disposition class than the multi-kilometre voids.

The remaining evidence hole is bounded and named: the four gap interiors
wider than the census windows — Albuquerque (1.85 km), the Delaware River
crossing (3.02 km), and the two downtown Los Angeles gaps (2.49 and 3.12 km),
about 10.5 km in total — where neither probe has yet established whether NHPN
carries any mainline mid-gap.

## Scope limits, stated because they are easy to overread

- An exact endpoint join is the source asserting shared geometry; it is not a
  statement that the joining record is the route, drivable, or westbound.
  Concurrency, ramps, and crossing routes all join at shared nodes — the
  recorded alignment angles (0.0°–88.9°) are the lens for telling those
  apart, and they are descriptive, not a selection.
- The 500 m windows characterise break neighbourhoods, not gap interiors
  beyond 500 m; pairs whose windows do not overlap are flagged in the
  artifact.
- Nothing here changes the lock, the tolerance, or the anchor policy, and no
  break is bridged.

## Verification

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  probe-continental-break-ends
```

Requires the locked NHPN response cache (regenerable from the live service
while its metadata hash still matches the lock) and network access for the 31
window queries; re-runs resume from the census's own checkpoint cache
(1.3 MB, ignored). The command validates every lock and page hash before
probing, refuses a drifted live service, and changes no lock. Output:
`6 segments, 31 break ends probed, 25 with an asserted endpoint join, 0 with
nothing beyond the locked records`.

The census was first run with a buffer-circle envelope and re-run after
reconciliation onto the geometric probe's shared corner-transform envelope
helper; the reconciled envelope is a strict superset per window, and all 31
break-end classifications, all 30 exact joins, both milepost-contiguous
pairs, and all four spanned pairs are identical between the runs.

Ten unit tests cover the bearing and acute-angle helpers, the tier ladder
from asserted join to distant feature, anchor-side end exclusion, per-feature
classification with cross-segment lock attribution, the source-void report,
checkpoint resumption, the no-breaks-on-a-connected-chain guard,
service-drift refusal, and the generated finding, all through fake transports
in the existing test style.
