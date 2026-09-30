"""Verify immutable package bytes and run the selected sedan's headless suites.

This standalone Python 3.13+ tool needs no editor, source tree or installed .NET
runtime. It supplements the normal package verifier and native visual evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

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
    "mirrors-configuration", "lod-near", "lod-middle", "lod-far", "lod-return",
]
FATAL = re.compile(
    r"(?:^|\n)(?:ERROR|WARNING|SCRIPT ERROR):|Unhandled exception|Fatal error|AccessViolationException|"
    r"SIGSEGV|Segmentation fault|Leaked unsafe reference|ObjectDB instances leaked|resources still in use",
    re.IGNORECASE,
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_path(root, relative):
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or any(value in relative for value in ("\n", "\r", "\0"))
            or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts):
        raise ValueError("Unsafe package inventory path: " + repr(relative))
    result = root / relative
    if result.resolve() == root or not result.resolve().is_relative_to(root):
        raise ValueError("Package inventory path escapes root: " + relative)
    return result


def inventory(root):
    result = {}
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in folders + files:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError("Package contains a link or junction: " + str(path))
        for name in files:
            path = Path(directory) / name
            result[path.relative_to(root).as_posix()] = {"sha256": sha(path), "bytes": path.stat().st_size}
    return dict(sorted(result.items()))


def verification_fixture(root, manifest, files):
    fixtures = manifest.get("verification_fixtures", [])
    if len(fixtures) != 1:
        raise ValueError("Package must declare its single locked representative verification fixture")
    fixture = fixtures[0]
    prefix = "verification/fixtures/representative-corridor/"
    if (fixture.get("fixture") != "representative-corridor"
            or fixture.get("purpose") != "endurance-sedan-functional-verification"
            or fixture.get("default_launcher") is not False or fixture.get("continental_coverage_claim") is not False):
        raise ValueError("Verification fixture scope or identity mismatch")
    for name in ("pointer", "route_root", "metadata", "provenance"):
        relative = fixture[name]
        file = package_path(root, relative)
        if (not relative.startswith(prefix) or relative not in files
                or sha(file) != fixture[name + "_sha256"]):
            raise ValueError("Verification fixture artifact binding mismatch: " + name)
    pointer = json.loads(package_path(root, fixture["pointer"]).read_text())
    metadata = json.loads(package_path(root, fixture["metadata"]).read_text())
    provenance = json.loads(package_path(root, fixture["provenance"]).read_text())
    if (pointer["schema_version"] != 1 or metadata["schema_version"] != 5
            or pointer["content_version"] != fixture["content_version"]
            or metadata["content_version"] != fixture["content_version"]
            or prefix + pointer["root_relative_path"] != fixture["route_root"]
            or prefix + pointer["metadata_relative_path"] != fixture["metadata"]):
        raise ValueError("Verification fixture pointer/metadata correspondence mismatch")
    if (provenance.get("fixture") != fixture["fixture"] or provenance.get("purpose") != fixture["purpose"]
            or provenance.get("default_launcher") is not False
            or provenance.get("continental_coverage_claim") is not False
            or provenance.get("chunk_meters") != 2000 or provenance.get("source") != metadata.get("source")):
        raise ValueError("Verification fixture provenance scope mismatch")
    required = {
        "data/sources/catalog.json", "data/sources/representative-corridor-lock.json",
        "data/sources/fixtures/nhpn-boulder-westminster-us36.geojson",
        "data/sources/fixtures/nhpn-boulder-westminster-us36.manifest.json",
        "data/sources/fixtures/usgs-13-n40w106-boulder-westminster.tif",
        "data/sources/fixtures/usgs-13-n40w106-boulder-westminster.metadata.json",
    }
    inputs = {row["path"]: row for row in provenance["inputs"]}
    build_inputs = {row["path"]: row["sha256"] for row in manifest["build"]["inputs"]}
    if (len(inputs) != len(provenance["inputs"]) or set(inputs) != required
            or any(build_inputs.get(name) != item["sha256"] or item["bytes"] <= 0 for name, item in inputs.items())
            or metadata["source"]["acquisition_lock_sha256"] != inputs["data/sources/representative-corridor-lock.json"]["sha256"]
            or metadata["source"]["sha256"] != inputs["data/sources/fixtures/nhpn-boulder-westminster-us36.geojson"]["sha256"]):
        raise ValueError("Verification fixture locked build-input provenance mismatch")
    records = provenance["retained_source_records"]
    if (len(records) != 4 or {row["source_path"] for row in records} != {name for name in required if name.endswith(".json")}):
        raise ValueError("Verification fixture source record inventory mismatch")
    for row in records:
        file = package_path(root, row["path"])
        item = inputs[row["source_path"]]
        if (not row["path"].startswith(prefix + "provenance/") or row["path"] not in files
                or sha(file) != row["sha256"] or row["sha256"] != item["sha256"] or file.stat().st_size != item["bytes"]):
            raise ValueError("Verification fixture retained source record mismatch")
    expected_chunks = sorted((row["chunk_id"], prefix + row["relative_path"], row["content_hash"], row["byte_count"])
                             for row in metadata["chunks"])
    actual_chunks = sorted((row["id"], row["path"], row["sha256"], row["bytes"]) for row in fixture["chunks"])
    if not expected_chunks or expected_chunks != actual_chunks or len({row[0] for row in actual_chunks}) != len(actual_chunks):
        raise ValueError("Verification fixture chunk inventory mismatch")
    for _, name, digest, count in actual_chunks:
        file = package_path(root, name)
        if (not name.startswith(prefix + "chunks/" + fixture["content_version"] + "/") or name not in files
                or sha(file) != digest or file.stat().st_size != count):
            raise ValueError("Verification fixture chunk bytes mismatch")
    miles = sum(float(edge["length_meters"]) for edge in metadata["edges"]) / 1609.344
    if not miles > 1 or abs(miles - fixture["unique_route_miles"]) > 1e-9:
        raise ValueError("Verification fixture measured route extent mismatch")
    sbom = json.loads(package_path(root, "metadata/sbom.cdx.json").read_text())
    components = [row for row in sbom["components"] if row["name"] == "Cannonball representative-corridor verification fixture"]
    if (len(components) != 1 or components[0]["version"] != fixture["content_version"]
            or components[0]["hashes"] != [{"alg": "SHA-256", "content": fixture["route_root_sha256"]}]):
        raise ValueError("Verification fixture SBOM binding mismatch")
    return fixture


def validate_package(root, actual):
    manifest = json.loads((root / "metadata/manifest.json").read_text(encoding="utf-8-sig"))
    expected = {}
    for entry in manifest["files"]:
        relative = entry["path"]
        path = package_path(root, relative)
        if relative in expected:
            raise ValueError("Duplicate package inventory path: " + relative)
        expected[relative] = {key: entry[key] for key in ("sha256", "bytes")}
        if os.name != "nt" and f"{path.stat().st_mode & 0o777:04o}" != entry["mode"]:
            raise ValueError("Package file mode mismatch: " + relative)
    without_metadata = {key: value for key, value in actual.items()
                        if key not in ("metadata/manifest.json", "metadata/SHA256SUMS")}
    if expected != without_metadata:
        raise ValueError("Manifest inventory differs from actual package bytes")
    checksums = {}
    for line in (root / "metadata/SHA256SUMS").read_text().splitlines():
        if not re.fullmatch(r"[a-f0-9]{64}  .+", line):
            raise ValueError("Invalid package checksum line")
        digest, relative = line[:64], line[66:]
        package_path(root, relative)
        if relative in checksums:
            raise ValueError("Duplicate package checksum path")
        checksums[relative] = digest
    if checksums != {key: value["sha256"] for key, value in actual.items() if key != "metadata/SHA256SUMS"}:
        raise ValueError("Package checksums do not cover every delivered byte")
    artifact = manifest["artifact"]
    target = "windows" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else None
    if artifact["platform"] != target or artifact["architecture"] != "x86_64":
        raise ValueError("Package platform/architecture must match this native Windows or Linux host")
    if artifact["signed"] or artifact["public_release_ready"] or not artifact["fixture_scoped"]:
        raise ValueError("Unexpected package approval or fixture declaration")
    if manifest["build"]["godot_version"] != "4.7.1.stable.mono.official.a13da4feb":
        raise ValueError("Package does not declare the pinned official Godot build")
    for name in (artifact["launcher"], artifact["binary"], manifest["content"]["route_root"]):
        package_path(root, name)
        if name not in expected:
            raise ValueError("Package entrypoint/content is not inventory-listed")
    if not any(name.endswith(".pck") for name in expected) or not any(name.endswith("/Cannonball.dll") for name in expected):
        raise ValueError("Package is missing actual PCK or game assembly bytes")
    if native_binary(manifest) not in expected:
        raise ValueError("Declared native runtime binary is not inventory-listed")
    verification_fixture(root, manifest, expected)
    return manifest


def native_binary(manifest):
    binary = manifest["artifact"]["binary"]
    # Godot's official Windows console wrapper launches the adjacent GUI
    # executable; OS.GetExecutablePath reports that native child. Linux runs
    # the declared executable directly. No other inventory member is accepted.
    if manifest["artifact"]["platform"] == "windows" and binary.endswith(".console.exe"):
        return binary.removesuffix(".console.exe") + ".exe"
    return binary


def verify_case(case, mode, log, home, root, package_files, manifest):
    expected = DRIVING if mode == "driving" else PRESENTATION
    summary = json.loads((case / ("summary.json" if mode == "driving" else "presentation-summary.json")).read_text(encoding="utf-8-sig"))
    if (summary["status"] != "passed" or summary["expected_stages"] != expected
            or [row["stage"] for row in summary["completed_stages"]] != expected
            or any(row["status"] != "passed" for row in summary["completed_stages"])):
        raise ValueError(mode + " expected/completed stage inventory or status mismatch")
    if summary["runtime_is_debug_build"] or not Path(summary["user_data_directory"]).resolve().is_relative_to(home):
        raise ValueError("Packaged execution must be Release with actual isolated Godot user data")
    executable = Path(summary["executable_path"]).resolve()
    expected_executable = package_path(root, native_binary(manifest)).resolve()
    if executable != expected_executable or native_binary(manifest) not in package_files:
        raise ValueError("Observed runtime executable differs from the manifest's declared native binary")
    if summary["input_hashes"] or not summary["unavailable_input_paths"]:
        raise ValueError("Packaged source absence must be explicit; package bytes are bound externally")
    arguments = summary["scenario_arguments"] if mode == "driving" else summary["arguments"]
    if "--vehicle=endurance-sedan" not in arguments or "--sedan-blockout" in arguments:
        raise ValueError("Packaged execution did not select the complete sedan")
    fixture = manifest["verification_fixtures"][0]
    routes = [argument for argument in arguments if argument.startswith("--route-package")]
    if routes != ["--route-package=" + str(package_path(root, fixture["route_root"]))]:
        raise ValueError("Packaged execution must use exactly the manifest-bound verification route")
    if summary["engine"] != "4.7.1-stable (official)":
        raise ValueError("Actual runtime engine differs from the pinned official version")
    prefix = "CANNONBALL_ENDURANCE_SEDAN" if mode == "driving" else "CANNONBALL_SEDAN_PRESENTATION"
    vehicle = " vehicle=endurance-sedan" if mode == "driving" else ""
    marker = f"{prefix}_OK{vehicle} stages={len(expected)} "
    if marker not in log or "CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true" not in log:
        raise ValueError("Packaged suite completion or controlled shutdown marker missing")
    for stage in expected:
        if f"{prefix}_STAGE_OK{vehicle} stage={stage} " not in log:
            raise ValueError("Missing completed package stage: " + stage)
    save_lines = [line for line in log.splitlines() if line.startswith("CANNONBALL_AUTOMATION_SAVE_PATH ")]
    if len(save_lines) != 1 or Path(json.loads(save_lines[0].split(" ", 1)[1])["path"]).resolve() != case / "run-save.json":
        raise ValueError("Packaged run save path was not isolated to its evidence case")
    frames = case / ("frames.jsonl" if mode == "driving" else "presentation-frames.jsonl")
    frame_hash = summary["frames"]["sha256"] if mode == "driving" else summary["frames_sha256"]
    if sha(frames) != frame_hash:
        raise ValueError("Packaged frame evidence hash differs from summary")
    rows = [json.loads(line) for line in frames.read_text().splitlines()]
    physics = [row for row in rows if row.get("kind") == "physics-frame"] if mode == "driving" else rows
    if any(not any(row["stage"] == stage for row in physics) for stage in expected):
        raise ValueError("A completed package stage has no actual frame samples")
    if mode == "driving":
        if (summary["vehicle"] != "endurance-sedan" or summary["loaded_asset"] != "endurance-sedan"
                or summary["blockout_presentation_omitted"] or summary["physics_hz"] != 120
                or len(physics) != summary["physics_frames"] or not (case / "run-save.json").is_file()):
            raise ValueError("Packaged driving identity, physics rate, frame count or saved state mismatch")
        if any(row["resets"] < 0 or row["rebases"] < 0 for row in summary["completed_stages"]):
            raise ValueError("Invalid instance-scoped reset/rebase counts")
        camera = summary.get("reconstruction_camera") or {}
        camera_frames = camera.get("process_frames", [])
        camera_observations = camera.get("observations", [])
        if (camera.get("native_display") is not False or len(camera_frames) != 3
                or camera_frames != list(range(camera_frames[0], camera_frames[0] + 3))
                or [row.get("render_frame") for row in camera_observations] != camera_frames
                or camera.get("captures") or any(row.get("valid") is not True
                    or row.get("observation_boundary") != "headless-process-no-image" or row.get("vehicle_epoch") != 1
                    or row.get("native_arm_child_error_m", 1) > 0.001
                    or row.get("hit_length_m", -1) < row.get("spring_length_m", 0) - 0.01 for row in camera_observations)):
            raise ValueError("Missing first three consecutive packaged reconstruction camera observations")
        contact = summary.get("contact_shading") or {}
        if contact.get("enabled_by_setup") is not True or contact.get("supported_renderer") is not False:
            raise ValueError("Packaged headless contact-shading scope mismatch")
        previous_count = previous_frame = -1
        for stage in ("natural-rebase", "forced-rebase"):
            observed = (summary.get("rebase_observations") or {}).get(stage) or {}
            frames = observed.get("process_frames", [])
            count = observed.get("rebase_count", -1)
            if (len(set(frames)) < 3 or count <= observed.get("baseline_rebase_count", count)
                    or count <= previous_count or frames[0] <= previous_frame):
                raise ValueError("Missing separate packaged rebase observations: " + stage)
            previous_count, previous_frame = count, frames[-1]
        moving = {"keyboard-acceleration", "keyboard-braking", "controller-acceleration", "controller-braking",
                  "reverse", "steer-left", "steer-right", "suspension", "collision", "natural-rebase", "lod-driving"}
        if any(row["frozen"] for row in physics if row["stage"] in moving):
            raise ValueError("Packaged driving was frozen during a driving stage")
        if {row["lod"] for row in physics if row["stage"] == "lod-driving"} != {0, 1, 2}:
            raise ValueError("Packaged driving did not cross all three LODs")
        for stage, device in (("keyboard-acceleration", "Keyboard"), ("controller-acceleration", "Controller")):
            if not any(row["stage"] == stage and row["input_device"] == device and row["input"]["Throttle"] > 0.1 for row in physics):
                raise ValueError("Missing actual packaged input-device response: " + device)
    elif (summary["vehicle"] != "endurance-sedan" or summary["loaded_asset"] != "endurance-sedan"
            or summary["physics_hz"] != 120 or summary["frame_samples"] != len(physics)
            or summary["rendered"] is not False or summary["diagnostic_probe"] is not None
            or any(not row["frozen"] or row["source_geometry_visible"] for row in physics)):
        raise ValueError("Packaged presentation fixture scope is incorrect")
    return {"status": "passed", "stage_count": len(expected), "frame_count": len(physics),
            "expected_stages": expected, "actual_executable": str(executable),
            "declared_binary": manifest["artifact"]["binary"], "expected_native_binary": native_binary(manifest),
            "verification_fixture": fixture["fixture"], "route_root_sha256": fixture["route_root_sha256"],
            "actual_user_data_directory": summary["user_data_directory"], "source_files_absent": True,
            "engine": summary["engine"], "runtime_is_debug_build": summary["runtime_is_debug_build"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["all", "driving", "presentation"], default="all")
    parser.add_argument("--validate-only", action="store_true", help="Hash validation only; claims no runtime execution")
    parser.add_argument("--timeout-seconds", type=int, default=240, help="Per-process watchdog, 30..600 seconds")
    args = parser.parse_args()
    root, out = args.package.resolve(), args.output.resolve()
    if not root.is_dir() or not (root / "metadata/manifest.json").is_file():
        parser.error("--package must contain metadata/manifest.json")
    if out.exists() or out.is_relative_to(root) or root.is_relative_to(out):
        parser.error("Choose a new evidence directory disjoint from the immutable package")
    if not 30 <= args.timeout_seconds <= 600:
        parser.error("--timeout-seconds must be within 30..600")
    out.mkdir(parents=True)
    shutil.copy2(__file__, out / "verifier-input.py")
    record = {"task_id": "P1-018", "milestone": "M5", "status": "failed", "started_utc": utc(),
              "platform": platform.platform(), "python": sys.version, "package": str(root),
              "commands": [], "cases": {}, "failures": [], "human_approval_reference": None,
              "scope": "immutable package validation only" if args.validate_only else "selected sedan packaged headless functional execution",
              "limitations": ["Headless state checks do not prove native visuals, mirror pixels, frame performance or physical device usability.",
                              "Human visual, handling, accessibility and source/output rights reviews remain open."]}
    before = None
    try:
        before = inventory(root)
        record["package_before"] = before
        manifest = validate_package(root, before)
        record["source_revision"] = manifest["source"]["revision"]
        record["declared_build"] = manifest["build"]
        record["packaged_content"] = manifest["content"]
        fixture = manifest["verification_fixtures"][0]
        record["verification_fixture"] = fixture
        record["default_launcher_invoked"] = False
        record["shipping_runtime_hashes"] = {key: value for key, value in before.items() if key.endswith((".pck", ".dll", ".exe", ".x86_64"))}
        if not args.validate_only:
            for mode in (["driving", "presentation"] if args.mode == "all" else [args.mode]):
                case = out / mode
                case.mkdir()
                with tempfile.TemporaryDirectory(prefix="cannonball-packaged-sedan-") as temporary:
                    home = Path(temporary).resolve()
                    (home / "empty-dotnet-root").mkdir()
                    environment = os.environ.copy()
                    environment.update(HOME=str(home), XDG_DATA_HOME=str(home / "xdg-data"), APPDATA=str(home / "appdata"),
                                       LOCALAPPDATA=str(home / "localappdata"), DOTNET_ROOT=str(home / "empty-dotnet-root"),
                                       DOTNET_ROOT_X64=str(home / "empty-dotnet-root"), DOTNET_MULTILEVEL_LOOKUP="0",
                                       DOTNET_GCgen0size="800000", CANNONBALL_RELEASE_SMOKE="1",
                                       CANNONBALL_GIT_REVISION=manifest["source"]["revision"])
                    for key in list(environment):
                        if key.startswith("PLAYGODOT_"):
                            environment.pop(key)
                    arguments = [str(package_path(root, native_binary(manifest))), "--headless",
                                 "--rendering-method", "gl_compatibility", "--fixed-fps", "120",
                                 "--log-file", str(case / "engine.log"), "--",
                                 "--route-package=" + str(package_path(root, fixture["route_root"])), "--vehicle=endurance-sedan",
                                 "--endurance-sedan-profile" if mode == "driving" else "--sedan-presentation-profile",
                                 "--sedan-evidence-dir=" + str(case), "--run-save-path=" + str(case / "run-save.json"),
                                 "--telemetry-path=" + str(case / "telemetry.jsonl")]
                    command = {"argv": arguments, "cwd": str(home), "started_utc": utc(), "timed_out": False,
                               "shell": False, "environment": {key: environment.get(key) for key in (
                                   "HOME", "XDG_DATA_HOME", "APPDATA", "LOCALAPPDATA", "DOTNET_ROOT", "DOTNET_ROOT_X64",
                                   "DOTNET_MULTILEVEL_LOOKUP", "DOTNET_GCgen0size", "DOTNET_ROLL_FORWARD", "CANNONBALL_RELEASE_SMOKE", "CANNONBALL_GIT_REVISION")}}
                    record["commands"].append(command)
                    logs = []
                    command["exit_status"] = None
                    try:
                        with (case / "stdout.log").open("wb") as stdout, (case / "stderr.log").open("wb") as stderr:
                            process = subprocess.Popen(arguments, cwd=home, env=environment, stdout=stdout, stderr=stderr,
                                                       shell=False, start_new_session=os.name != "nt",
                                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                            command["pid"] = process.pid
                            try:
                                command["exit_status"] = process.wait(args.timeout_seconds)
                            except subprocess.TimeoutExpired:
                                command["timed_out"] = True
                                if os.name == "nt":
                                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=stderr,
                                                   stderr=stderr, check=False, timeout=30)
                                else:
                                    os.killpg(process.pid, signal.SIGKILL)
                                command["exit_status"] = process.wait(30)
                    except Exception as error:
                        command["process_error"] = f"{type(error).__name__}: {error}"
                        raise
                    finally:
                        # Preserve engine diagnostics even if launch, tree kill,
                        # or the bounded post-kill wait fails, before the
                        # disposable user directory leaves its context.
                        command["finished_utc"] = utc()
                        for index, path in enumerate(sorted(home.rglob("*.log"))):
                            retained = case / f"user-{index:02d}-{path.name}"
                            shutil.copy2(path, retained)
                            logs.append(retained)
                        logs += [path for path in (case / "stdout.log", case / "stderr.log", case / "engine.log") if path.is_file()]
                        command["logs"] = {path.name: sha(path) for path in logs}
                    log = "\n".join(path.read_text(encoding="utf-8-sig", errors="replace") for path in logs)
                    log = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", log).replace("\r", "")
                    if command["exit_status"] != 0 or command["timed_out"] or FATAL.search(log) or "PLAYGODOT_" in log:
                        raise ValueError(mode + " process failed, timed out or reported a forbidden runtime diagnostic")
                    if f"content_version={fixture['content_version']}" not in log:
                        raise ValueError("Packaged route content identity is absent")
                    # The native Windows GUI executable may have no console.
                    # Its explicit engine log is the single authoritative copy.
                    engine_text = (case / "engine.log").read_text(encoding="utf-8-sig", errors="replace").replace("\r", "")
                    record["cases"][mode] = verify_case(case, mode, engine_text, home, root, before, manifest)
                command["disposable_user_data_removed"] = not home.exists()
        record["status"] = "package_hashes_validated_no_runtime_claim" if args.validate_only else "passed"
    except Exception as error:
        record["failures"].append(str(error))
    finally:
        if before is not None:
            try:
                record["package_after"] = inventory(root)
                if record["package_after"] != before:
                    record["failures"].append("Immutable package changed during verification")
            except Exception as error:
                record["failures"].append("Package post-verification inventory failed: " + str(error))
        if record["failures"]:
            record["status"] = "failed"
        record["output_hashes"] = {path.relative_to(out).as_posix(): sha(path) for path in out.rglob("*") if path.is_file()}
        record["finished_utc"] = utc()
        (out / "evidence.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": record["status"], "failures": record["failures"], "evidence": str(out / "evidence.json")}))
    return 1 if record["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
