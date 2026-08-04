# P0-021 continental transfer-node lock

- Local date: 2026-08-03
- Derivation time: 2026-08-04T03:51:27Z
- Decision: ADR-0024
- Policy: `data/routes/continental/transfer-node-policy.v1.json`
- Lock: `data/routes/continental/transfer-node-lock.v1.json`
- Status: `transfer_nodes_locked_exact_path_pending`

## Outcome

The second continental acquisition slice locked all 12 non-endpoint transfer
nodes used by the canonical Central Rockies path and its Northern Plains and
Southern I-40 alternatives. The derivation reads only the ignored NHPN response
cache created by the candidate-lock slice and verifies every response against
the committed per-page SHA-256 before using its geometry.

Nine facility-to-facility nodes use the midpoint of the nearest NHPN geometries
inside a bounded, versioned research window. The three transitions between an
authored endpoint connector and one NHPN facility snap the policy anchor to the
locked facility geometry. Every result records the contributing candidate
segment, NHPN `OBJECTID`, and exact page-response SHA-256.

All nine paired transfers reconcile within 24.401 meters; seven intersect in
the NHPN coarse geometry and two represent separated carriageway centerlines.
All derived anchors are within 5.502 meters of their policy search hints. The
lock validator checks the candidate and policy input hashes, node order and
coverage, source policy, CONUS bounds, separation gates, exact candidate IDs,
and each candidate's expected page hash without requiring downloaded data.

## Reproduction

With the ignored candidate cache present:

```bash
uv run --project tools/map_pipeline --frozen cannonball-map \
  derive-continental-transfers \
  data/routes/continental/transfer-node-policy.v1.json \
  --output data/routes/continental/transfer-node-lock.v1.json
```

On a clean checkout without the cache:

```bash
./scripts/validate-continental-route.sh
```

The repository-wide `scripts/check.sh` gate now runs the same cache-independent
candidate-lock and transfer-lock validation.

## Boundary

These coordinates are coarse-topology anchors, not lane centerlines, ramps, or
a claim that the final playable transfer geometry exists. The ignored NHPN
responses and any generated continental packages remain uncommitted. The next
slice must build a snapped graph around these anchors, reject disconnected or
ambiguous candidate components, and checksum-lock the exact westbound object
IDs. Authored endpoint connectors, 3DEP discovery, route reconstruction,
traversal, and the required human plausibility review remain open.

## Sources

The transfer policy references only the source IDs already locked in
`route-selection.v1.json`, including USDOT NHPN, FHWA, NJDOT, NDOT, UDOT,
TDOT, Caltrans, and the Port Authority of New York and New Jersey. No
OpenStreetMap-derived source is used.
