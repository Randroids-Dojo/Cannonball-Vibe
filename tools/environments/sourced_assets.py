"""Plan, acquire, and verify checksum-locked third-party CC0 art sources.

The lock file is the machine-readable rights and provenance record that
ADR-0012 and the Q-023 rights policy require for every non-project-original
asset: publisher, authors, license, canonical URL, declared size and MD5 from
the provider API, the exact bytes acquired (SHA-256), the acquisition time,
and the HTTP response metadata. Runtime files are the acquired bytes; nothing
is re-encoded, so the lock hash is the shipping hash.

Subcommands:

  plan     Fill provider metadata and download records from the Poly Haven
           API for every asset whose files are declared by map, resolution
           and format. Idempotent; never discards an acquired hash unless the
           canonical URL changed.
  acquire  Download every file that is missing or unverified, refuse any byte
           count or MD5 that disagrees with the provider declaration, and
           record SHA-256, timestamp and response headers.
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
from pathlib import Path

USER_AGENT = "Cannonball-Vibe sourced-asset acquisition (+https://github.com/Randroids-Dojo/Cannonball-Vibe)"
POLYHAVEN_API = "https://api.polyhaven.com"
TEXTURE_MAP_KEYS = {
    "diffuse": "Diffuse",
    "normal": "nor_gl",
    "arm": "arm",
    "rough": "Rough",
    "ao": "AO",
    "displacement": "Displacement",
}


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


def load_lock(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_lock(path: Path, lock: dict) -> None:
    path.write_text(json.dumps(lock, indent=2, sort_keys=False) + "\n", encoding="utf-8")


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
    if "url" not in requested:
        raise ValueError("runtime_path requires a planned url")
    # glTF sidecar files keep the relative layout the .gltf document references.
    name = requested["map"] if asset["kind"] == "model" and requested["map"] != "gltf" else requested["url"].rsplit("/", 1)[-1]
    return f"{asset['runtime_directory']}/{name}"


def plan(lock: dict) -> None:
    for asset in lock["assets"]:
        if asset["provider"] != "polyhaven":
            raise ValueError(f"Unsupported provider '{asset['provider']}'")
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
    lock["planned_utc"] = utc_now()


def acquire(lock: dict, repo_root: Path, force: bool) -> int:
    downloaded = 0
    for asset in lock["assets"]:
        for requested in asset["files"]:
            target = repo_root / requested["path"]
            if not force and requested.get("sha256") and target.exists() and sha256_of(target) == requested["sha256"]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(requested["url"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
                payload = response.read()
                headers = {key.lower(): value for key, value in response.headers.items()}
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
            requested["response"] = {
                key: headers[key]
                for key in ("content-type", "content-length", "etag", "last-modified", "server")
                if key in headers
            }
            downloaded += 1
            print(f"acquired {requested['path']} sha256={requested['sha256']}")
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
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
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
