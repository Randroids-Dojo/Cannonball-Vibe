"""Plan, acquire, and verify checksum-locked third-party CC0 art sources.

The lock file is the machine-readable rights and provenance record that
ADR-0012 and the Q-023 rights policy require for every non-project-original
asset: publisher, authors, license, canonical URL, declared size and MD5 from
the provider API, the exact bytes acquired (SHA-256), the acquisition time,
and the HTTP response metadata. Runtime files are the acquired bytes; nothing
is re-encoded, so the lock hash is the shipping hash.

Providers:

  polyhaven   Per-map files declared by map, resolution and format; the API
              declares size and MD5 for every file.
  ambientcg   One zip per asset and resolution; the API declares the byte
              count, no hash, so the archive SHA-256 is recorded on first
              acquisition and enforced afterwards. Only the members listed
              under ``files`` are extracted into the runtime directory and
              each member's SHA-256 is recorded.
  texturecan  One zip per asset with no API; the byte count comes from the
              HEAD response at plan time and the archive SHA-256 is recorded
              on first acquisition, as for ambientCG.

Archives are cached under ``.tools/sourced-cache`` and never committed.

Subcommands:

  plan     Fill provider metadata and download records. Idempotent; never
           discards an acquired hash unless the canonical URL changed.
  acquire  Download every archive or file that is missing or unverified,
           refuse any byte count or MD5 that disagrees with the provider
           declaration, extract requested members, and record SHA-256,
           timestamp and response headers.
  verify   Re-hash every runtime file against the lock and write a report.

Only the Python standard library is used so the tool runs on every declared
platform without the map-pipeline virtual environment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = "Cannonball-Vibe sourced-asset acquisition (+https://github.com/Randroids-Dojo/Cannonball-Vibe)"
POLYHAVEN_API = "https://api.polyhaven.com"
AMBIENTCG_API = "https://ambientcg.com/api/v2/full_json"
TEXTURE_MAP_KEYS = {
    "diffuse": "Diffuse",
    "normal": "nor_gl",
    "arm": "arm",
    "rough": "Rough",
    "ao": "AO",
    "displacement": "Displacement",
    "metal": "Metal",
}
CACHE_DIRECTORY = ".tools/sourced-cache"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def md5_of(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - provider-declared integrity value, not security
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
        return json.load(response)


def head_length(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return int(response.headers.get("content-length", "0"))


def load_lock(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_lock(path: Path, lock: dict) -> None:
    path.write_text(json.dumps(lock, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")


def polyhaven_file_record(files: dict, asset: dict, requested: dict) -> dict:
    kind = asset["kind"]
    resolution = requested["resolution"]
    fmt = requested["format"]
    if kind == "hdri":
        entry = files["hdri"][resolution][fmt]
    elif kind == "texture-set":
        entry = files[TEXTURE_MAP_KEYS[requested["map"]]][resolution][fmt]
    elif kind == "model":
        gltf = files["gltf"][resolution]["gltf"]
        if requested["map"] == "gltf":
            entry = gltf
        else:
            entry = gltf["include"][requested["map"]]
    else:
        raise ValueError(f"Unknown asset kind '{kind}'")
    return {"url": entry["url"], "declared_bytes": int(entry["size"]), "declared_md5": entry["md5"]}


def runtime_path(asset: dict, requested: dict) -> str:
    if "url" not in requested and "member" not in requested:
        raise ValueError("runtime_path requires a planned url or archive member")
    if "member" in requested:
        return f"{asset['runtime_directory']}/{requested['member'].rsplit('/', 1)[-1]}"
    # glTF sidecar files keep the relative layout the .gltf document references.
    name = requested["map"] if asset["kind"] == "model" and requested["map"] != "gltf" else requested["url"].rsplit("/", 1)[-1]
    return f"{asset['runtime_directory']}/{name}"


def plan_polyhaven(asset: dict) -> None:
    provider_id = asset["provider_asset_id"]
    info = fetch_json(f"{POLYHAVEN_API}/info/{provider_id}")
    files = fetch_json(f"{POLYHAVEN_API}/files/{provider_id}")
    asset["name"] = info["name"]
    asset["authors"] = info.get("authors", {})
    asset["date_published_utc"] = dt.datetime.fromtimestamp(
        int(info["date_published"]), dt.timezone.utc
    ).date().isoformat()
    asset["canonical_url"] = f"https://polyhaven.com/a/{provider_id}"
    asset["provider_categories"] = info.get("categories", [])
    if "dimensions_mm" not in asset and info.get("dimensions"):
        asset["dimensions_mm"] = info["dimensions"]
    asset["license"].setdefault("spdx", "CC0-1.0")
    asset["license"].setdefault("redistributable", True)
    asset["license"].setdefault("status", "pending-human-review")
    asset["license"]["attribution"] = (
        f"{info['name']} by {', '.join(info.get('authors', {}).keys())} "
        f"via Poly Haven ({asset['canonical_url']}), CC0 1.0"
    )
    for requested in asset["files"]:
        record = polyhaven_file_record(files, asset, requested)
        if requested.get("url") != record["url"]:
            requested.pop("sha256", None)
            requested.pop("acquired_utc", None)
            requested.pop("response", None)
        requested.update(record)
        requested["path"] = runtime_path(asset, requested)


def plan_archive(asset: dict) -> None:
    """ambientCG and TextureCan: one archive whose members are the runtime files."""
    archive = asset.setdefault("archive", {})
    if asset["provider"] == "ambientcg":
        provider_id = asset["provider_asset_id"]
        payload = fetch_json(f"{AMBIENTCG_API}?id={provider_id}&include=downloadData,tagData")
        found = [item for item in payload.get("foundAssets", []) if item.get("assetId") == provider_id]
        if not found:
            raise ValueError(f"ambientCG has no asset '{provider_id}'")
        info = found[0]
        wanted = archive["attribute"]
        download = None
        for folder in info.get("downloadFolders", {}).values():
            for category in folder.get("downloadFiletypeCategories", {}).values():
                for candidate in category.get("downloads", []):
                    if candidate.get("attribute") == wanted:
                        download = candidate
        if download is None:
            raise ValueError(f"ambientCG '{provider_id}' has no download attribute '{wanted}'")
        url = download["downloadLink"]
        asset["name"] = provider_id
        asset["authors"] = {"ambientCG (Lennart Demes)": "Publisher"}
        asset["canonical_url"] = info.get("shortLink", f"https://ambientcg.com/a/{provider_id}")
        asset["provider_categories"] = info.get("tags", [])
        asset["license"]["attribution"] = f"{provider_id} via ambientCG ({asset['canonical_url']}), CC0 1.0"
        declared_bytes = int(download["size"])
    elif asset["provider"] == "texturecan":
        url = archive["url"]
        asset.setdefault("name", asset["provider_asset_id"])
        asset.setdefault("authors", {"TextureCan": "Publisher"})
        asset["license"]["attribution"] = f"{asset['name']} via TextureCan ({asset['canonical_url']}), CC0 1.0"
        declared_bytes = head_length(url)
    else:
        raise ValueError(f"Unsupported provider '{asset['provider']}'")
    asset["license"].setdefault("spdx", "CC0-1.0")
    asset["license"].setdefault("redistributable", True)
    asset["license"].setdefault("status", "pending-human-review")
    if archive.get("url") != url:
        archive.pop("sha256", None)
        archive.pop("acquired_utc", None)
        archive.pop("response", None)
        archive.pop("resolved_url", None)
        for requested in asset["files"]:
            requested.pop("sha256", None)
            requested.pop("acquired_utc", None)
    archive["url"] = url
    archive["declared_bytes"] = declared_bytes
    archive["cache_path"] = f"{CACHE_DIRECTORY}/{asset['provider']}/{url.rsplit('/', 1)[-1].split('=')[-1]}"
    for requested in asset["files"]:
        requested["path"] = runtime_path(asset, requested)


def plan(lock: dict) -> None:
    for asset in lock["assets"]:
        if asset["provider"] == "polyhaven":
            plan_polyhaven(asset)
        elif asset["provider"] in ("ambientcg", "texturecan"):
            plan_archive(asset)
        else:
            raise ValueError(f"Unsupported provider '{asset['provider']}'")
    lock["planned_utc"] = utc_now()


def download(url: str, timeout: int = 600) -> tuple[bytes, dict, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        resolved = response.geturl()
    return payload, headers, resolved


def response_record(headers: dict) -> dict:
    return {
        key: headers[key]
        for key in ("content-type", "content-length", "etag", "last-modified", "server")
        if key in headers
    }


def acquire_polyhaven(asset: dict, repo_root: Path, force: bool) -> int:
    downloaded = 0
    for requested in asset["files"]:
        target = repo_root / requested["path"]
        if not force and requested.get("sha256") and target.exists() and sha256_of(target) == requested["sha256"]:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        payload, headers, _ = download(requested["url"], timeout=300)
        if len(payload) != requested["declared_bytes"]:
            raise RuntimeError(
                f"{requested['url']}: declared {requested['declared_bytes']} bytes, received {len(payload)}"
            )
        actual_md5 = hashlib.md5(payload).hexdigest()  # noqa: S324
        if actual_md5 != requested["declared_md5"]:
            raise RuntimeError(f"{requested['url']}: declared MD5 {requested['declared_md5']}, received {actual_md5}")
        target.write_bytes(payload)
        requested["sha256"] = hashlib.sha256(payload).hexdigest()
        requested["acquired_utc"] = utc_now()
        requested["response"] = response_record(headers)
        downloaded += 1
        print(f"acquired {requested['path']} sha256={requested['sha256']}")
    return downloaded


def acquire_archive(asset: dict, repo_root: Path, force: bool) -> int:
    archive = asset["archive"]
    cache = repo_root / archive["cache_path"]
    need_archive = force or not cache.exists() or (archive.get("sha256") and sha256_of(cache) != archive["sha256"])
    if not need_archive and not archive.get("sha256"):
        need_archive = True
    downloaded = 0
    if need_archive:
        cache.parent.mkdir(parents=True, exist_ok=True)
        payload, headers, resolved = download(archive["url"])
        if len(payload) != archive["declared_bytes"]:
            raise RuntimeError(
                f"{archive['url']}: declared {archive['declared_bytes']} bytes, received {len(payload)}"
            )
        actual = hashlib.sha256(payload).hexdigest()
        if archive.get("sha256") and archive["sha256"] != actual:
            raise RuntimeError(f"{archive['url']}: locked SHA-256 {archive['sha256']}, received {actual}")
        cache.write_bytes(payload)
        archive["sha256"] = actual
        archive["md5"] = hashlib.md5(payload).hexdigest()  # noqa: S324
        archive["acquired_utc"] = utc_now()
        archive["resolved_url"] = resolved
        archive["response"] = response_record(headers)
        downloaded += 1
        print(f"acquired archive {archive['cache_path']} sha256={actual}")
    with zipfile.ZipFile(cache) as bundle:
        names = set(bundle.namelist())
        for requested in asset["files"]:
            member = requested["member"]
            if member not in names:
                raise RuntimeError(f"{archive['cache_path']} has no member {member}")
            target = repo_root / requested["path"]
            data = bundle.read(member)
            digest = hashlib.sha256(data).hexdigest()
            if requested.get("sha256") and requested["sha256"] != digest:
                raise RuntimeError(f"{member}: locked SHA-256 {requested['sha256']}, archive holds {digest}")
            if not target.exists() or sha256_of(target) != digest:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                print(f"extracted {requested['path']} sha256={digest}")
            requested["sha256"] = digest
            requested["declared_bytes"] = len(data)
            requested.setdefault("acquired_utc", archive["acquired_utc"])
    return downloaded


def acquire(lock: dict, repo_root: Path, force: bool) -> int:
    downloaded = 0
    for asset in lock["assets"]:
        if asset["provider"] == "polyhaven":
            downloaded += acquire_polyhaven(asset, repo_root, force)
        else:
            downloaded += acquire_archive(asset, repo_root, force)
    lock["acquired_utc"] = utc_now()
    return downloaded


def verify(lock: dict, repo_root: Path) -> dict:
    checked = []
    failures = []
    for asset in lock["assets"]:
        for requested in asset["files"]:
            path = repo_root / requested["path"]
            entry = {"asset": asset["id"], "path": requested["path"], "expected_sha256": requested.get("sha256")}
            if not requested.get("sha256"):
                failures.append({**entry, "reason": "not acquired"})
                continue
            if not path.exists():
                failures.append({**entry, "reason": "missing"})
                continue
            actual = sha256_of(path)
            entry["actual_sha256"] = actual
            entry["bytes"] = path.stat().st_size
            if actual != requested["sha256"]:
                failures.append({**entry, "reason": "sha256 mismatch"})
            elif entry["bytes"] != requested["declared_bytes"]:
                failures.append({**entry, "reason": "byte count drift"})
            else:
                checked.append(entry)
    statuses = sorted({asset["license"]["status"] for asset in lock["assets"]})
    return {
        "schema_version": 1,
        "lock": lock.get("id"),
        "verified_utc": utc_now(),
        "assets": len(lock["assets"]),
        "files_verified": len(checked),
        "failures": failures,
        "license_statuses": statuses,
        "total_bytes": sum(entry["bytes"] for entry in checked),
        "ok": not failures,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["plan", "acquire", "verify"])
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, help="verify: report path")
    parser.add_argument("--force", action="store_true", help="acquire: re-download verified files")
    args = parser.parse_args(argv)
    lock = load_lock(args.lock)
    if args.command == "plan":
        plan(lock)
        save_lock(args.lock, lock)
        print(f"CANNONBALL_SOURCED_ASSETS_PLANNED assets={len(lock['assets'])}")
        return 0
    if args.command == "acquire":
        count = acquire(lock, args.repo_root, args.force)
        save_lock(args.lock, lock)
        print(f"CANNONBALL_SOURCED_ASSETS_ACQUIRED downloaded={count}")
        return 0
    report = verify(lock, args.repo_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    if not report["ok"]:
        for failure in report["failures"]:
            print(f"FAIL {failure['path']}: {failure['reason']}", file=sys.stderr)
        return 1
    print(
        "CANNONBALL_SOURCED_ASSETS_OK "
        f"assets={report['assets']} files={report['files_verified']} bytes={report['total_bytes']} "
        f"license_statuses={','.join(report['license_statuses'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
