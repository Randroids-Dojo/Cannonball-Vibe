# P0-003 locked-source acquisition audit

- Date: 2026-07-16
- Task: P0-003
- Status: complete; protected Linux and Windows evidence recorded

## Findings and decisions

The official USDOT/BTS NHPN FeatureServer layer is the acquisition surface. It
publishes a stable `OBJECTID`, supports ID queries, ordering and pagination, and
states that the U.S. government work is available for unrestricted public use.
The BTS DOI remains the catalog landing surface; the exact public layer and
query URLs are locked for acquisition and license evidence.

NHPN acquisition snapshots the count and complete ID set before paging. It
sorts IDs, hashes the full request contract, fetches pages of at most 2,000 IDs,
deduplicates identical features, rejects conflicting duplicates, and reconciles
the count, ID set, pages and final feature set. Validated page responses are
atomically checkpointed; malformed pages are removed rather than poisoning
resume state. Retryable transport and ArcGIS errors use bounded backoff.

The production elevation baseline is the seamless USGS 3DEP 1/3 arc-second
GeoTIFF product because it provides full CONUS coverage at approximately
10-meter resolution. Per Q-014, a corridor may upgrade to locked 1-meter 3DEP
only after coverage, seam, visual/grade value, package-size, and acquisition-time
gates pass. The lock records the exact historical tile, TNM discovery
request and response hash, candidate count, deterministic selection policy,
product ID, publication date, raster and metadata URLs, response metadata, and
SHA-256 values. The locked FGDC metadata supplies NAD83 and NAVD88 explicitly;
the vertical datum is never inferred from the horizontal raster CRS.

CI uses a 48-KiB checked-in raster window and one official US-36 NHPN feature.
Both are recursively derived from separately locked raw responses. The lock
materializer fetches exact ancestors without discovery, verifies each download,
executes the recorded canonical-JSON or raster-window recipe, and verifies the
derived hash. A local replay rebuilt every checked-in artifact byte-for-byte,
including the crop from the 410,392,672-byte parent tile.

Schema 2 preserves route CRS, elevation CRS, horizontal and vertical datums,
product identity, source and elevation hashes, lock hash, elevation samples and
grades. The portable C# loader accepts schema 1 for compatibility and requires
complete, valid schema-2 provenance.

## Adversarial review

Three independent reviews challenged the acquisition, lock and runtime paths.
The review found and the implementation corrected:

- discarded runtime elevation samples;
- optional or unvalidated locks on elevation builds;
- raster metadata that was not bound to checked bytes or the lock;
- replay URLs that represented parents rather than derived bytes;
- incomplete artifact response metadata and dangling ancestry;
- checkpoint identities that omitted the endpoint and query contract;
- malformed pages checkpointed before semantic validation;
- rejection rather than deterministic deduplication of identical features;
- URL prefix checks vulnerable to path-suffix confusion;
- missing operational lock materialization.

The final adversarial pass reported no remaining acceptance-blocking findings.

## Human boundary

The technical gate did not itself approve public distribution rights. The
project owner resolved Q-013 on 2026-07-16 by approving distribution of the
exact locked NHPN and USGS 3DEP government data and project derivatives with
source credit, provenance, a no-endorsement statement, and no agency logos.
Product resolution was resolved by Q-014, and Q-015 selected content-addressed
GitHub Release assets for immutable source retention. The short human inbox is
[QUESTIONS_FOR_RANDROID.md](../QUESTIONS_FOR_RANDROID.md).

## Primary official references

- NHPN layer: <https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Highway_Planning_Network/FeatureServer/0>
- NHPN BTS landing page: <https://geodata.bts.gov/datasets/usdot::national-highway-planning-network/about>
- ArcGIS layer query documentation: <https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/>
- TNM Access API: <https://tnmaccess.nationalmap.gov/api/v1/docs>
- 3DEP products: <https://www.usgs.gov/3d-elevation-program/about-3dep-products-services>
- USGS datum guidance: <https://www.usgs.gov/faqs/what-projection-horizontal-datum-vertical-datum-and-resolution-usgs-digital-elevation-model>
