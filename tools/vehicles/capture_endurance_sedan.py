"""Record an actual native sedan movie with strict completion and decoded-size gates.

Run only while holding the shared GPU/runtime lane. The lead authorized the
temporary project override; an existing override is never changed or removed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVING = [
    "static-ride", "keyboard-acceleration", "keyboard-braking", "controller-acceleration",
    "controller-braking", "reverse", "steer-left", "steer-right", "suspension", "collision",
    "reset", "cameras", "natural-rebase", "forced-rebase", "save-resume", "starter-policy", "lod-driving",
]
PRESENTATION = [
    "contract", "view-front", "view-rear", "view-left", "view-right", "view-top", "view-underside",
    "view-front-three-quarter", "view-rear-three-quarter", "turntable", "cockpit", "view-footwell", "view-rear-cabin",
    "inspection-keyboard", "inspection-controller", "open-Door_FL", "close-Door_FL", "open-Door_FR", "close-Door_FR",
    "open-Door_RL", "close-Door_RL", "open-Door_RR", "close-Door_RR", "open-Hood_Hinge", "close-Hood_Hinge",
    "open-Trunk_Hinge", "close-Trunk_Hinge", "lights-off", "headlights", "brake-lights", "reverse-lights",
    "left-indicator", "right-indicator", "hazards", "wipers-sweep", "wipers-park", "steering-small-right",
    "controls-left", "controls-right", "instruments-forward", "instruments-reverse", "instruments-low-fuel",
    "instruments-damage", "instruments-cooling", "instruments-tires", "instruments-panel-open", "instruments-park-brake",
    "mirrors-configuration", "lod-near", "lod-middle", "lod-far", "lod-return", "mirrors-live", "mirrors-door-follow", "mirrors-disabled",
]
WARNING_STATES = {
    "instruments-low-fuel": "LOW FUEL", "instruments-damage": "DAMAGE", "instruments-cooling": "COOLING",
    "instruments-tires": "TIRES", "instruments-panel-open": "PANEL OPEN", "instruments-park-brake": "PARK BRAKE",
}
OVERRIDE = b"""; Temporary P1-018 capture settings. Removed by the owning capture runner.
[display]
window/size/viewport_width=2560
window/size/viewport_height=1440
window/size/window_width_override=2560
window/size/window_height_override=1440
window/stretch/mode="canvas_items"
"""
FATAL = re.compile(r"(?:^|\n)(?:ERROR|WARNING|SCRIPT ERROR):|Unhandled exception|Fatal error|AccessViolationException|SIGSEGV|Segmentation fault|Leaked unsafe reference|ObjectDB instances leaked|resources still in use", re.IGNORECASE)
IMPORT_WARNINGS = {
    "WARNING: Ignoring unsupported header information in HDR: GAMMA=1.",
    "WARNING: Ignoring unsupported header information in HDR: PRIMARIES=0 0 0 0 0 0 0 0.",
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_reconstruction_camera(summary, out):
    camera = summary.get("reconstruction_camera") or {}
    frames = camera.get("render_frames", [])
    process_frames = camera.get("process_frames", [])
    observations = camera.get("observations", [])
    captures = camera.get("captures", [])
    def consecutive(values):
        return len(values) == 3 and values == list(range(values[0], values[0] + 3))
    if (camera.get("native_display") is not True or not consecutive(frames) or not consecutive(process_frames)
            or [row.get("render_frame") for row in observations] != frames
            or [row.get("render_frame") for row in captures] != frames
            or [row.get("index") for row in captures] != [1, 2, 3]):
        raise ValueError("Missing first three consecutive actual reconstructed camera frames")
    for observation, capture in zip(observations, captures, strict=True):
        if (observation.get("valid") is not True or observation.get("observation_boundary") != "native-before-draw"
                or observation.get("vehicle_epoch") != 1 or observation.get("native_arm_child_error_m", 1) > 0.001
                or observation.get("hit_length_m", -1) < observation.get("spring_length_m", 0) - 0.01
                or capture.get("before_draw") != observation):
            raise ValueError("First reconstructed camera frame preceded native arm collision/placement")
        path = Path(capture["path"]).resolve()
        if not path.is_relative_to(out) or path.name != f"resume-frame-{capture['index']:02}.png":
            raise ValueError("First reconstructed camera PNG path is invalid")
        with path.open("rb") as image:
            header = image.read(24)
        size = list(struct.unpack(">II", header[16:24])) if header[:8] == b"\x89PNG\r\n\x1a\n" else []
        if size != [2560, 1440] or capture.get("size") != size or capture.get("sha256") != sha(path):
            raise ValueError("First reconstructed camera actual PNG hash/size mismatch")
    return {"status": "passed", "render_frames": frames, "captures": captures}


def validate_summary(out, mode, expected, record):
    summary = json.loads((out / ("summary.json" if mode == "driving" else "presentation-summary.json")).read_text(encoding="utf-8-sig"))
    captures = summary["rendered_captures" if mode == "driving" else "captures"]
    record["completed_stages"] = [stage["stage"] for stage in summary["completed_stages"]]
    if (summary["status"] != "passed" or summary["expected_stages"] != expected or record["completed_stages"] != expected
            or any(stage["status"] != "passed" for stage in summary["completed_stages"])):
        record["failures"].append("Summary inventory or stage status mismatch")
    if mode == "driving" and (summary["vehicle"] != "endurance-sedan"
            or summary["loaded_asset"] != "endurance-sedan"
            or summary["blockout_presentation_omitted"] is not record.get("blockout", False)):
        record["failures"].append("Wrong vehicle or unexpected blockout/production presentation scope")
    if mode == "presentation":
        if summary["rendered"] is not True or summary["diagnostic_probe"] != record.get("diagnostic_probe"):
            record["failures"].append("Summary rendering/diagnostic identity mismatch")
        if record.get("diagnostic_probe") == "mirrors" and summary["mirror_lighting"] != record["mirror_lighting"]:
            record["failures"].append("Mirror lighting identity mismatch")
        if sha(out / "mirror-samples.jsonl") != summary["mirror_samples_sha256"]:
            record["failures"].append("Mirror pixel/sample evidence hash mismatch")
        for stage, label in WARNING_STATES.items():
            if stage not in expected:
                continue
            warning = (summary.get("warning_visibilities") or {}).get(stage) or {}
            if (warning.get("passed") is not True or warning.get("source_glyph_pixels", 0) < 40
                    or warning.get("stage") != stage or warning.get("warning") != label
                    or warning.get("total_ratio", 0) < 0.90 or len(warning.get("half_ratios", [])) != 2
                    or any(value < 0.85 for value in warning.get("half_ratios", []))):
                record["failures"].append("Actual cockpit warning visibility was not verified: " + label)
    if [capture["stage"] for capture in captures] != expected:
        record["failures"].append("Actual PNG capture inventory mismatch")
    if mode == "driving":
        record["reconstruction_camera"] = validate_reconstruction_camera(summary, out)
        contact = summary.get("contact_shading") or {}
        shading_required = not record.get("blockout", False) or contact.get("enabled_by_setup") is True
        if shading_required and (contact.get("enabled_by_setup") is not True or contact.get("supported_renderer") is not True
                                 or contact.get("render_samples", 0) < 3 or contact.get("visible_wheel_samples", 0) < 4
                                 or contact.get("airborne_wheel_samples", 0) < 1
                                 or contact.get("maximum_alignment_error_m", 1) > 0.001 or contact.get("maximum_plane_error_m", 1) > 0.001):
            record["failures"].append("Native contact shading contact/alignment/airborne proof missing")
        if not shading_required and (contact.get("supported_renderer") is not False or contact.get("render_samples") != 0):
            record["failures"].append("Historical blockout contact-shading omission scope mismatch")
        record["contact_shading"] = contact
        budget_path = Path(record.get("project_root", ROOT)) / "tools/vehicles/vehicle_contract.json"
        budgets = json.loads(budget_path.read_text())["budgets"]
        record["runtime_budget_sha256"] = sha(budget_path)
        inventories = list((summary.get("runtime_resource_inventory") or {}).values())
        required_lods = {0} if record.get("blockout", False) else {0, 1, 2}
        if not required_lods.issubset({row["ActiveLod"] for row in inventories}) or any(
                row["DrawnTriangles"] + (48 if shading_required else 0) > budgets["triangles_lod0_max"]
                or row["ActiveMaterialResources"] > budgets["materials_max"]
                or row["ActiveTextureResources"] + int(shading_required) > budgets["textures_max"] for row in inventories):
            record["failures"].append("Actual runtime visible geometry/material/texture budget inventory missing or exceeded")
        record["runtime_resource_inventory"] = inventories
        record["contact_proxy_geometry_budget"] = {"triangles_per_viewport_upper_bound": 48 if shading_required else 0,
            "basis": "Four renderer-owned twelve-triangle cluster boxes per viewport; additional mirror-view submissions are measured separately."}
        previous_frame = previous_count = -1
        for stage in ("natural-rebase", "forced-rebase"):
            observation = (summary.get("rebase_observations") or {}).get(stage) or {}
            capture = next((row for row in captures if row["stage"] == stage), {})
            rendered = observation.get("rendered_frames", [])
            count = observation.get("captured_rebase_count", -1)
            frame = observation.get("captured_render_frame", -1)
            if (observation.get("native_display") is not True or len(set(rendered)) < 3
                    or len(set(observation.get("process_frames", []))) < 3
                    or count != observation.get("rebase_count") or count <= previous_count
                    or count <= observation.get("baseline_rebase_count", count)
                    or frame != capture.get("render_frame") or frame <= previous_frame or frame not in rendered
                    or any(capture.get(boundary, {}).get("local_origin", {}).get("RebaseCount") != count
                           for boundary in ("before_draw", "after_draw"))):
                record["failures"].append("Missing separately rendered rebase event: " + stage)
            previous_frame, previous_count = frame, count
    for capture in captures:
        path = Path(capture["path"]).resolve()
        if not path.is_relative_to(out):
            raise RuntimeError("Capture image escapes its evidence directory")
        with path.open("rb") as image:
            header = image.read(24)
        decoded_size = list(struct.unpack(">II", header[16:24])) if header[:8] == b"\x89PNG\r\n\x1a\n" else []
        if decoded_size != [2560, 1440] or capture["size"] != decoded_size or capture["sha256"] != sha(path):
            record["failures"].append("Actual PNG size/hash mismatch: " + capture["stage"])
        quality = capture.get("render_quality", {})
        if (capture.get("renderer") != "forward_plus" or quality.get("actual_msaa_3d") != "Msaa4X"
                or quality.get("applied_tier") != "high" or quality.get("applied_directional_shadow_size") != 8192):
            record["failures"].append("Actual native High rendering configuration mismatch: " + capture["stage"])
        if mode == "driving" and capture.get("lighting") != "day":
            record["failures"].append("Actual driving capture environment preset mismatch: " + capture["stage"])
        if mode == "presentation" and capture.get("actual_environment_preset") != str(capture.get("lighting", "")).lower():
            record["failures"].append("Actual presentation capture environment preset mismatch: " + capture["stage"])
        if mode == "driving":
            before, after = capture["before_draw"], capture["after_draw"]
            if (before["render_frame"] != capture["render_frame"] or after["render_frame"] != capture["render_frame"]
                    or before["active_lod"] != after["active_lod"] or before["stage"] != capture["stage"]):
                record["failures"].append("Capture LOD/render-frame identity mismatch: " + capture["stage"])
            selection = before["lod_selection"]
            if record.get("blockout", False):
                if selection is not None or before["active_lod"] != 0 or after["active_lod"] != 0:
                    record["failures"].append("Historical blockout did not retain its fixed LOD0/no-presenter scope: " + capture["stage"])
            elif selection is None or selection["render_frame"] != before["render_frame"] or abs(selection["distance_m"] - before["displayed_distance_m"]) > 0.01:
                record["failures"].append("Capture LOD selection used stale camera/body distance: " + capture["stage"])
    frame_file = out / ("frames.jsonl" if mode == "driving" else "presentation-frames.jsonl")
    expected_hash = summary["frames"]["sha256"] if mode == "driving" else summary["frames_sha256"]
    if sha(frame_file) != expected_hash:
        record["failures"].append("Per-frame evidence hash mismatch")
    record["rendered_capture_count"] = len(captures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["driving", "presentation"], required=True)
    parser.add_argument("--blockout", action="store_true", help="Driving-only historical blockout revalidation; omits production presentation and the final LOD-driving stage")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--upstream-evidence", type=Path)
    parser.add_argument("--probe", choices=["mirrors"])
    parser.add_argument("--lighting", choices=["daylight", "night"], help="mirror-only diagnostic lighting; default daylight")
    parser.add_argument("--mirror-camera-source-y", type=float)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", type=Path, default=os.environ.get("GODOT_BIN"), help="pinned official .NET executable, or GODOT_BIN")
    parser.add_argument("--route-package", type=Path, required=True)
    parser.add_argument("--ffmpeg-bin", type=Path, help="directory containing ffmpeg/ffprobe; defaults to the local cache or PATH")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.godot is None:
        parser.error("provide --godot or GODOT_BIN")
    if args.probe and args.mode != "presentation":
        parser.error("--probe requires --mode presentation")
    if args.blockout and args.mode != "driving":
        parser.error("--blockout requires --mode driving")
    if (args.mirror_camera_source_y is not None or args.lighting is not None) and args.probe != "mirrors":
        parser.error("--lighting and --mirror-camera-source-y require --probe mirrors")
    if args.mirror_camera_source_y is not None and (not math.isfinite(args.mirror_camera_source_y) or not 0.4 <= args.mirror_camera_source_y <= 0.7):
        parser.error("--mirror-camera-source-y must be finite and within 0.4..0.7 meters")
    if not 30 <= args.timeout_seconds <= 3600:
        parser.error("--timeout-seconds must be within 30..3600")
    root = args.project_root.resolve()
    out = args.output.resolve()
    if out.exists():
        parser.error("existing evidence is preserved; choose a fresh --output")
    if not (root / "project.godot").is_file():
        parser.error("project.godot is absent from --project-root")
    out.mkdir(parents=True, exist_ok=False)
    (out / "capture-runner-input.py").write_bytes(Path(__file__).read_bytes())
    override = root / "override.cfg"
    prior_override = {"path": str(override), "existed": override.exists(), "sha256": sha(override) if override.exists() else None}
    record = dict(task_id="P1-018", mode=args.mode, status="failed", started_utc=utc(), platform=platform.platform(),
                  blockout=args.blockout,
                  milestone="M5", python=sys.version, project_root=str(root), git_revision=None,
                  commands=[], failures=[], override_before=prior_override, human_approval_reference=None,
                  limitations=["Movie Maker is fixed-timestep inspection, not real-time performance evidence.",
                               "Driving uses actual InputMap-conditioned physics; presentation uses explicitly posed fixtures.",
                               "Human visual, handling, physical-device and rights approvals remain open."])
    override_owned = False
    env = os.environ.copy()
    env.update(DOTNET_GCgen0size="800000")

    def run(label, argv, timeout=60):
        started = utc()
        with (out / (label + ".stdout.log")).open("wb") as stdout, (out / (label + ".stderr.log")).open("wb") as stderr:
            process = subprocess.Popen([str(x) for x in argv], cwd=root, env=env, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                       start_new_session=os.name != "nt")
            timed_out = False
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=stderr, stderr=stderr, check=False)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                exit_code = process.wait(timeout=30)
        result = dict(label=label, argv=[str(x) for x in argv], pid=process.pid, started_utc=started,
                      finished_utc=utc(), exit_code=exit_code, timed_out=timed_out)
        record["commands"].append(result)
        return result

    def require_command(label, argv, timeout=60, importing=False):
        result = run(label, argv, timeout)
        log = "\n".join((out / (label + suffix)).read_text(encoding="utf-8-sig", errors="replace") for suffix in [".stdout.log", ".stderr.log"])
        checked = "\n".join(line for line in log.splitlines() if not importing or line not in IMPORT_WARNINGS)
        if result["exit_code"] != 0 or result["timed_out"] or FATAL.search(checked):
            raise RuntimeError(f"{label} failed exit, timeout or strict diagnostic checks")
        return log.strip()

    try:
        if args.blockout:
            record["scope"] = "later revalidation of historical blockout using the corrected runtime/capture fixture"
            record["lod_policy"] = "fixed LOD0; production presenter and distance selection omitted by --sedan-blockout"
            record["limitations"].append("Historical blockout only: production mechanisms, materials, interior controls, mirrors and final LOD-driving acceptance are omitted.")
        if args.probe:
            record["diagnostic_probe"] = args.probe
            record["mirror_lighting"] = args.lighting or "daylight"
            record["diagnostic_side_mirror_camera_source_y_m"] = args.mirror_camera_source_y
            record["limitations"].append("Four-stage mirror diagnostic; cannot satisfy the full 55-stage native acceptance gate. Camera changes are temporary runtime anchor poses, not edited asset bytes.")
        if root != ROOT:
            if not args.upstream_evidence or "reports" not in root.parts:
                raise RuntimeError("An isolated candidate project requires its retained upstream evidence.")
            upstream = json.loads(args.upstream_evidence.read_text(encoding="utf-8-sig"))
            record["upstream_asset_diagnostic"] = {"path": str(args.upstream_evidence.resolve()), "sha256": sha(args.upstream_evidence), "status": upstream["status"]}
            record["limitations"].append("Isolated candidate capture only. Upstream asset-diagnostic failures remain open; this does not establish final asset acceptance.")
        if prior_override["existed"]:
            raise RuntimeError("Existing override.cfg preserved; use an isolated capture project or coordinate its settings before retrying.")
        cache = ROOT / ".tools/ffmpeg-9.0.1/ffmpeg-9.0.1-essentials_build/bin"
        directory = args.ffmpeg_bin or (cache if cache.is_dir() else None)
        suffix = ".exe" if os.name == "nt" else ""
        ffmpeg = directory / ("ffmpeg" + suffix) if directory else Path(shutil.which("ffmpeg") or "missing-ffmpeg")
        ffprobe = directory / ("ffprobe" + suffix) if directory else Path(shutil.which("ffprobe") or "missing-ffprobe")
        args.godot, args.route_package, ffmpeg, ffprobe = [path.resolve() for path in [args.godot, args.route_package, ffmpeg, ffprobe]]
        for executable in [args.godot, ffprobe, ffmpeg, args.route_package]:
            if not executable.is_file():
                raise FileNotFoundError(executable)
        expected = ["mirrors-configuration", "mirrors-live", "mirrors-door-follow", "mirrors-disabled"] if args.probe else DRIVING[:-1] if args.blockout else DRIVING if args.mode == "driving" else PRESENTATION
        record["expected_stages"] = expected
        record["git_revision"] = require_command("git-revision", ["git", "rev-parse", "HEAD"])
        env["CANNONBALL_GIT_REVISION"] = record["git_revision"]
        record["environment"] = {key: env[key] for key in ["DOTNET_GCgen0size", "CANNONBALL_GIT_REVISION"]}
        record["external_inputs"] = [{"path": str(p), "sha256": sha(p)} for p in [args.godot, args.route_package, ffprobe, ffmpeg, Path(__file__)]]
        record["tool_versions"] = {}
        for label, command in [("godot", [args.godot, "--version"]), ("dotnet", ["dotnet", "--version"]),
                               ("ffmpeg", [ffmpeg, "-version"]), ("ffprobe", [ffprobe, "-version"])]:
            record["tool_versions"][label] = require_command(label + "-version", command)
        if record["tool_versions"]["godot"] != json.loads((root / "tools/assets/toolchain.json").read_text())["godot"]["version"]:
            raise RuntimeError("Godot is not the pinned official .NET version")
        if record["tool_versions"]["dotnet"] != json.loads((root / "global.json").read_text())["sdk"]["version"]:
            raise RuntimeError("The executing .NET SDK does not match global.json")
        build = require_command("build", ["dotnet", "build", "Cannonball.csproj", "--nologo"], 300)
        if "0 Warning(s)" not in build or "0 Error(s)" not in build:
            raise RuntimeError("C# capture build was not warning-free")
        require_command("import", [args.godot, "--headless", "--path", root, "--editor", "--import"], 300, importing=True)
        record["input_hashes"] = {str(p.relative_to(root)).replace("\\", "/"): sha(p) for p in [
            *sorted((root / "game").rglob("*.cs")), *sorted((root / "game/Vehicle").rglob("*.tres")),
            *sorted((root / "game").rglob("*.cs.uid")),
            *sorted((root / "game/Vehicle").rglob("*.gdshader")),
            *sorted(p for p in (root / "assets").rglob("*") if p.is_file()),
            *sorted(p for p in (root / "src/Cannonball.Core").rglob("*.cs") if not set(p.parts) & {"bin", "obj"}),
            root / "game/Vehicle/Visuals/EnduranceSedan.tscn", root / "project.godot",
            root / "Cannonball.csproj", root / "global.json", root / "tools/vehicles/vehicle_contract.json",
            root / ".godot/mono/temp/bin/Debug/Cannonball.dll", root / ".godot/mono/temp/bin/Debug/Cannonball.Core.dll",
            root / "data/assets/vehicles/sources/endurance-sedan.blend",
            root / "data/assets/vehicles/derived/endurance-sedan.glb",
            root / "assets/vehicles/endurance-sedan/endurance-sedan.generated.tscn",
            root / "assets/vehicles/endurance-sedan/endurance-sedan.generated.textures.json",
            root / "docs/vehicles/endurance-sedan/specification.json", root / "tools/assets/toolchain.json",
        ]}
        with override.open("xb") as stream:
            stream.write(OVERRIDE)
        override_owned = True
        (out / "capture-override.cfg").write_bytes(OVERRIDE)
        record["override_capture_sha256"] = sha(override)
        movie = out / (args.mode + ".ogv")
        command = [args.godot, "--path", root, "--rendering-method", "forward_plus", "--resolution", "2560x1440", "--fullscreen",
                   "--fixed-fps", "30", "--write-movie", movie, "--log-file", out / "engine.log", "--",
                   "--route-package=" + str(args.route_package.resolve()), "--vehicle=endurance-sedan", "--environment-quality=high",
                   "--endurance-sedan-profile" if args.mode == "driving" else "--sedan-presentation-profile",
                   "--run-save-path=" + str(out / "run-save.json"),
                   "--sedan-captures", "--sedan-evidence-dir=" + str(out), "--telemetry-path=" + str(out / "telemetry.jsonl")]
        if args.probe:
            command.append("--sedan-presentation-probe=" + args.probe)
            command.append("--sedan-mirror-lighting=" + record["mirror_lighting"])
        if args.blockout:
            command.append("--sedan-blockout")
        if args.mirror_camera_source_y is not None:
            command.append("--sedan-mirror-camera-source-y=" + str(args.mirror_camera_source_y))
        process = run("godot", command, args.timeout_seconds)
        if process["exit_code"] != 0 or process["timed_out"]:
            record["failures"].append(f"Godot capture did not exit cleanly: {process}")
        logs = "\n".join((out / name).read_text(encoding="utf-8-sig", errors="replace") for name in ["godot.stdout.log", "godot.stderr.log", "engine.log"] if (out / name).exists())
        save_path_line = next((line for line in logs.splitlines() if line.startswith("CANNONBALL_AUTOMATION_SAVE_PATH ")), None)
        record["run_save_path"] = str(out / "run-save.json")
        try:
            if not save_path_line or Path(json.loads(save_path_line.removeprefix("CANNONBALL_AUTOMATION_SAVE_PATH "))["path"]).resolve() != out / "run-save.json":
                record["failures"].append("Run save was not isolated to its evidence directory")
        except (ValueError, KeyError, TypeError):
            record["failures"].append("Run save isolation record invalid")
        record["failure_markers"] = [match.group(0) for match in FATAL.finditer(logs)]
        if record["failure_markers"]:
            record["failures"].append("Engine error, warning, fatal or resource-leak diagnostic")
        if "CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true" not in logs:
            record["failures"].append("Controlled shutdown did not complete")
        marker = f"CANNONBALL_ENDURANCE_SEDAN_OK vehicle=endurance-sedan stages={len(expected)} " if args.mode == "driving" else f"CANNONBALL_SEDAN_PRESENTATION_OK stages={len(expected)} posed=true rendered=true"
        if marker not in logs:
            record["failures"].append("Capture suite completion marker absent")
        for stage in expected:
            stage_marker = (f"CANNONBALL_ENDURANCE_SEDAN_STAGE_OK vehicle=endurance-sedan stage={stage} " if args.mode == "driving"
                            else f"CANNONBALL_SEDAN_PRESENTATION_STAGE_OK stage={stage} posed=true")
            if stage_marker not in logs:
                record["failures"].append("Stage completion marker absent: " + stage)
        try:
            validate_summary(out, args.mode, expected, record)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exception:
            record["failures"].append("Invalid summary/capture evidence: " + str(exception))
        # Decode partial failed-scenario movies too. Actual decoded frame count
        # comes from FFprobe; duration times frame rate is only a timeline.
        probe = run("movie-probe", [ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_read_frames,duration:format=duration", "-of", "json", movie], 180)
        if probe["exit_code"] != 0 or probe["timed_out"]:
            raise RuntimeError("Movie stream probe failed")
        movie_info = json.loads((out / "movie-probe.stdout.log").read_text(encoding="utf-8"))
        record["decoded_movie"] = movie_info
        stream = movie_info["streams"][0]
        if stream["width"] != 2560 or stream["height"] != 1440 or int(stream["nb_read_frames"]) < 30:
            record["failures"].append("Decoded movie is not 2560x1440 with a nonempty sequence")
        decode = run("movie-full-decode", [ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-i", movie, "-map", "0:v:0", "-f", "null", "-"], 180)
        if decode["exit_code"] != 0 or decode["timed_out"]:
            record["failures"].append("Complete movie stream decode failed")
    except Exception as exception:
        record["failures"].append(f"{type(exception).__name__}: {exception}")
    finally:
        if "input_hashes" in record:
            record["input_hashes_after"] = {relative: sha(root / relative) if (root / relative).is_file() else None for relative in record["input_hashes"]}
            if record["input_hashes"] != record["input_hashes_after"]:
                record["failures"].append("Captured source/runtime/asset inputs changed during the native run")
        if override_owned:
            if override.exists() and override.read_bytes() == OVERRIDE:
                override.unlink()
                record["override_owned_file_removed"] = True
            else:
                record["failures"].append("Owned override changed or disappeared during capture; unexpected file left untouched")
        record["override_after"] = {"exists": override.exists(), "sha256": sha(override) if override.exists() else None}
        record["finished_utc"] = utc()
        record["status"] = "failed" if record["failures"] else "passed"
        record["output_hashes"] = {str(p.relative_to(out)).replace("\\", "/"): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "process.json"}
        (out / "process.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: record.get(key) for key in ["status", "mode", "rendered_capture_count", "failures", "override_after"]}), flush=True)
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exception:
        print(f"Capture configuration failed: {exception}", file=sys.stderr)
        raise SystemExit(1) from None
