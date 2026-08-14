# P0-021 break contiguity: the candidate set is missing corridor

Date: 2026-08-14

Task: P0-021; stage `exact-westbound-path-solve`

Artifact: `data/routes/continental/edge-path-lock.v1.json`

Follows [the carriageway-finding correction](2026-08-14-nhpn-connectivity-audit-correction.md),
whose structural conclusion stands and whose explanation of the breaks is
corrected here.

## What this corrects

The correction published earlier today established that each segment is a
near-linear chain, not paired carriageways. That holds. It then explained the
components as places where *consecutive records do not share an endpoint within
the snapping tolerance*, and said the breaks were "endpoint discontinuities of
metres to hundreds of metres rather than missing corridor".

**That explanation was unsupported, and it is backwards.**

It rested on the distances between nearby chain ends. Proximity is not adjacency:
two unrelated parts of one route pass within metres of each other routinely. On
`i70-denver-to-cove-fort` the two chain ends 5.82 m apart belong to records at
mileposts 280.4 and 4.9 of the same LRS section — nowhere near each other along
the road.

## The test that settles it

Two chain ends are adjacent only if one record's `END_POINT` equals the other's
`BEGIN_POIN` on the same `LRSKEY`. Applying that across all twelve segments:

| Segment | Chain ends | Milepost-contiguous record pairs |
| --- | ---: | ---: |
| i80-new-jersey-to-big-springs | 7 | 2 |
| i80-big-springs-to-salt-lake | 4 | 1 |
| all ten others | 56 | 0 |
| **total** | **67** | **3** |

**Only 3 of the breaks are two records that merely missed each other.** For the
rest, the candidate set does not contain the records that would join the chain.
The corridor is missing from the acquisition, not misaligned within it.

## Why this changes the next stage again

The earlier framing implied a bridging policy: decide, per gap, whether a
discontinuity of 1 m or 661 m may be closed. That question applies to at most
three breaks.

The real question is why the locked candidate set lacks the connecting records.
The acquisition predicate selects signed Interstate route-family records within a
declared list of state FIPS codes, so a record carrying a different signed route,
a different route-family qualifier, or a jurisdiction outside the declared list
would not have been returned even though the corridor runs through it. That is a
hypothesis this audit does not test; establishing it is the next stage's work and
it may require re-acquisition rather than reconstruction.

No bridging is performed here, and ADR-0018 continues to forbid inventing
connectivity the source does not assert.

## Two measurement errors found while producing this

Both were caught by cross-checking rather than by review, and both are recorded
because the pattern matters more than the individual bugs.

**The contiguity test first read the wrong field.** It used `BEGMP` and `ENDMP`,
which describe the LRS *section* a record belongs to and are shared by every
consecutive record in it — the identical mistake that produced the withdrawn
carriageway finding, repeated in the code written to correct it. It surfaced
because the implementation reported 11 contiguous pairs while a standalone probe
reported 3. The record's own extent is `BEGIN_POIN` and `END_POINT`; both are now
carried under names that state which is which, with a regression test that fails
if the section extent is used again.

**The metric then over-counted.** It compared endpoint pairs while testing record
adjacency, so a record with both ends dangling was counted once per endpoint
combination. Real data hid this because such records are rare; a synthetic test
with two short chains exposed it as 4 where 1 was correct. It now counts distinct
record pairs.

The general lesson, three times over in one task: a statistic that agrees with
expectation is not evidence, and consistency across many inputs is not
corroboration when the key itself is wrong. The cheap check — reading the records
the metric claims are related — catches all three.
