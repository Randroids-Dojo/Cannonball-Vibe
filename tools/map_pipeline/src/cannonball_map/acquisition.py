from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ArcGisTransport(Protocol):
    def post(self, url: str, form: dict[str, str]) -> dict[str, Any]: ...


class UrllibArcGisTransport:
    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds

    def post(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(form).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in {408, 429, 500, 502, 503, 504}:
                return {"error": {"code": error.code, "message": str(error)}}
            raise ValueError(f"ArcGIS HTTP request failed with status {error.code}.") from error


@dataclass(frozen=True)
class NhpnAcquisitionResult:
    expected_count: int
    object_ids: tuple[int, ...]
    features: tuple[dict[str, Any], ...]
    retries: int
    resumed_pages: int


def with_retries(
    operation: Callable[[], dict[str, Any]],
    *,
    attempts: int = 4,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    retries = 0
    for attempt in range(attempts):
        try:
            response = operation()
            if "error" in response:
                code = int(response["error"].get("code", 0))
                if code not in {408, 429, 500, 502, 503, 504}:
                    raise ValueError(f"ArcGIS request failed: {response['error']}")
                raise RuntimeError(f"retryable ArcGIS error {code}")
            return response, retries
        except (OSError, RuntimeError):
            if attempt + 1 == attempts:
                raise
            retries += 1
            sleep(min(0.25 * (2**attempt), 2.0))
    raise AssertionError("retry loop did not return")


def acquire_nhpn(
    transport: ArcGisTransport,
    query_url: str,
    query: dict[str, str],
    checkpoint_directory: Path,
    *,
    page_size: int = 2_000,
    attempts: int = 4,
    sleep: Callable[[float], None] = time.sleep,
) -> NhpnAcquisitionResult:
    if page_size <= 0 or page_size > 2_000:
        raise ValueError("NHPN page size must be between 1 and 2000.")
    checkpoint_directory.mkdir(parents=True, exist_ok=True)
    base = {**query, "f": "json"}
    count_response, retries = with_retries(
        lambda: transport.post(query_url, {**base, "returnCountOnly": "true"}),
        attempts=attempts,
        sleep=sleep,
    )
    expected = int(count_response["count"])
    ids_response, used = with_retries(
        lambda: transport.post(query_url, {**base, "returnIdsOnly": "true"}),
        attempts=attempts,
        sleep=sleep,
    )
    retries += used
    if ids_response.get("objectIdFieldName", "OBJECTID") != "OBJECTID":
        raise ValueError("NHPN service no longer uses OBJECTID as its stable identifier.")
    raw_ids = [int(value) for value in ids_response["objectIds"]]
    object_ids = sorted(set(raw_ids))
    if len(object_ids) != expected:
        raise ValueError(
            f"NHPN count reconciliation failed: count={expected}, ids={len(object_ids)}."
        )

    features: dict[int, dict[str, Any]] = {}
    resumed_pages = 0
    snapshot_sha256 = _canonical_sha256(object_ids)
    for page_index, start in enumerate(range(0, len(object_ids), page_size)):
        page_ids = object_ids[start : start + page_size]
        form = {
            "objectIds": ",".join(map(str, page_ids)),
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "returnZ": "false",
            "returnM": "false",
            "orderByFields": "OBJECTID ASC",
            "f": "json",
        }
        request_identity = _canonical_sha256(
            {
                "query_url": query_url,
                "base_query": query,
                "snapshot_sha256": snapshot_sha256,
                "page_form": form,
            }
        )
        checkpoint = checkpoint_directory / f"page-{page_index:06d}.json"
        page: dict[str, Any] | None = None
        downloaded = False
        if checkpoint.is_file():
            candidate = json.loads(checkpoint.read_text(encoding="utf-8"))
            response = candidate.get("response")
            if (
                candidate.get("request_sha256") == request_identity
                and isinstance(response, dict)
                and candidate.get("response_sha256") == _canonical_sha256(response)
            ):
                page = response
                resumed_pages += 1
        if page is None:
            page, used = with_retries(
                lambda form=form: transport.post(query_url, form),
                attempts=attempts,
                sleep=sleep,
            )
            retries += used
            downloaded = True
        try:
            page_features = _validate_page(page, page_ids)
        except (KeyError, TypeError, ValueError):
            checkpoint.unlink(missing_ok=True)
            raise
        for object_id, feature in page_features.items():
            existing = features.get(object_id)
            if existing is not None and _canonical_sha256(existing) != _canonical_sha256(feature):
                raise ValueError(f"NHPN returned conflicting duplicate OBJECTID {object_id}.")
            features[object_id] = feature
        if downloaded:
            record = {
                "request_sha256": request_identity,
                "response_sha256": _canonical_sha256(page),
                "response": page,
            }
            temporary = checkpoint.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(checkpoint)
    if sorted(features) != object_ids or len(features) != expected:
        raise ValueError("NHPN fetched features do not reconcile with the locked ID snapshot.")
    return NhpnAcquisitionResult(
        expected,
        tuple(object_ids),
        tuple(features[key] for key in sorted(features)),
        retries,
        resumed_pages,
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _validate_page(
    page: dict[str, Any],
    page_ids: list[int],
) -> dict[int, dict[str, Any]]:
    returned_ids: list[int] = []
    page_features: dict[int, dict[str, Any]] = {}
    for feature in page.get("features", []):
        object_id = int(feature["attributes"]["OBJECTID"])
        if object_id not in page_ids:
            raise ValueError(f"NHPN page returned unexpected OBJECTID {object_id}.")
        existing = page_features.get(object_id)
        if existing is not None:
            if _canonical_sha256(existing) != _canonical_sha256(feature):
                raise ValueError(f"NHPN returned conflicting duplicate OBJECTID {object_id}.")
            continue
        page_features[object_id] = feature
        returned_ids.append(object_id)
    if returned_ids != sorted(returned_ids):
        raise ValueError("NHPN page is not uniquely ordered by OBJECTID.")
    if set(returned_ids) != set(page_ids):
        raise ValueError("NHPN page did not return its complete locked ID slice.")
    return page_features
