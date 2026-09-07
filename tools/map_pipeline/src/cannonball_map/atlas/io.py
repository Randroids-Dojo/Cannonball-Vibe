from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from cannonball_map.catalog import load_catalog, require_catalog_source
from cannonball_map.manifest import SourceManifest, compute_sha256, validate_source

MAX_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 100_000


class IntakeError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise IntakeError("invalid_json", f"Repeated JSON key: {key}")
        result[key] = value
    return result


def decode_json(raw: bytes | str) -> Any:
    def reject(value: str) -> None:
        raise IntakeError("invalid_json", f"Non-finite JSON value: {value}")

    return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=reject)


def read_bytes(path: Path, *, decompress: bool = False) -> bytes:
    if path.stat().st_size > MAX_BYTES:
        raise IntakeError("size_limit", f"Artifact exceeds {MAX_BYTES} bytes: {path.name}")
    opener = gzip.open if decompress and path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise IntakeError("size_limit", "Decoded artifact exceeds the byte limit")
    return raw


def read_json(path: Path) -> dict:
    result = decode_json(read_bytes(path))
    if not isinstance(result, dict):
        raise IntakeError("invalid_document", f"Expected a JSON object: {path.name}")
    return result


def versioned(path: Path) -> dict:
    result = read_json(path)
    if type(result.get("schema_version")) is not int or result["schema_version"] != 1:
        raise IntakeError("schema_version", f"Unsupported schema version: {path.name}")
    return result


def locked_path(base: Path, ref: dict) -> Path:
    path = (base / ref["path"]).resolve()
    expected = ref["sha256"]
    if not isinstance(expected, str) or len(expected) != 64 or compute_sha256(path) != expected:
        raise IntakeError("hash_mismatch", f"Input checksum does not match: {path.name}")
    return path


def utc_timestamp(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise IntakeError("acquisition_time", "Acquisition timestamps must specify UTC")
    return stamp


def source_allowed(profile: dict, catalog_path: Path) -> None:
    if profile["license_status"] != "public_domain":
        raise IntakeError("license_blocked", f"{profile['id']}: public_domain is required")
    try:
        require_catalog_source(
            load_catalog(catalog_path),
            source_id=profile["source_id"],
            publisher=profile["publisher"],
            license_status=profile["license_status"],
            source_url=profile["url"],
            license_evidence_url=profile["license_evidence_url"],
        )
    except ValueError as error:
        raise IntakeError("catalog_blocked", str(error)) from error
    if (
        profile["source_id"] == "usdot-national-highway-planning-network"
        and profile["kind"] != "road"
    ):
        raise IntakeError("source_use_blocked", "NHPN cannot supply observed exit/service data")
    if profile["source_id"] in {"usda-naip", "usgs-3dep"}:
        raise IntakeError("source_use_blocked", "Imagery/elevation are not atlas semantic records")


class Provenance:
    def __init__(self, bundles: list[Path], catalog: Path, as_of: date):
        self.catalog = catalog
        self.as_of = as_of
        self.items: dict[str, dict] = {}
        self.paths: dict[str, Path] = {}
        self.checked: set[str] = set()
        for bundle in bundles:
            for item in versioned(bundle)["artifacts"]:
                key = item["id"]
                if key in self.items:
                    raise IntakeError("duplicate_artifact", f"Repeated artifact ID: {key}")
                self.items[key] = item
                self.paths[key] = (bundle.parent / item["path"]).resolve()

    def validate(self, key: str, active: frozenset[str] = frozenset()) -> dict:
        if key in active:
            raise IntakeError("ancestry_cycle", f"Ancestry cycle at {key}")
        if key not in self.items:
            raise IntakeError("missing_ancestor", f"Missing artifact/ancestor: {key}")
        item = self.items[key]
        if key in self.checked:
            return item
        try:
            stamp = utc_timestamp(item["acquired_at"])
            if stamp.date() > self.as_of:
                raise IntakeError("future_acquisition", f"{key} was acquired after the audit date")
            parents = item["parents"]
            origin = item["origin"]
            if not isinstance(parents, list) or len(set(parents)) != len(parents):
                raise IntakeError("invalid_ancestry", f"{key}: parents must be unique IDs")
            if origin not in {"acquired", "derived", "authored"}:
                raise IntakeError("invalid_ancestry", f"{key}: unknown origin")
            if origin != "acquired" and (not parents or not item.get("process_reference")):
                raise IntakeError(
                    "invalid_ancestry", f"{key}: derivation needs parents and process"
                )
            response = item["response_metadata"]
            if origin == "acquired" and (parents or response.get("status") != 200):
                raise IntakeError("response_metadata", f"{key}: invalid acquired response")
            if origin == "acquired" and not response.get("content_type"):
                raise IntakeError("response_metadata", f"{key}: content type is required")
            for parent in parents:
                self.validate(parent, active | {key})
            path = self.paths[key]
            read_bytes(path)  # Enforce the same input bound on non-JSON formats and ancestors.
            manifest = SourceManifest(
                item["source_id"],
                item["publisher"],
                item["source_url"],
                stamp.date().isoformat(),
                item["license_status"],
                item["license_evidence_url"],
                item["sha256"],
                tuple(item.get("derived_from", [])),
            )
            validate_source(manifest, path, self.catalog)
            if origin == "acquired":
                require_catalog_source(
                    load_catalog(self.catalog),
                    source_id=item["source_id"],
                    publisher=item["publisher"],
                    license_status=item["license_status"],
                    source_url=response["final_url"],
                    license_evidence_url=item["license_evidence_url"],
                )
        except IntakeError:
            raise
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise IntakeError("provenance_invalid", f"{key}: {error}") from error
        self.checked.add(key)
        return item

    def roots(self, key: str) -> set[tuple[str, str]]:
        item = self.validate(key)
        if not item["parents"]:
            return {(item["source_id"], item["source_url"].split("?")[0])}
        return set().union(*(self.roots(parent) for parent in item["parents"]))


def get_field(row: dict, path: str | None) -> Any:
    value: Any = row
    for part in (path or "").split("."):
        if isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple)):
        return bool(value) and any(
            has_value(v) for v in (value.values() if isinstance(value, dict) else value)
        )
    return True


