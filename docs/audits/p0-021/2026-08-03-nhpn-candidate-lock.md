# P0-021 NHPN candidate-lock acquisition

- Local date: 2026-08-03
- Final lock generation: 2026-08-04T02:00:37Z
- Decision: ADR-0024
- Lock: `data/sources/continental-route-lock.json`
- Status: `nhpn_candidates_locked_3dep_pending`

## Outcome

The first continental acquisition stage queried the cataloged USDOT National
Highway Planning Network service for every NHPN-backed segment in the selected
route graph. Each selector includes the segment's declared states and checks
all three NHPN signed-route slots so a concurrent Interstate identity is not
lost merely because it is not locally primary.

The acquisition locked:

- 12 segment snapshots;
- 15,525 unique candidate `OBJECTID` values;
- sorted object-ID lists and hashes per segment;
- stable page membership and canonical response hashes;
- a canonical hash of the live service metadata;
- the source-catalog and route-selection input hashes; and
- zero network retries and 16 verified page resumptions during final lock
  regeneration after validator refinement.

The downloaded responses occupy 54.43 MB under ignored `.tools/` storage. No
continental source response or generated route package is committed.

## Locked identities

| Input | SHA-256 |
| --- | --- |
| Source catalog | `356a0fe4810a37bb5e5970bba3ae8295208908bc800e016c22e3b608bbb7c9eb` |
| Route selection | `00ac4df354a8644997a2a073ee07c736ff3f3bc2d2565c8cd9cb51b957d2ff2f` |
| Canonical service metadata | `5150b91eb2c736bbc2fc26666c6607365bb4b3608187ac459719a3a4e11f50b5` |
| Candidate union | `bb192757b04478758f282d8953f88fa919808cd5435201bfae3c31f8edcb7d44` |

## Validation boundary

This is a reproducible route-family candidate lock, not selected coast-to-coast
geometry. State-level signed-route queries intentionally include portions of a
facility outside the chosen transfer nodes and include both carriageway
directions where NHPN represents them separately.

The validator therefore:

- validates the partial lock by default;
- rejects missing segments, selector drift, unsorted or duplicate IDs, page
  reconciliation failures, catalog or route-selection drift, invalid hashes,
  and relaxed source policy;
- rejects `--require-complete` while the lock remains partial; and
- records 3DEP as pending exact path geometry instead of selecting a broad or
  opportunistic elevation superset.

The next stage must lock transfer-node coordinates, snap the NHPN candidates,
solve and audit exact connected westbound paths, and establish authored
connector bounds. Only those resolved bounds can drive exact 1/3 arc-second
3DEP product discovery and checksum locking.

## Sources

- [USDOT NHPN FeatureServer layer](https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_Planning_Network/FeatureServer/0)
- [USGS 3D Elevation Program](https://www.usgs.gov/3d-elevation-program)
- [USGS National Map product API](https://tnmaccess.nationalmap.gov/api/v1/products)
