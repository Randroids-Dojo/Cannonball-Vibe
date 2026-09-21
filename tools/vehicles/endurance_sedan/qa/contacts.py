"""Independent CPU contact diagnostics on retained evaluated mesh/pose bytes.

Observed intersections have explicit actual triangle or solid witnesses.
A lack of witnesses in sampled poses is not a continuous-clearance pass.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

from mathutils import Matrix, Vector, geometry
from mathutils.bvhtree import BVHTree


sys.path.insert(0,str(Path(__file__).resolve().parent))
from geometry import Mesh, contact, overlap_bounds, segment_hit

def main():
    test_triangle = [Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0))]
    assert segment_hit(Vector((-.5, -.5, -1)), Vector((-.5, -.5, 1)), test_triangle) is None, "Plane crossing outside triangle must not count."
    assert segment_hit(Vector((.25, .25, -1)), Vector((.25, .25, 1)), test_triangle) is not None
    assert segment_hit(Vector((.25, .25, -2)), Vector((.25, .25, -1)), test_triangle) is None, "Hit beyond segment endpoint must not count."
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", choices=("packaging", "openings", "tires", "wipers"), required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.output.exists():
        raise RuntimeError("Retain original contact probe evidence.")
    payload = json.loads(gzip.decompress(args.input.read_bytes()))
    rows = {name: row for name, row in payload["meshes"].items() if row["properties"].get("source_preview_only") is not True}
    excluded = [name for name in payload["meshes"] if name not in rows]
    base = {name: Mesh(row) for name, row in rows.items()}
    poses = {row["name"]: row for row in payload["poses"]}
    rest = poses["rest"]["semantic_world_matrices"]
    started = datetime.now(timezone.utc).isoformat()
    begin = time.perf_counter()
    results = []
    checked = 0

    def inspect(label, selected, posed=None, ignore_same_rigid_parent=False):
        nonlocal checked
        meshes = base.copy()
        if posed is not None:
            transforms = posed["semantic_world_matrices"]
            for name, row in rows.items():
                parent = next((n for n in row["ancestors"] if n in transforms), None)
                if parent and transforms[parent] != rest[parent]:
                    delta = Matrix(transforms[parent]) @ Matrix(rest[parent]).inverted()
                    meshes[name] = Mesh(row, delta)
        seen = set()
        for first in selected:
            for second in meshes:
                if first == second:
                    continue
                pair = tuple(sorted((first, second)))
                if pair in seen:
                    continue
                seen.add(pair)
                if ignore_same_rigid_parent:
                    a = next((n for n in rows[first]["ancestors"] if n.startswith("Door_") or n in ("Hood_Hinge", "Trunk_Hinge", "Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR", "Wiper_L", "Wiper_R")), None)
                    if a is not None and a in rows[second]["ancestors"]:
                        continue
                if not overlap_bounds(meshes[first], meshes[second]):
                    continue
                checked += 1
                observed = contact(meshes[first], meshes[second])
                if observed:
                    row = {"pose": label, "pair": list(pair), "witness": observed,
                           "classification": "unclassified contact; compare exact allowed interface before assigning defect"}
                    results.append(row)
                    print("QA_CONTACT " + json.dumps(row), flush=True)

    if args.scope == "packaging":
        selected = [n for n in rows if any(key in n for key in ("MainFuel", "MainTankCrossover", "AuxiliaryTank", "AuxFill", "AuxVent", "VentBulkheadUnion", "VentRolloverValve", "VentExternalCover", "TransferPump", "PumpInletUnion", "FuelBulkheadGland", "FuelTransferLine", "DctBellhousing", "FrontFinalDrive", "HoodOffsetArm", "TrunkOffsetArm"))]
        inspect("rest", selected)
    elif args.scope == "openings":
        for label, pose in poses.items():
            active = [key.removesuffix("_open") for key in pose["controls"] if key.endswith("_open")]
            if not active:
                continue
            selected = [name for name, row in rows.items() if any(parent in row["ancestors"] for parent in active)]
            inspect(label, selected, pose, True)
    elif args.scope == "tires":
        selected = [n for n in rows if n.startswith("LOD0_Tire_")]
        for label, pose in poses.items():
            if label == "rest" or label.startswith("suspension_") or label in ("steering_-1", "steering_1"):
                inspect(label, selected, pose, True)
    else:
        selected = [n for n in rows if n.startswith("LOD0_Wiper_")]
        for label, pose in poses.items():
            if label == "rest" or label.startswith("wiper_sweep_"):
                inspect(label, selected, pose, True)

    report = {"task_id": "P1-018", "start_utc": started, "end_utc": datetime.now(timezone.utc).isoformat(),
              "elapsed_seconds": time.perf_counter() - begin, "source_sha256": payload["source_sha256"],
              "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": args.scope, "excluded_source_preview_meshes": excluded, "aabb_candidate_pairs_checked": checked, "observed_contacts": results,
              "probe_self_checks": {"outside_triangle_rejected": True, "inside_triangle_accepted": True, "beyond_segment_rejected": True},
              "method": "Actual evaluated triangle vertices transformed by recorded Blender native driver matrices. Three-ray solid parity or exact segment/triangle intersection confirms every reported contact. BVH/AABB candidates alone do not establish contact.",
              "limits": "Sampled poses, no positive minimum-clearance or continuous sweep claim. Same rigid moving assembly contacts omitted only in motion scopes; all other contacts remain unclassified for exact interface review.",
              "human_approval_reference": None}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("QA_CONTACT_PROBE_OK " + json.dumps({"scope": args.scope, "contacts": len(results), "candidate_pairs": checked, "seconds": report["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
