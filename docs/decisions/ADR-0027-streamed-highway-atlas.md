# ADR-0027: Streamed 2D highway atlas

- Status: Proposed
- Date: 2026-09-06
- Task: P1-016; open question: Q-045
- Authority: owner request to research and design a realistic, readable,
  entirely streamed 2D map of the game's selected highways. This authorizes
  the design investigation; source admission and production readiness are not
  established by the request.
- Extends if accepted: ADR-0011 map presentation and packaging.
- Preserves: ADR-0002 source policy, ADR-0017 route-context truth, ADR-0018
  reconstruction gates, ADR-0019 package ceilings, ADR-0024 selected routes,
  ADR-0026 restrictions on source use, and the solo pause decision.

## Context

The existing P0-013 map provides authoritative progress, paths and semantic
markers with a bounded simplified-geometry payload. Its three embedded LODs and
8x maximum zoom cannot supply a realistic geographic atlas with independently
streamed labels, background context and detailed interchanges.

The [design audit](../audits/2026-09-06-streamed-highway-map-design.md) identifies
the three route families, existing implementation, candidate data sources,
verified exit/service metadata gaps, zoom behavior, contract boundaries,
streaming lifecycle and proposed pilot measurements.

## Proposed decision

1. Present a geographic vector atlas in the existing Godot UI, using the complete
   union of ADR-0024's supported roads. Give nearby places, water, boundaries and
   terrain enough context to read the route, while limiting detailed road data
   to selected facilities, their validated ramps, authored connectors and
   playable service access. Context-only roads never add graph connectivity.
2. Compile an independent spatial map tile pyramid offline with the existing
   Python/PROJ toolchain and versioned FlatBuffer readers. Load every geographic
   layer on demand, including the overview. Keep only a bounded manifest and
   spatial directory path resident before tile requests; stream search/feature
   records independently as needed.
3. Use EPSG:3857/XYZ for proposed display tiling, with a 512-logical-pixel
   reference tile. Retain the route pipeline's existing metric/geodetic
   contracts. Compute trip distances from authoritative route state and scale
   bars geodesically. Convert doubles to floats only after subtracting the map
   camera origin, independently of 3D world rebasing.
4. Keep labels and shields in screen space with deterministic candidate IDs,
   cross-tile collision layout, stable zoom transitions and accessible feature
   selection. Preserve all concurrent route identities, local milepoint systems,
   exit suffixes/directions, observed/derived/authored distinctions and unknowns.
5. Bind the atlas to the route/semantic content version. A subsequent schema
   change adds an explicit atlas-reference mode that moves map geometry out of
   new root packages. Legacy schema-5 map payloads retain their existing rules;
   unsupported readers reject new content clearly. Do not assign a schema
   version or edit generated code in this design slice.
6. Use separate map CPU, GPU, metadata and in-flight budgets, background reads
   and validation, bounded main-thread attachment, parent-tile fallback, byte-
   weighted eviction, cancellation, retry limits and corruption recovery. Never
   reconstruct an atlas from loaded 3D chunks or synchronously fetch an entire
   country payload. Preserve the current root/chunk ceilings in ADR-0019.
7. Prefer complete local installation with on-demand memory streaming for the
   first production atlas. A network backend may later deliver the same immutable
   chunks without changing navigation semantics. No hosted provider or payment
   is selected. Public government services are offline acquisition sources only.
8. Propose cataloging Census non-road boundaries/places, USGS GNIS and selected
   hydrography products after exact artifact rights and recursive ancestry checks.
   This proposed ADR makes no catalog change and grants no TIGER road-geometry
   use beyond ADR-0026. Keep NHPN/NHS/reconstruction authoritative for roads;
   3DEP remains the selected elevation family. Inventory real exits and services
   separately under ADR-0017; unresolved values cannot be invented from mileage.
9. Prove the pilot and complete-graph gates in P1-016 before claiming realistic
   coverage. New map comprehension/accessibility review and final source/asset
   rights review remain human gates. P0-013's historical approval is preserved.

## Alternatives and consequences

- PMTiles/MVT with MapLibre is a comparison option if the native approach fails
  a declared gate. No Godot integration was validated here, and no selected tool
  is replaced without evidence and a superseding decision. The PMTiles format
  is distinct from the incompatible OSM-derived Protomaps basemap.
- Raster relief tiles remain useful beneath independently rendered text. A
  raster-only labeled atlas cannot meet the desired text scaling, interaction
  and semantic selection behavior well.
- Catalog additions require coordinated downstream lock updates; this design
  must not trigger them incidentally. Tile bytes remain build/release artifacts,
  while source locks, provenance and audit evidence remain reviewable.
- Native cartographic labeling and corridor semantic curation are explicit new
  engineering/content work. Neither a working tile loader nor a sharper line
  makes missing real exit/service information complete.
- Pilot residency and latency values in the audit are hypotheses. They do not
  tighten ADR-0019 ceilings or ratify production allocations under ADR-0023.

## Acceptance disposition

Q-045 is open. Merging this proposed record preserves a reviewable design; it
does not change its status to Accepted, admit a source, or complete P1-016.
