# What NHPN carries inside the 45 large milepost gaps

Date: 2026-08-27

Task: P0-021. Performs the probe that
[the milepost-gap characterisation](2026-08-16-milepost-gap-characterisation.md)
prescribed, and closes the acquisition-predicate question
[the break-contiguity finding](2026-08-14-break-contiguity.md) raised.

Status: diagnostic acquisition. No bridging is performed, no lock is changed,
no route is selected, and no direction or authoritative distance is claimed.
Probe responses stay in the ignored cache.

## Why this exists

The 2026-08-14 finding — only 3 of 67 chain ends milepost-contiguous —
concluded that the candidate set lacks the records that would join the chains,
and that the next stage was a question about the acquisition predicate,
possibly requiring re-acquisition. The 2026-08-16 characterisation then showed
about 40% of the within-key gaps are quantisation artefacts, but left the 45
gaps over a mile unexplained and named the test that would explain them:
query NHPN for the gap's milepost range without the sign filter. That query is
an acquisition, and this audit makes it.

## Method

A new pipeline command, `probe-continental-milepost-gaps`, recomputes the gaps
from the checksum-locked candidate lock and the response cache whose page
hashes that lock pins, then fetches every gap's **whole LRS key unfiltered**
(`LRSKEY='<key>'` — no sign filter, no state filter) with the same paging,
checkpoint, and hash discipline as the candidate acquisition. Every record
overlapping a gap is classified: already in the candidate lock, excluded by
the sign filter, excluded by the state filter, excluded by both, or matching
the original predicate while absent from the lock, which would be an anomaly.
The probe refuses to run when the live service metadata hash differs from the
locked one, because it would then characterise a different dataset than the
one the gaps were measured in.

Two facts establish the probe ran against the same source snapshot the lock
pinned:

- The live service metadata is byte-identical to the locked canonical hash
  (`5150b91e…`), with `dataLastEditDate` unchanged at `1720466290444`.
- The locked response cache was regenerated from the live service on this
  machine before probing, and reproduced the committed lock exactly modulo
  acquisition timestamps: identical page hashes and the identical
  15,525-candidate union.

The probe fetched 33 unique LRS keys and 3,363 records (all with usable
mileposts) into an 8.2 MB ignored checkpoint cache. Re-running it resumes all
33 pages from checkpoints without re-download.

## What the probe found

```
45 gaps probed, 3 fully covered by records on their key, 5 partially covered,
37 without records on their key, 0 predicate anomalies
```

| Classification | Gaps | Gap miles |
| --- | ---: | ---: |
| No records on the key in the range | 37 | 2,400.9 |
| Fully covered by records on the key | 3 | 58.8 |
| Partially covered (186.1 mi of coverage) | 5 | 855.6 |

**Zero predicate anomalies.** No NHPN record anywhere in the probed keys
matches the acquisition predicate while being absent from the lock. The
acquisition acquired everything its predicate describes.

**37 of 45 gaps — 2,400.9 miles of milepost space — contain no NHPN records
at all**, under any signed route or any state. There is nothing on those keys
in those ranges to acquire.

The eight populated gaps decompose completely:

- **Already-locked records (151 classifications):** Nevada I-15 records locked
  under `i15-cove-fort-to-barstow` fill the Salt-Lake segment's gaps on the
  shared key `000000001500003` — a segment-scoped grouping artefact, not
  anything unacquired.
- **A different signed route within the declared states (46 records):** New
  Jersey Turnpike sections signed I-95/NJ-700 but not I-80 on key
  `00000095__00003`, and Ohio records signed only S-11 on key
  `000000001100099`. These facilities are not on the ADR-0024 route where they
  are not signed with its Interstates.
- **The declared route beyond the declared states (162 classifications, 81
  distinct records):** Montana I-15 (concurrent US-287) on key
  `000000001500049`, counted once per segment sharing the gap. Montana is
  beyond the corridor; these are the route continuing past Salt Lake City, not
  missing corridor.
- **Unrelated routes on a colliding key (5 records):** Delaware S-15/S-896
  records on I-15's key `000000001500003`, and Nebraska S-70 records filling
  I-70's key `000000007000041`. **LRSKEY is not nationally unique**: distinct
  states reuse a key with independent milepost spaces.

## The state-collision hypothesis, tested and mostly rejected

Because keys collide across states, the gap measurement was re-run offline
grouping the locked records by `(STFIPS, LRSKEY)` instead of `LRSKEY` alone —
the only change being the group key. The result barely moves: 104 gaps stay
104, and 45 over a mile becomes 44. Only the 280.9 mi composite on key
`000000008000153` dissolves, into separate New Jersey and Iowa sections with a
residual 3.594 mi gap in Iowa. Cross-state key reuse is real but explains
almost none of the large gaps, so the shipped audit's numbers stand to first
order. A future change to the audit's grouping should nonetheless use the
state-qualified key, since the unqualified one demonstrably mixes states.

## What follows, and what does not

**The predicate question is closed.** The candidate set is not missing records
that a corrected sign or state filter would have returned: for 37 of 45 gaps
the source carries nothing in the range, and for the rest what it carries is
either already locked, not the declared route, or the route beyond the
corridor. No re-acquisition against these keys' milepost ranges can join the
chains.

**Within-key mileposts are exhausted as a lens.** A chain's milepost span ends
where the key stops carrying the route; continuity across key boundaries is
geometric. That is what the endpoint-snapping audit measured when it found six
of twelve segments unconnected at the 1 m tolerance, and it is where the
question now lives.

**The next stage is a geometric probe at the break locations:** query NHPN
spatially around each unconnected chain-end pair, without the sign filter, to
establish whether the source asserts any joining feature there — for example a
facility carrying the route unsigned, which lives on a different key and is
invisible to the milepost lens — or whether the break is authoring noise
beyond the snapping tolerance. That evidence is what an ADR-0018-compliant
per-break decision needs, and this probe's checkpointed acquisition machinery
is reusable for it.

## Scope limits, stated because they are easy to overread

- This characterises linear referencing within the gap keys. It does **not**
  establish that the acquired set covers the corridor geometrically; the six
  unconnected segments remain the open fact.
- "No records in the range" is a statement about one key's milepost space, not
  about the road.
- The milepost-adjacency tolerance derived from the source quantum remains a
  separate lock-affecting decision, untouched here.

## Verification

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  probe-continental-milepost-gaps
```

Requires the locked NHPN response cache (regenerable from the live service
while its metadata hash still matches the lock) and network access for the
whole-key queries; re-runs resume from the probe's own checkpoint cache. The
command validates the candidate lock and every page hash before measuring,
refuses a drifted live service, and changes no lock. Output:
`45 gaps probed, 3 fully covered by records on their key, 5 partially
covered, 37 without records on their key, 0 predicate anomalies`.

Nine unit tests cover uncovered-span arithmetic, sign-slot space padding,
exclusion attribution, anomaly flagging, locked-record handling on shared
keys, the quantum coverage tolerance, boundary abutment, service-drift
refusal, and end-to-end classification with provenance through fake
transports.
