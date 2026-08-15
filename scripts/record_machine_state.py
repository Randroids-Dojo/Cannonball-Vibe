"""Record the machine's own state around a reference-performance capture.

The 2026-08-13 repeat matrix contained a run whose mean render GPU time was about
ten times its sibling runs at identical arguments, with frame rate down by a
similar factor. Nothing in the capture recorded anything that could distinguish
that run from the others. This makes the machine's state observable per capture.

Since the owner's 2026-08-14 answer to Q-022a this record also decides: a capture
that does not start from an idle machine, or that sees a new GPU client appear
while it runs, is reported as contended and the capture script refuses to publish
it. That is a precondition on the measurement, not a change to any acceptance
threshold; the zero-stall limit is unchanged and still failed.
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

# Declared, not derived. An idle desktop still runs a compositor, so the bar is
# "nothing is doing sustained GPU work", not "the GPU is at zero". Raising this
# would admit more contended captures; it is deliberately not tunable per run.
IDLE_UTILIZATION_CEILING_PERCENT = 10.0


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


CAPTURE_PROCESS_HINTS = ("godot", "cannonball")


def summarise_clients(raw: str) -> dict[str, object]:
    """Reduce the GPU client list to a count, keeping no identifying detail.

    nvidia-smi reports absolute image paths. Those carry the user profile
    directory, and even reduced to a basename they amount to an inventory of the
    owner's installed software — browsers, chat clients, games. Capture evidence
    is committed to a public repository, so nothing identifying is retained.

    The contention question only needs how many clients held a GPU context and
    whether the capture itself was one of them. Process identifiers and names add
    nothing to that and cannot be un-published once committed.
    """
    total = 0
    includes_capture_process = False
    unavailable = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        _, _, process = line.partition(",")
        process = process.strip().lower()
        if process.startswith("[") and process.endswith("]"):
            unavailable += 1
            continue
        if any(hint in process for hint in CAPTURE_PROCESS_HINTS):
            includes_capture_process = True
    return {
        "count": total,
        "includes_capture_process": includes_capture_process,
        "not_attributable_count": unavailable,
    }


def parse_during_samples(path: str | None) -> list[dict[str, float]]:
    """Read the `seconds,utilisation,client_count` series taken during the run."""
    if not path:
        return []
    series_path = Path(path)
    if not series_path.exists():
        return []
    samples: list[dict[str, float]] = []
    for line in series_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(",")
        if len(parts) != 3:
            continue
        try:
            samples.append(
                {
                    "seconds": float(parts[0]),
                    "gpu_utilization_percent": float(parts[1]),
                    "client_count": float(parts[2]),
                }
            )
        except ValueError:
            continue
    return samples


def summarise_during(samples: list[dict[str, float]], baseline_clients: int) -> dict[str, object]:
    """Summarise the during-run series, and say whether a new GPU client appeared.

    Utilisation during the run cannot separate contention from the capture's own
    work — the capture is meant to load the GPU. Client count can: the capture
    adds exactly one client to the pre-run baseline, so any sample above that is
    a process that arrived while the measurement was in flight.
    """
    if not samples:
        return {
            "available": False,
            "reason": "no during-run samples were taken",
            "new_client_observed": False,
        }
    counts = [sample["client_count"] for sample in samples]
    utilisation = [sample["gpu_utilization_percent"] for sample in samples]
    expected = baseline_clients + 1
    over = [count for count in counts if count > expected]
    return {
        "available": True,
        "sample_count": len(samples),
        "gpu_utilization_percent_mean": sum(utilisation) / len(utilisation),
        "gpu_utilization_percent_max": max(utilisation),
        "client_count_min": min(counts),
        "client_count_max": max(counts),
        "expected_client_count": expected,
        "samples_over_expected": len(over),
        "new_client_observed": bool(over),
    }


def assess(
    before: dict[str, object],
    clients_before: dict[str, object],
    during: dict[str, object],
) -> dict[str, object]:
    """Decide whether this capture started idle and stayed uncontended."""
    reasons: list[str] = []
    if not before.get("available"):
        reasons.append(
            "GPU state could not be sampled before the capture, so idleness is unknown"
        )
    else:
        # Only utilization.gpu is tested. utilization.memory reads as the fraction
        # of the sample period in which device memory was being accessed, which an
        # idle desktop compositor keeps in the mid teens; including it refused
        # every capture on a real interactive machine while saying nothing about
        # whether another process was doing sustained GPU work. It is still
        # recorded, just not gated on.
        utilisation = before.get("gpu_utilization_percent")
        if (
            isinstance(utilisation, (int, float))
            and utilisation > IDLE_UTILIZATION_CEILING_PERCENT
        ):
            reasons.append(
                f"GPU utilisation was {utilisation:.0f}% before the capture, above the "
                f"{IDLE_UTILIZATION_CEILING_PERCENT:.0f}% idle ceiling"
            )
    if clients_before.get("includes_capture_process"):
        reasons.append("a capture process already held a GPU context before this run")
    if during.get("new_client_observed"):
        reasons.append(
            f"a GPU client appeared during the run in "
            f"{during.get('samples_over_expected')} of "
            f"{during.get('sample_count')} samples"
        )
    return {
        "idle_precondition": "ratified 2026-08-14 (ADR-0023 Q-022a)",
        "criterion": (
            f"GPU utilisation at or below {IDLE_UTILIZATION_CEILING_PERCENT:.0f}% "
            "before the capture, no capture process already holding a GPU context, "
            "and no new GPU client appearing while the run is measured"
        ),
        "contended": bool(reasons),
        "reasons": reasons,
        "boundary": (
            "This is a precondition on the measurement, not an acceptance threshold. "
            "It does not relax the zero-stall limit, which remains failed until a "
            "matrix passing this precondition records no stall."
        ),
    }


def main() -> None:
    output, scenario = sys.argv[1], sys.argv[2]
    gpu_before, gpu_after = sys.argv[3], sys.argv[4]
    clients_before, clients_after = sys.argv[5], sys.argv[6]
    during_path = sys.argv[7] if len(sys.argv) > 7 else None

    before, after = parse_gpu(gpu_before), parse_gpu(gpu_after)
    listed_before = summarise_clients(clients_before)
    listed_after = summarise_clients(clients_after)
    count_before = listed_before["count"]
    count_after = listed_after["count"]
    during = summarise_during(parse_during_samples(during_path), int(count_before))
    assessment = assess(before, listed_before, during)

    document = {
        "schema_version": 2,
        "scenario": scenario,
        "purpose": (
            "Records GPU utilisation, clock, temperature, power draw, and the "
            "number of processes holding a GPU context before, during, and after "
            "a capture, and decides whether the capture is admissible."
        ),
        "gpu_before": before,
        "gpu_after": after,
        "gpu_clients_before": listed_before,
        "gpu_clients_after": listed_after,
        "gpu_client_count_before": count_before,
        "gpu_client_count_after": count_after,
        "gpu_during": during,
        "assessment": assessment,
        "boundary": (
            "nvidia-smi lists every process holding a GPU context, which on an "
            "interactive Windows session always includes the shell and compositor. "
            "A non-zero client count is therefore not by itself evidence of "
            "contention, which is why the during-run test compares against the "
            "pre-run baseline plus the capture rather than against zero. Sampling is "
            "periodic, so a load shorter than the sample interval can still go "
            "unobserved. Only client counts are retained: process identifiers, image "
            "paths, and executable names are all discarded, because committed evidence "
            "must not carry an inventory of the owner's installed software."
        ),
        "enforcement": (
            "the capture script refuses to publish a contended capture unless "
            "--allow-contended is passed, which is recorded in the run"
        ),
    }

    Path(output).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        "CANNONBALL_REFERENCE_MACHINE_STATE "
        f"scenario={scenario} "
        f"gpu_util_before={before.get('gpu_utilization_percent', 'na')} "
        f"gpu_util_after={after.get('gpu_utilization_percent', 'na')} "
        f"clients_before={count_before} clients_after={count_after} "
        f"contended={str(assessment['contended']).lower()} "
        f"manifest={output}"
    )
    if assessment["contended"]:
        for reason in assessment["reasons"]:
            print(f"CANNONBALL_REFERENCE_CONTENDED scenario={scenario} reason={reason}")
        sys.exit(3)


if __name__ == "__main__":
    main()
