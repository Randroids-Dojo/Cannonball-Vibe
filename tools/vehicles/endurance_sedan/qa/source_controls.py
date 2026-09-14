"""Exercise actual saved display drivers, warning priority and boundary values."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import struct
from pathlib import Path
import sys

import bpy


PATTERNS = [[0, 1, 2, 3, 4, 5], [1, 2], [0, 1, 3, 4, 6], [0, 1, 2, 3, 6],
            [1, 2, 5, 6], [0, 2, 3, 5, 6], [0, 2, 3, 4, 5, 6], [0, 1, 2],
            list(range(7)), [0, 1, 2, 3, 5, 6]]
WARNINGS = ("LOW FUEL", "DAMAGE", "COOLING", "TIRES", "PANEL OPEN", "PARK BRAKE")
OPENINGS = tuple(name + "_open" for name in
                 ("Door_FL", "Door_FR", "Door_RL", "Door_RR", "Hood_Hinge", "Trunk_Hinge"))
FIELDS = (("source_sim_speed_mph", 3), ("source_sim_rpm", 4), ("source_sim_fuel_l", 3))


def f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


def expected_warning(values):
    checks = (f32(values["source_sim_fuel_l"]) < f32(20),
              f32(values["source_sim_damage"]) > f32(.05),
              f32(values["source_sim_cooling_condition"]) < f32(.4),
              f32(values["source_sim_tire_condition"]) < f32(.3),
              any(f32(values[name]) > f32(.001) for name in OPENINGS),
              f32(values["source_sim_handbrake"]) > f32(.02))
    return next((name for name, enabled in zip(WARNINGS, checks) if enabled), None)


def cases():
    rows = [(f"digit-{i}", 1, {key: float(str(i) * width) for key, width in FIELDS},
             "Synthetic repeated digits exceed some ordinary inspection UI ranges.")
            for i in range(10)]
    rows += [("idle", 1, {}, "Saved ordinary defaults."),
             ("cruise", 1, {"source_sim_speed_mph": 72, "source_sim_rpm": 3750,
                             "source_sim_fuel_l": 82, "source_sim_gear": 4}, "Ordinary preview."),
             ("reverse-low-fuel", 1, {"source_sim_speed_mph": 12, "source_sim_rpm": 1600,
                                       "source_sim_fuel_l": 9, "source_sim_gear": -1}, "Ordinary preview.")]
    rows += [(f"gear-{g}", 1, {"source_sim_gear": g}, "Ordinary preview.") for g in range(-1, 8)]
    rows += [(f"{prop}-frame-{frame}", frame, {prop: 1}, "Actual emitter and telltale phase.")
             for prop in ("hazards", "left_indicators", "right_indicators")
             for frame in (1, 30, 31, 60, 61)]
    boundaries = (("source_sim_fuel_l", 20), ("source_sim_damage", .05),
                  ("source_sim_cooling_condition", .4), ("source_sim_tire_condition", .3),
                  ("source_sim_handbrake", .02), *((key, .001) for key in OPENINGS))
    for prop, boundary in boundaries:
        for offset in (-.000001, 0, .000001):
            rows.append((f"boundary-{prop}-{offset:+.6f}", 1, {prop: boundary + offset},
                         "Strict below/equal/above boundary; all other warnings neutral."))
        bits = struct.unpack('<I',struct.pack('<f',boundary))[0]
        for offset in (-1,0,1):
            adjacent = struct.unpack('<f',struct.pack('<I',bits+offset))[0]
            rows.append((f"representable-{prop}-{offset:+d}",1,{prop:adjacent},
                         "Exact float32 threshold and immediate representable neighbors; native Blender driver precision."))
    triggers = {"source_sim_fuel_l": 19, "source_sim_damage": .1,
                "source_sim_cooling_condition": .2, "source_sim_tire_condition": .2,
                "Door_FL_open": .5, "source_sim_handbrake": 1}
    for index, key in enumerate(triggers):
        # Every lower priority warning stays active while earlier ones are neutral.
        rows.append((f"priority-{WARNINGS[index]}", 1,
                     dict(list(triggers.items())[index:]), "Mutually exclusive priority chain."))
    assert len({row[0] for row in rows}) == len(rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.output.exists():
        raise RuntimeError("Evidence output already exists.")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    source_hash = sha(args.source)
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()), load_ui=False, use_scripts=True)
    controls = bpy.data.objects["RigControls"]
    baseline = {key: float(controls[key]) for key in controls.keys()
                if isinstance(controls[key], (float, int))}
    required = {key for key, _ in FIELDS} | set(OPENINGS) | {
        "source_sim_gear", "source_sim_damage", "source_sim_cooling_condition",
        "source_sim_tire_condition", "source_sim_handbrake", "hazards", "left_indicators", "right_indicators"}
    report = {"task_id": "P1-018", "milestone": "M5", "start_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": source_hash, "blender_version": bpy.app.version_string,
              "blender_build": bpy.app.build_hash.decode(), "script_sha256": sha(Path(__file__)),
              "saved_numeric_defaults": baseline, "expected_state_inventory": [r[0] for r in cases()],
              "states": [], "failures": [], "human_approval_reference": None,
              "limits": "Actual saved source-preview drivers at measured float32 evaluation precision. Nominal warning thresholds are quantized to that precision; authoritative runtime condition values remain double and can differ within one float32 bin. Synthetic gauges are explicit. No rendered readability, gameplay, or mechanical simulation claim."}
    missing = sorted(required - baseline.keys())
    if missing:
        report["failures"].append({"field": "missing-controls", "missing": missing})
    missing_labels = [name for name in WARNINGS if "LOD0_SourceDisplay_" + name not in bpy.data.objects]
    if missing_labels:
        report["failures"].append({"field": "missing-warning-labels", "missing": missing_labels})
    if not missing:
        expected_defaults = {"source_sim_damage": 0, "source_sim_cooling_condition": 1,
                             "source_sim_tire_condition": 1, "source_sim_handbrake": 0,
                             **{name: 0 for name in OPENINGS}}
        for key, expected in expected_defaults.items():
            if baseline[key] != expected:
                report["failures"].append({"field": "saved-default", "control": key,
                                           "expected": expected, "actual": baseline[key]})
        for label, frame, values, scope in cases():
            for key, value in baseline.items():
                controls[key] = value
            for key, value in values.items():
                controls[key] = float(value)
            controls.update_tag(refresh={"OBJECT"})
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            visible = [obj.name for obj in bpy.data.objects if obj.get("source_preview_only") is True
                       and not obj.hide_render]
            row = {"label": label, "frame": frame, "controls": values, "scope": scope,
                   "expected_driver_float32_inputs":{key:f32(float(controls[key])) for key in required},
                   "visible_source_geometry": visible, "digits": {}, "invalid_drivers": []}
            for field, width in FIELDS:
                segments = [sorted(int(n.rsplit("_", 1)[1]) for n in visible
                                   if n.startswith(f"LOD0_SourceDigit_{field}_{i}_")) for i in range(width)]
                decoded = "".join(str(PATTERNS.index(s)) if s in PATTERNS else "?" for s in segments)
                expected = str(math.floor(float(controls[field])) % (10 ** width)).zfill(width)
                row["digits"][field] = {"decoded": decoded, "expected": expected, "segments": segments}
                if decoded != expected:
                    report["failures"].append({"state": label, "field": field,
                                               "expected": expected, "actual": decoded})
            gear = controls["source_sim_gear"]
            expected_gear = "R" if gear == -1 else "N" if gear == 0 else str(int(gear))
            actual_gear = [name for name in ("R", "N", "1", "2", "3", "4", "5", "6", "7")
                           if "LOD0_SourceDisplay_" + name in visible]
            row["gear"] = {"actual": actual_gear, "expected": [expected_gear]}
            if actual_gear != [expected_gear]:
                report["failures"].append({"state": label, "field": "gear", **row["gear"]})
            warning = expected_warning(controls)
            actual_warnings = [name for name in WARNINGS if "LOD0_SourceDisplay_" + name in visible]
            expected_warnings = [] if warning is None else [warning]
            row["warning"] = {"actual": actual_warnings, "expected": expected_warnings}
            if actual_warnings != expected_warnings:
                report["failures"].append({"state": label, "field": "warning", **row["warning"]})
            for side in ("LEFT", "RIGHT"):
                expected = bool((controls["hazards"] >= .5 or controls[side.lower() + "_indicators"] >= .5)
                                and (frame - 1) % 60 < 30)
                actual = "LOD0_SourceDisplay_" + side in visible
                material = bpy.data.materials["Material_Indicator" + side.title()]
                emission = material.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value
                row[side.lower()] = {"actual": actual, "expected": expected, "emission": emission}
                if actual != expected or (emission > 0) != expected:
                    report["failures"].append({"state": label, "field": side, **row[side.lower()]})
            owners = list(bpy.data.objects) + [m.node_tree for m in bpy.data.materials if m.node_tree]
            for owner in owners:
                if owner.animation_data:
                    for curve in owner.animation_data.drivers:
                        if not curve.is_valid or not curve.driver.is_valid:
                            row["invalid_drivers"].append({"owner": owner.name, "path": curve.data_path,
                                                           "expression": curve.driver.expression})
            if row["invalid_drivers"]:
                report["failures"].append({"state": label, "field": "invalid-drivers",
                                           "drivers": row["invalid_drivers"]})
            report["states"].append(row)
    report["source_unchanged"] = sha(args.source) == source_hash
    report["end_utc"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed" if not report["failures"] and report["source_unchanged"] else "failed"
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "states": len(report["states"]),
                      "expected_states": len(cases()), "failures": report["failures"]}), flush=True)
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
