"""Record the machine's own state around a reference-performance capture.

The 2026-08-13 repeat matrix contained a run whose mean render GPU time was about
ten times its sibling runs at identical arguments, with frame rate down by a
similar factor. Nothing in the capture recorded anything that could distinguish
that run from the others. This makes the machine's state observable per capture.

This record observes only. It never classifies a capture as contended and never
fails one, because whether a capture is admissible on machine-state grounds is
Q-022a, an open owner decision.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GPU_FIELDS = [
    "gpu_utilization_percent",
    "memory_utilization_percent",
    "graphics_clock_mhz",
    "temperature_c",
    "power_draw_w",
]


def parse_gpu(raw: str) -> dict[str, object]:
    if raw.strip() == "unavailable":
        return {"available": False, "reason": "nvidia-smi did not return a sample"}
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != len(GPU_FIELDS):
        return {"available": False, "raw": raw.strip()}
    sample: dict[str, object] = {"available": True}
    for name, value in zip(GPU_FIELDS, parts):
        try:
            sample[name] = float(value)
        except ValueError:
            sample[name] = value
    return sample


def parse_clients(raw: str) -> list[dict[str, str]]:
    clients = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        pid, _, process = line.partition(",")
        clients.append({"pid": pid.strip(), "process": process.strip()})
    return clients


def main() -> None:
    output, scenario = sys.argv[1], sys.argv[2]
    gpu_before, gpu_after = sys.argv[3], sys.argv[4]
    clients_before, clients_after = sys.argv[5], sys.argv[6]

    before, after = parse_gpu(gpu_before), parse_gpu(gpu_after)
    listed_before = parse_clients(clients_before)
    listed_after = parse_clients(clients_after)

    document = {
        "schema_version": 1,
        "scenario": scenario,
        "purpose": (
            "Records GPU utilisation, clock, temperature, power draw, and the "
            "processes holding a GPU context immediately before and after a "
            "capture."
        ),
        "gpu_before": before,
        "gpu_after": after,
        "gpu_clients_before": listed_before,
        "gpu_clients_after": listed_after,
        "gpu_client_count_before": len(listed_before),
        "gpu_client_count_after": len(listed_after),
        "boundary": (
            "nvidia-smi lists every process holding a GPU context, which on an "
            "interactive Windows session always includes the shell and compositor. "
            "A non-zero client count is therefore not by itself evidence of "
            "contention. These samples bracket the capture rather than covering it, "
            "so a transient load during measurement can still go unobserved."
        ),
        "enforcement": (
            "none; this sample is recorded and never fails or reclassifies a capture"
        ),
        "open_question": "Q-022a owns whether machine state should gate a capture",
    }

    Path(output).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        "CANNONBALL_REFERENCE_MACHINE_STATE "
        f"scenario={scenario} "
        f"gpu_util_before={before.get('gpu_utilization_percent', 'na')} "
        f"gpu_util_after={after.get('gpu_utilization_percent', 'na')} "
        f"clients_before={len(listed_before)} clients_after={len(listed_after)} "
        f"manifest={output}"
    )


if __name__ == "__main__":
    main()
