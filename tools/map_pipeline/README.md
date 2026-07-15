# Cannonball map pipeline

This tool turns an explicitly approved public-domain line dataset into three
artifacts:

- `normalized.gpkg` for GIS inspection and corrections;
- `route_graph.json` for audits and diffs;
- `route_graph.cbrg` for the game runtime.

Every source file needs a sidecar manifest:

```json
{
  "source_id": "usdot-national-highway-planning-network",
  "publisher": "U.S. Department of Transportation",
  "source_url": "https://example.gov/exact-download",
  "acquired_on": "2026-07-14",
  "license_status": "public_domain",
  "license_evidence_url": "https://doi.org/10.21949/1518325",
  "sha256": "64-lowercase-hex-characters",
  "derived_from": []
}
```

Build with:

```bash
uv sync --locked
uv run cannonball-map validate-source --source route.gpkg --manifest route.manifest.json
uv run cannonball-map build --source route.gpkg --manifest route.manifest.json --output ../../data/processed
```

The pipeline fails closed on unknown licenses, OpenStreetMap ancestry, malformed
dates, missing hashes, changed files, disconnected selected geometry, and
duplicate directed edges.

Local JSONL telemetry can be summarized without a service:

~~~
uv run cannonball-map telemetry-summary --telemetry /path/to/prototype.jsonl
~~~
