# What the NHPN contiguity gaps actually measure

Date: 2026-08-16

Task: P0-021. Follows
[the break contiguity finding](2026-08-14-break-contiguity.md), which this audit
qualifies rather than withdraws.

Status: characterisation. No bridging is performed, no lock is changed, and no
acquisition is made.

## Why this exists

The 2026-08-14 finding tested adjacency correctly — one record's `END_POINT`
against another's `BEGIN_POIN` on the same `LRSKEY` — and reported that only 3 of
67 chain ends across the twelve segments are contiguous. It concluded that the
candidate set lacks the records that would join the chains, and that the next
stage is a question about the acquisition predicate, possibly requiring
re-acquisition.

That test is exact. This audit asks what the gaps it rejects actually measure,
because "not exactly equal" and "a record is missing" are different claims.

## Method, and a correction to how contiguity was counted

Contiguity is computed here as a **union of milepost intervals per LRS key**, not
by differencing sorted neighbours.

That matters because the candidate set contains 38 exact duplicate records and
many overlapping ones. Differencing adjacent records reports both as breaks: a
duplicate produces a zero-length step and an overlap produces a negative one. On
`i76-big-springs-to-denver` the same pair appears twice with an identical
−58.634 mi "gap", which is one overlapping record counted twice, not two breaks.

Interval union is invariant to duplication, overlap and record ordering.
`test_milepost_spans_merge_duplicate_and_overlapping_records` and
`test_milepost_spans_are_direction_insensitive` pin that.

## What the gaps measure

Across 17,545 locked records in 377 (segment, LRS key) groups:

- **320 of 377 keys (84.9%) are already a single contiguous span.** Most keys have
  no internal gap at all.
- **104 gaps remain**, and they are bimodal.

| Gap size | Count | Share |
| --- | ---: | ---: |
| ≤ 0.0011 mi (one milepost quantum, 1.61 m) | 32 | 30.8% |
| 0.0011 – 0.01 mi (up to 16 m) | 10 | 9.6% |
| 0.01 – 0.1 mi (up to 161 m) | 5 | 4.8% |
| 0.1 – 1 mi | 12 | 11.5% |
| > 1 mi | 45 | 43.3% |

**About 40% of the gaps are at or near the precision of the source itself.** NHPN
publishes record mileposts to three decimals, so 0.001 mi — 1.61 m — is the
finest distance the data can express. Thirty-two gaps are exactly one such
quantum: `284.440 → 284.441`, `97.209 → 97.210`, `81.180 → 81.181`. Two records
that abut exactly can still be recorded a quantum apart, and an exact-equality
test will always reject them.

That scale is not a coincidence. The 2026-08-13 connectivity audit reported
endpoint discontinuities "of 1.0 to 661 m". The 1.0 m end of that range is this
quantum.

**The other 43% are genuinely large** — 45 gaps over a mile, the largest 310 mi.
Those are a different phenomenon and this audit does not explain them.

## What follows, and what does not

**The predicate is not yet shown to be at fault.** The 2026-08-14 conclusion —
that the candidate set lacks joining records — remains possible for the large
gaps, but roughly 40% of the gaps that motivated it are artefacts of comparing
quantised mileposts exactly. The count of genuinely missing joins is smaller than
67 chain ends implied.

**Milepost adjacency needs a tolerance derived from the source, not a chosen
one.** 0.001 mi is what NHPN can express; asserting equality below that asks the
data for precision it does not carry. This audit does not change any adjacency
test — that is a lock-affecting decision — but it establishes the number such a
test would have to be derived from.

**The large gaps still need a probe.** Resolving whether a 310 mi hole is a
predicate miss, a route whose middle leaves the segment's states, or a key that
carries only part of a route requires querying NHPN for that milepost range
without the sign filter. That is an acquisition, and it is not made here.

## Scope limit, stated because it is easy to overread

This characterises adjacency **within** an LRS key. Mileposts are key-local, so
nothing here speaks to continuity where a route crosses from one key to another —
that is a geometric question, and it is what the original endpoint-connectivity
audit measured when it found six of twelve segments connected.

Concretely: `i15-salt-lake-to-cove-fort` key `000000001500003` contributes three
disjoint spans (0.000–0.909, 41.865–42.716, 351.475–400.592). The rest of that
segment's route is carried by its other ten keys, whose mileposts cannot be
compared with these. A per-key gap is not a hole in the road.

## Verification

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  audit-continental-milepost-gaps
```

Reads only the checksum-locked candidate lock and the response cache whose page
hashes that lock pins, through the same loader the edge-path derivation uses, so
a drifted cache fails rather than being characterised. Output:
`104 gaps, 32 within the 1.61 m source quantum, 45 over a mile`.

Four unit tests cover the span merge and the quantum constant.