def validate_values(values: dict) -> None:
    for key in ("name", "destination", "route", "category", "direction"):
        value = values.get(key)
        if has_value(value) and not (
            isinstance(value, str)
            or isinstance(value, list)
            and all(isinstance(v, str) for v in value)
        ):
            raise IntakeError("field_type_invalid", f"{key} must be text or a list of text")
    number = values.get("exit_number")
    if has_value(number):
        if isinstance(number, str):
            pass  # Preserve leading zeroes and suffixes from text sources.
        elif (
            type(number) is int
            or type(number) is float
            and math.isfinite(number)
            and number.is_integer()
        ):
            values["exit_number"] = str(int(number))
        else:
            raise IntakeError("field_type_invalid", "Exit number must be a label or whole number")
    for key in ("lanes", "truck_parking", "toll_amount", "milepost"):
        if not has_value(values.get(key)):
            continue
        value = values[key]
        if isinstance(value, bool):
            raise IntakeError("field_type_invalid", f"{key} must be numeric")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as error:
            raise IntakeError("field_type_invalid", f"{key} must be numeric") from error
        if not math.isfinite(numeric) or key != "milepost" and numeric < 0:
            raise IntakeError("field_type_invalid", f"{key} is out of range")
        if key in {"lanes", "truck_parking"} and not numeric.is_integer():
            raise IntakeError("field_type_invalid", f"{key} must be a whole number")


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(val) for val in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def feature_entries(features, *, arcgis: bool = False):
    for feature in features:
        if not isinstance(feature, dict) or not arcgis and feature.get("type") != "Feature":
            raise IntakeError("invalid_record", "Expected a feature object")
        row = feature.get("attributes" if arcgis else "properties")
        if not isinstance(row, dict):
            raise IntakeError("invalid_record", "Feature properties must be an object")
        yield row, feature.get("geometry")


