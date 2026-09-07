from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

from cannonball_map.acquisition import with_retries
from cannonball_map.atlas.io import (
    MAX_BYTES,
    MAX_RECORDS,
    IntakeError,
    canonical,
    decode_json,
    digest,
    read_bytes,
    read_json,
    source_allowed,
)
from cannonball_map.catalog import load_catalog, url_matches_prefix
from cannonball_map.manifest import compute_sha256


class AllowedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, prefixes: tuple[str, ...]):
        super().__init__()
        self.prefixes = prefixes

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not any(url_matches_prefix(newurl, prefix) for prefix in self.prefixes):
            raise IntakeError("redirect_blocked", "Redirect is outside the approved source URLs")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpTransport:
    def __init__(self, prefixes: tuple[str, ...]):
        self.prefixes = prefixes
        self.opener = urllib.request.build_opener(AllowedRedirects(prefixes))

    def get(self, url: str) -> tuple[bytes, dict]:
        if not any(url_matches_prefix(url, prefix) for prefix in self.prefixes):
            raise IntakeError("url_blocked", "Request URL is outside the approved catalog")
        request = urllib.request.Request(url, headers={"User-Agent": "Cannonball-Atlas-Intake/1"})
        try:
            with self.opener.open(request, timeout=30) as response:
                if response.status != 200:
                    raise IntakeError("http_status", f"Unexpected HTTP status {response.status}")
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise IntakeError("size_limit", "Response exceeds the acquisition byte bound")
                return payload, {
                    "status": response.status,
                    "final_url": response.url,
                    "content_type": response.headers.get("Content-Type", ""),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except urllib.error.HTTPError as error:
            if error.code in {408, 429, 500, 502, 503, 504}:
                raise RuntimeError(f"Retryable HTTP status {error.code}") from error
            raise IntakeError("http_status", f"HTTP request failed: {error.code}") from error


def acquire_snapshot(
    profile: dict,
    catalog: Path,
    output: Path,
    *,
    where: str | None = None,
    observed_on: str | None = None,
    transport=None,
) -> dict:
    source_allowed(profile, catalog)  # No network request or output before source admission.
    if observed_on and date.fromisoformat(observed_on) > datetime.now(UTC).date():
        raise IntakeError("observation_in_future", "Observation date is in the future")
    if profile.get("acquisition_mode") == "manual_reviewed_export":
        raise IntakeError("manual_export_required", "This profile needs a reviewed bounded export")
    if profile["format"] == "arcgis" and profile.get("crs", "EPSG:4326") != "EPSG:4326":
        raise IntakeError(
            "crs_mismatch", "ArcGIS acquisition emits EPSG:4326; set profile accordingly"
        )
    prefixes = load_catalog(catalog)[profile["source_id"]].allowed_url_prefixes
    transport = transport or HttpTransport(prefixes)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    retries = 0
    resumed = 0

    def response(url: str, *, phase: str = "", fresh: bool = False) -> tuple[bytes, str]:
        nonlocal retries, resumed
        if not any(url_matches_prefix(url, prefix) for prefix in prefixes):
            raise IntakeError("url_blocked", "Request is outside the catalog allowlist")
        identity = digest(
            {
                "url": url,
                "phase": phase,
                "profile": digest(profile),
                "observed_on": observed_on,
                "catalog": compute_sha256(catalog),
            }
        )
        key = f"{profile['id']}/response/{identity}"
        folder = output / "responses"
        folder.mkdir(exist_ok=True)
        raw_path = folder / f"{identity}.bin"
        meta_path = folder / f"{identity}.json"
        item = None
        if not fresh and raw_path.is_file() and meta_path.is_file():
            candidate = read_json(meta_path)
            if (
                candidate.get("id") == key
                and candidate.get("source_url") == url
                and candidate.get("sha256") == compute_sha256(raw_path)
            ):
                item = candidate
                resumed += 1
        if item is None:

            def operation():
                raw, metadata = transport.get(url)
                if len(raw) > MAX_BYTES:
                    raise IntakeError("size_limit", "Response exceeds the acquisition byte bound")
                if metadata.get("status") != 200 or not metadata.get("content_type"):
                    raise IntakeError("response_metadata", "Incomplete HTTP response metadata")
                if not any(
                    url_matches_prefix(metadata["final_url"], prefix) for prefix in prefixes
                ):
                    raise IntakeError("redirect_blocked", "Final URL is outside the allowlist")
                if profile["format"] == "arcgis":
                    parsed = decode_json(raw)
                    if parsed.get("error"):
                        return parsed
                    if parsed.get("exceededTransferLimit"):
                        raise IntakeError("incomplete_response", "ArcGIS response is truncated")
                    page_ids = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get(
                        "objectIds"
                    )
                    if page_ids:
                        expected = sorted(int(v) for v in page_ids[0].split(","))
                        returned = sorted(
                            f["attributes"][profile["id_field"]] for f in parsed.get("features", [])
                        )
                        if returned != expected:
                            raise IntakeError(
                                "incomplete_page", "ArcGIS page omitted/duplicated IDs"
                            )
                return {"raw": raw, "metadata": metadata}

            result, used = with_retries(operation)
            retries += used
            temporary = raw_path.with_suffix(".tmp")
            temporary.write_bytes(result["raw"])
            temporary.replace(raw_path)
            item = {
                "id": key,
                "path": raw_path.relative_to(output).as_posix(),
                "sha256": compute_sha256(raw_path),
                "source_id": profile["source_id"],
                "publisher": profile["publisher"],
                "license_status": profile["license_status"],
                "license_evidence_url": profile["license_evidence_url"],
                "source_url": url,
                "acquired_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "observed_on": observed_on,
                "origin": "acquired",
                "parents": [],
                "response_metadata": result["metadata"],
            }
            temporary = meta_path.with_suffix(".tmp")
            temporary.write_bytes(canonical(item))
            temporary.replace(meta_path)
        artifacts[key] = item
        return read_bytes(raw_path), key

    if profile["format"] == "arcgis":
        if not where or where.replace(" ", "").casefold() in {"1=1", "true"}:
            raise IntakeError("unbounded_query", "Supply an explicit corridor/route predicate")
        base_url = profile["url"].rstrip("/")

        def fetch(params: dict, *, phase: str = "", fresh: bool = False, metadata=False):
            url = base_url + ("?" if metadata else "/query?") + urllib.parse.urlencode(params)
            raw, _ = response(url, phase=phase, fresh=fresh)
            payload = decode_json(raw)
            if payload.get("error") or payload.get("exceededTransferLimit"):
                raise IntakeError(
                    "incomplete_response", "ArcGIS returned an error or truncated page"
                )
            return payload

        meta = fetch({"f": "json"}, phase="before", fresh=True, metadata=True)
        id_field = profile["id_field"]
        actual_id = meta.get("objectIdField", meta.get("objectIdFieldName"))
        if actual_id != id_field or id_field not in {f["name"] for f in meta["fields"]}:
            raise IntakeError("service_schema_drift", "ArcGIS stable ID field changed")
        requested_fields = {path.split(".")[0] for path in profile["fields"].values()}
        if not requested_fields <= {f["name"] for f in meta["fields"]}:
            raise IntakeError("service_schema_drift", "Mapped ArcGIS source fields are missing")
        query = {"f": "json", "where": where}
        count = fetch({**query, "returnCountOnly": "true"}, phase="before", fresh=True)["count"]
        if type(count) is not int or count < 0 or count > MAX_RECORDS:
            raise IntakeError("record_limit", "ArcGIS query exceeds the bounded record limit")
        snapshot = fetch({**query, "returnIdsOnly": "true"}, phase="before", fresh=True)
        ids = snapshot.get("objectIds") or []
        if (
            snapshot.get("objectIdFieldName") != id_field
            or any(type(value) is not int for value in ids)
            or len(set(ids)) != count
        ):
            raise IntakeError("id_count_mismatch", "ArcGIS count and unique IDs do not reconcile")
        ids = sorted(ids)
        if len(ids) != count:
            raise IntakeError("id_count_mismatch", "ArcGIS ID snapshot contains duplicates")
        features = []
        feature_bytes = 0
        page_size = min(500, int(meta.get("maxRecordCount", 500)))
        if page_size < 1:
            raise IntakeError("service_schema_drift", "Invalid ArcGIS page size")
        for start in range(0, count, page_size):
            page_ids = ids[start : start + page_size]
            page = fetch(
                {
                    "f": "json",
                    "objectIds": ",".join(map(str, page_ids)),
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "returnZ": "false",
                    "returnM": "false",
                    "orderByFields": f"{id_field} ASC",
                },
                phase=digest({"where": where, "ids": ids, "metadata": meta}),
                fresh=not bool(meta.get("editingInfo", {}).get("lastEditDate")),
            )
            returned = [f["attributes"][id_field] for f in page["features"]]
            if sorted(returned) != page_ids:
                raise IntakeError("incomplete_page", "ArcGIS page omitted or duplicated locked IDs")
            feature_bytes += len(canonical(page["features"]))
            if feature_bytes > MAX_BYTES - 1024:
                raise IntakeError("size_limit", "Assembled snapshot exceeds the byte limit")
            features.extend(page["features"])
        after_ids = fetch({**query, "returnIdsOnly": "true"}, phase="after", fresh=True)
        after_meta = fetch({"f": "json"}, phase="after", fresh=True, metadata=True)
        if (
            sorted(after_ids.get("objectIds") or []) != ids
            or meta.get("editingInfo") != after_meta.get("editingInfo")
            or meta["fields"] != after_meta["fields"]
        ):
            raise IntakeError(
                "service_drift", "ArcGIS changed during acquisition; no snapshot emitted"
            )
        payload = canonical(
            {
                "spatialReference": {"wkid": 4326},
                "features": sorted(features, key=lambda f: f["attributes"][id_field]),
            }
        )
        path = output / "dataset.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
        item = {
            "id": f"{profile['id']}/dataset",
            "path": path.name,
            "sha256": compute_sha256(path),
            "source_id": profile["source_id"],
            "publisher": profile["publisher"],
            "license_status": profile["license_status"],
            "license_evidence_url": profile["license_evidence_url"],
            "source_url": profile["url"],
            "acquired_at": max(a["acquired_at"] for a in artifacts.values()),
            "observed_on": observed_on,
            "origin": "derived",
            "value_class": "observed",
            "process_reference": "ADR-0028: bounded ArcGIS ID snapshot assembly v1",
            "parents": sorted(artifacts),
            "response_metadata": {},
            "source_consistency": "ID set, available edit stamp and schema checked before/after",
        }
    else:
        # Generic URLs can be mutable. Locked offline replay uses the artifact bundle;
        # a new acquisition refreshes the provider response rather than caching forever.
        _, key = response(profile["url"], fresh=True)
        item = artifacts[key]
    artifacts[item["id"]] = item
    result = {
        "schema_version": 1,
        "profile_id": profile["id"],
        "artifact_id": item["id"],
        "catalog_sha256": compute_sha256(catalog),
        "profile_sha256": digest(profile),
        "artifacts": [artifacts[key] for key in sorted(artifacts)],
    }
    temporary = output / "artifacts.json.tmp"
    temporary.write_bytes(canonical(result))
    temporary.replace(output / "artifacts.json")
    return {
        "manifest": str(output / "artifacts.json"),
        "artifact_id": item["id"],
        "manifest_sha256": compute_sha256(output / "artifacts.json"),
        "retries": retries,
        "resumed_responses": resumed,
    }
