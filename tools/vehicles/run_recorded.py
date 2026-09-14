"""Run a production command without a shell and retain its exact outcome."""

import argparse
import datetime
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--environment", action="append", default=[], help="Explicit non-secret environment variable to retain")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    args.directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    stem = timestamp.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + args.label
    log = args.directory / (stem + ".log")
    record = {
        "task_id": "P1-018", "start_utc": timestamp.isoformat(),
        "platform": platform.platform(), "cwd": str(Path.cwd()), "argv": command,
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "input_artifacts": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in args.input],
        "log": str(log), "human_approval_reference": None,
        "environment": {key: os.environ.get(key) for key in args.environment},
    }
    with log.open("wb") as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    record["end_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record["exit_status"] = process.returncode
    record["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
    record_path = args.directory / (stem + ".json")
    record_path.write_text(json.dumps(record, indent=2) + "\n", newline="\n")
    print(json.dumps({"record": str(record_path), "log": str(log), "exit_status": process.returncode}), flush=True)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
