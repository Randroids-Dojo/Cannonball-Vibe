# Continental route-selection research

- Date: 2026-07-31
- Decision: ADR-0024
- Machine-readable result: `data/routes/continental/route-selection.v1.json`
- Delivery owner: P0-021

## Outcome

The selected graph is westbound from a public-road portal adjacent to the
historic East 31st Street reference in Manhattan to a public-road portal on
Portofino Way in Redondo Beach.

| Role | Selected facility spine | Principal distinction |
| --- | --- | --- |
| Canonical | Lincoln Tunnel, I-80, I-76, I-70, I-15, I-10, I-405 | Central Rockies, existing Colorado investment, maximum terrain contrast |
| Northern alternative | Lincoln Tunnel, I-80, I-15, I-10, I-405 | Wyoming exposure and Wasatch approach instead of I-70 mountain passes |
| Southern alternative | Holland Tunnel, I-78, I-81, I-40, I-15, I-10, I-405 | Appalachia, mid-South, southern plains, and Southwest; merges at Barstow |

## Authoritative findings

- FHWA's January 2026 main-route log confirms the selected Interstate
  facilities and the states and principal cities they serve. It identifies
  I-80, I-40, and I-70 among the five longest Interstate routes and records
  I-80 from San Francisco to Teaneck, I-40 from Barstow to Wilmington, and
  I-70 from Cove Fort to Baltimore.
- FHWA records I-76 in Nebraska and Colorado, I-78 in New York, New Jersey, and
  Pennsylvania, and I-81 from Tennessee through Pennsylvania and New York.
  These records support the selected route-family continuity but are not a
  touring guide or lane-level geometry source.
- Nebraska DOT mapping identifies the I-80/I-76 branch at Big Springs. Utah DOT
  material identifies the I-70/I-15 Cove Fort interchange. Tennessee DOT's
  I-40/I-81 corridor study covers both complete Tennessee corridors. Caltrans
  mapping covers the I-40, I-15, I-10, I-405, and CA 107 finish approach.
- The U.S. Census geocoder matched both reference addresses. The resulting
  coordinates are address-match anchors only, not lane, curb, driveway, or
  portal geometry.

## Product rationale

The central route is canonical because it gives the MVP the strongest sequence
of region and driving-risk changes while using the representative Colorado
pipeline and environment investment already present in the repository. The
northern path makes the Big Springs decision meaningful without introducing a
second endpoint. The southern path diverges from Manhattan and stays distinct
until Barstow, producing the major graph alternative required by the GDD.

The shared Los Angeles approach is deliberate. Building three redundant urban
finishes would add substantial source, interchange, sign, traffic, and art work
without a comparable route-choice benefit.

## Evidence boundaries

This research locks route policy, facility order, reference endpoints, and the
three path identities. It does **not** establish:

- exact geographic distance;
- a locked NHPN object-ID set or any 3DEP tiles;
- lane, ramp, interchange, or endpoint-connector geometry;
- current closure, toll, construction, or seasonal availability;
- sign text, exits, milepoints, services, or enforcement parameters;
- drivability, package reproducibility, performance, or save/resume results;
- permission to enter private property or use private marks; or
- the required human coast-to-coast completion and geographic review.

Those facts belong to P0-021 acquisition, reconstruction, validation, and human
qualification. Continental downloads and generated packages remain cached or
release artifacts and must not be committed.

## Sources consulted

- [FHWA Interstate Route Log, Table 1](https://www.fhwa.dot.gov/planning/national_highway_system/interstate_highway_system/routefinder/table01.cfm)
- [USDOT National Highway Planning Network service](https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_Planning_Network/FeatureServer/0)
- [Port Authority bridges and tunnels](https://www.panynj.gov/bridges-tunnels/en/index.html)
- [NJDOT straight-line diagrams](https://www.nj.gov/transportation/refdata/sldiag/)
- [NJDOT Route 3/Route 495 transfer study](https://www.nj.gov/transportation/uploads/comm/pubmeet/details/Handbook_20210803_074328_2021-08-01PICHandoutRt3-495.pdf)
- [Nebraska DOT right-of-way index map](https://dot.nebraska.gov/media/jvgp1f2k/row-plan-index-map.pdf)
- [Utah DOT clearance and Interstate reference map](https://www.udot.utah.gov/connect/wp-content/uploads/sites/50/2019/11/Map14ft6inUpdated.pdf)
- [Tennessee DOT I-40/I-81 corridor study](https://www.tn.gov/tdot/government/g/planning-studies/i-40-81-multimodal-corridor-study.html)
- [Caltrans statewide district route map](https://dot.ca.gov/-/media/dot-media/programs/traffic-operations/documents/trucks/busmap-d1-d12-v3-a11y.pdf)
- [U.S. Census geocoder](https://geocoding.geo.census.gov/geocoder/)
- [Portofino Hotel address page](https://www.hotelportofino.com/contact/)
- [Cannonball Dino historical account](https://www.cannonballdino.com/explore-the-story)