def records(path: Path, profile: dict):
    """Yield raw properties/geometry pairs; normalization handles per-record errors."""
    fmt = profile["format"]
    crs = profile.get("crs", "EPSG:4326")
    if fmt in {"geopackage", "geoparquet"}:
        if "crs" not in profile:
            raise IntakeError("crs_unknown", "Spatial file profiles must declare their CRS")
        if path.stat().st_size > MAX_BYTES:
            raise IntakeError(
                "size_limit", "Spatial file exceeds the byte limit; subset it offline"
            )
        if fmt == "geopackage":
            import geopandas as gpd

            frame = gpd.read_file(path, layer=profile["layer"], rows=MAX_RECORDS + 1)
            if frame.crs is None or not CRS(frame.crs).equals(CRS(crs)):
                raise IntakeError("crs_mismatch", "GeoPackage CRS differs from the profile")
            if len(frame) > MAX_RECORDS:
                raise IntakeError("record_limit", "Spatial file exceeds the record limit")
            for _, row in frame.iterrows():
                geom = row.geometry
                yield (
                    clean(row.drop(frame.geometry.name).to_dict()),
                    (mapping(geom) if geom is not None else None),
                )
        else:
            import duckdb
            from shapely import from_wkb

            with duckdb.connect(config={"memory_limit": "256MB", "threads": "1"}) as conn:
                metadata = conn.execute(
                    "SELECT key, value FROM parquet_kv_metadata(?)", [str(path)]
                ).fetchall()
                for key, value in metadata:
                    if bytes(key) == b"geo":
                        geo = decode_json(bytes(value))
                        column = profile.get("geometry_field", "geometry")
                        declared = geo["columns"][column].get("crs", "OGC:CRS84")
                        if declared is None or not CRS(declared).equals(
                            CRS(crs), ignore_axis_order=True
                        ):
                            raise IntakeError(
                                "crs_mismatch", "GeoParquet CRS differs or is unknown"
                            )
                result = conn.execute(
                    "SELECT * FROM read_parquet(?) LIMIT ?", [str(path), MAX_RECORDS + 1]
                )
                names = [col[0] for col in result.description]
                count = 0
                while rows := result.fetchmany(1024):
                    for values in rows:
                        count += 1
                        if count > MAX_RECORDS:
                            raise IntakeError("record_limit", "Parquet exceeds the record limit")
                        row = dict(zip(names, values, strict=True))
                        raw_geom = row.pop(profile.get("geometry_field", "geometry"), None)
                        geom = from_wkb(raw_geom) if raw_geom is not None else None
                        yield clean(row), mapping(geom) if geom is not None else None
        return
    raw = read_bytes(path, decompress=True)
    if fmt == "csv":
        rows = csv.DictReader(
            io.StringIO(raw.decode("utf-8-sig")), delimiter=profile.get("delimiter", ",")
        )
        if not rows.fieldnames or len(set(rows.fieldnames)) != len(rows.fieldnames):
            raise IntakeError("schema_drift", "CSV headers are missing or duplicated")
        entries = ((row, None) for row in rows)
    elif fmt == "ndjson":
        entries = feature_entries(decode_json(line) for line in raw.splitlines() if line.strip())
    elif fmt in {"geojson", "arcgis"}:
        payload = decode_json(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise IntakeError("invalid_document", "Dataset features must be an array")
        if "error" in payload or payload.get("exceededTransferLimit"):
            raise IntakeError("incomplete_response", "ArcGIS error or truncated response")
        if fmt == "geojson" and payload.get("type") != "FeatureCollection":
            raise IntakeError("invalid_geojson", "Expected a FeatureCollection")
        if fmt == "geojson" and payload.get("crs"):
            declared = payload["crs"].get("properties", {}).get("name")
            if declared is None or not CRS(declared).equals(CRS(crs), ignore_axis_order=True):
                raise IntakeError("crs_mismatch", "GeoJSON CRS differs from the profile")
        if fmt == "arcgis":
            sr = payload.get("spatialReference", {})
            wkid = sr.get("latestWkid", sr.get("wkid"))
            if wkid and not CRS(f"EPSG:{3857 if wkid == 102100 else wkid}").equals(CRS(crs)):
                raise IntakeError("crs_mismatch", "ArcGIS response CRS differs from the profile")
        entries = feature_entries(payload["features"], arcgis=fmt == "arcgis")
    else:
        raise IntakeError("unsupported_format", f"Unsupported adapter: {fmt}")
    for count, (row, geom) in enumerate(entries, 1):
        if count > MAX_RECORDS:
            raise IntakeError("record_limit", "Record limit exceeded; acquire smaller subsets")
        if not isinstance(row, dict) or None in row:
            raise IntakeError("invalid_record", "Record properties must be an object")
        yield row, geom


def geometry(row: dict, raw: dict | None, profile: dict) -> dict | None:
    if raw is None and profile.get("longitude_field"):
        lon = get_field(row, profile["longitude_field"])
        lat = get_field(row, profile["latitude_field"])
        if lon not in (None, "") or lat not in (None, ""):
            raw = {"type": "Point", "coordinates": [float(lon), float(lat)]}
    if raw is None:
        return None
    if profile["format"] == "arcgis":
        if "x" in raw and "y" in raw:
            raw = {"type": "Point", "coordinates": [raw["x"], raw["y"]]}
        elif "paths" in raw:
            raw = {"type": "MultiLineString", "coordinates": raw["paths"]}
        else:
            raise IntakeError("geometry_invalid", "Export ArcGIS polygons as GeoJSON")
    canonical(raw)  # Reject non-finite coordinates before GEOS/PROJ.
    geom = shape(raw)
    if geom.is_empty or not geom.is_valid:
        raise IntakeError("geometry_invalid", "Empty or invalid source geometry")
    crs = CRS(profile.get("crs", "EPSG:4326"))
    if not crs.equals(CRS("EPSG:4326")):
        converter = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        geom = transform(lambda x, y, z=None: converter.transform(x, y, errcheck=True), geom)
    bounds = geom.bounds
    if (
        not all(math.isfinite(v) for v in bounds)
        or bounds[0] < -180
        or bounds[2] > 180
        or bounds[1] < -90
        or bounds[3] > 90
        or not geom.is_valid
    ):
        raise IntakeError("geometry_invalid", "Geometry is outside valid longitude/latitude bounds")
    return json.loads(canonical(mapping(geom)))
