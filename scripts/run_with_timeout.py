"""Run an engine process with a bounded lifetime on all supported desktops."""

from __future__ import annotations

import subprocess
import sys


def run(seconds: float, command: list[str], grace_seconds: float = 30) -> int:
    with subprocess.Popen(command) as process:
        try:
            return process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            print(f"Capture exceeded {seconds:g}s; terminating engine.", file=sys.stderr)
            process.terminate()
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return 124


if __name__ == "__main__":
    raise SystemExit(run(float(sys.argv[1]), sys.argv[2:]))
