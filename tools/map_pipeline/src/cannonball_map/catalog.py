from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class CatalogSource:
    source_id: str
    publisher: str
    license_status: str
    license_evidence_url: str
    allowed_url_prefixes: tuple[str, ...]
    raw: dict[str, Any]


def load_catalog(path: Path) -> dict[str, CatalogSource]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, CatalogSource] = {}
    for item in payload.get("sources", []):
        source = CatalogSource(
            source_id=item["id"],
            publisher=item["publisher"],
            license_status=item["license_status"],
            license_evidence_url=item["license_evidence_url"],
            allowed_url_prefixes=tuple(item["allowed_url_prefixes"]),
            raw=item,
        )
        if source.source_id in result:
            raise ValueError(f"Catalog repeats source ID '{source.source_id}'.")
        result[source.source_id] = source
    if not result:
        raise ValueError("Source catalog contains no sources.")
    return result


def require_catalog_source(
    catalog: dict[str, CatalogSource],
    *,
    source_id: str,
    publisher: str,
    license_status: str,
    source_url: str,
    license_evidence_url: str,
) -> CatalogSource:
    try:
        source = catalog[source_id]
    except KeyError as error:
        raise ValueError(f"Source '{source_id}' is not in the approved catalog.") from error
    if publisher != source.publisher:
        raise ValueError(f"Publisher for '{source_id}' does not match the catalog.")
    if license_status != source.license_status:
        raise ValueError(f"License for '{source_id}' does not match the catalog.")
    if license_evidence_url != source.license_evidence_url:
        raise ValueError(f"License evidence for '{source_id}' does not match the catalog.")
    if not any(url_matches_prefix(source_url, prefix) for prefix in source.allowed_url_prefixes):
        raise ValueError(f"URL for '{source_id}' is outside the catalog allowlist.")
    return source


def url_matches_prefix(url: str, prefix: str) -> bool:
    candidate = urlsplit(url)
    allowed = urlsplit(prefix)
    if (
        candidate.scheme != "https"
        or candidate.scheme != allowed.scheme
        or candidate.hostname != allowed.hostname
        or candidate.port != allowed.port
        or candidate.username is not None
        or candidate.password is not None
    ):
        return False
    path = unquote(candidate.path)
    allowed_path = unquote(allowed.path)
    if any(part == ".." for part in Path(path).parts):
        return False
    if allowed_path.endswith("/"):
        return path.startswith(allowed_path)
    return path == allowed_path or path.startswith(allowed_path + "/")
