# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow==11.3.0"]
# ///
"""Package actual, hash-verified sedan captures for independent human review.

Run with `uv run tools/vehicles/endurance_sedan/review.py --help`.
Images are copied unchanged. Contact sheets only resize and label them; movies
are encoded from every recorded source frame and fully decoded for validation.
"""

import argparse
import datetime
import hashlib
import html
import json
import math
import platform
import shutil
import subprocess
from pathlib import Path

import PIL
from PIL import Image, ImageDraw, ImageFont


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def named_path(value):
    name, separator, path = value.partition("=")
    if not separator or not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
        raise argparse.ArgumentTypeError("Use a unique lower-case label=path")
    return name, Path(path).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--render", action="append", type=named_path, default=[])
    parser.add_argument("--movie", action="append", type=named_path, default=[])
    parser.add_argument("--runtime", action="append", type=named_path, default=[])
    parser.add_argument("--runtime-scene", type=Path, help="Normalized delivered sedan scene; required with --runtime")
    parser.add_argument("--ffmpeg", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    source_hash = digest(source)
    labels = [name for name, _ in args.render + args.movie + args.runtime]
    if len(set(labels)) != len(labels):
        parser.error("Capture labels must be unique")
    if args.runtime and not args.runtime_scene:
        parser.error("--runtime requires --runtime-scene to bind captures to the delivered asset")
    output = args.output.resolve()
    if output.exists():
        parser.error("Use a new output directory; existing evidence is never replaced")
    ffmpeg = args.ffmpeg.resolve()
    ffprobe = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix == ".exe" else "ffprobe")
    output.mkdir(parents=True)
    manifest = {
        "task_id": "P1-018", "milestone": "M5", "status": "running",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source": str(source), "source_sha256": source_hash,
        "tool_sha256": digest(__file__), "python": platform.python_version(),
        "pillow": PIL.__version__, "commands": [], "captures": [],
        "human_approval_reference": None,
    }

    def save():
        (output / "review.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")

    def run(command, label):
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = subprocess.run([str(v) for v in command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        log = output / (label + ".log")
        log.write_bytes(result.stdout)
        manifest["commands"].append({"argv": [str(v) for v in command], "started_utc": started,
                                     "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                     "exit_status": result.returncode, "log": log.name, "sha256": digest(log)})
        save()
        if result.returncode:
            raise RuntimeError(f"{label} failed with exit {result.returncode}: {log}")
        return result.stdout.decode("utf-8")

    def movie(command, destination, label, expected=None):
        if command is not None:
            run(command, label + "-encode")
        details = json.loads(run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
                                  "-show_entries", "stream=width,height,nb_read_frames,avg_frame_rate,duration",
                                  "-of", "json", destination], label + "-probe"))["streams"][0]
        run([ffmpeg, "-v", "error", "-xerror", "-i", destination, "-f", "null", "-"], label + "-decode")
        if expected and (int(details["nb_read_frames"]) != expected[0] or
                         [details["width"], details["height"]] != expected[1]):
            raise RuntimeError(f"{label}: decoded frame count or dimensions disagree with capture manifest")
        return {"path": destination.relative_to(output).as_posix(), "sha256": digest(destination),
                "bytes": destination.stat().st_size, "decoded_stream": details}

    try:
        manifest["ffmpeg"] = run([ffmpeg, "-version"], "ffmpeg-version").splitlines()[0]
        for label, folder in args.render:
            capture = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            config = capture["configuration"]
            if capture["status"] != "completed" or config["source_sha256"] != source_hash:
                raise RuntimeError(f"{label}: incomplete capture or wrong Blender source")
            frames = capture["frames"]
            if len(frames) != config["frame_count"]:
                raise RuntimeError(f"{label}: incomplete frame inventory")
            destination = output / label
            destination.mkdir()
            for frame in frames:
                path = folder / frame["path"]
                if path.parent.resolve() != folder or digest(path) != frame["sha256"]:
                    raise RuntimeError(f"{label}: unsafe path or changed frame {frame['path']}")
                with Image.open(path) as original:
                    if list(original.size) != config["size"]:
                        raise RuntimeError(f"{label}: wrong frame size")
                if config["sequence"] == "none":
                    shutil.copy2(path, destination / path.name)
            shutil.copy2(folder / "manifest.json", destination / "capture.json")
            selected = frames if len(frames) <= 24 else [frames[round(i * (len(frames) - 1) / 23)] for i in range(24)]
            width, height, caption = 480, 270, 42
            columns = min(4, len(selected))
            sheet = Image.new("RGB", (columns * width, math.ceil(len(selected) / columns) * (height + caption)), "#17191d")
            draw = ImageDraw.Draw(sheet)
            font = ImageFont.load_default(size=15)
            for index, frame in enumerate(selected):
                x, y = (index % columns) * width, (index // columns) * (height + caption)
                with Image.open(folder / frame["path"]) as original:
                    thumbnail = original.convert("RGB")
                    thumbnail.thumbnail((width, height), Image.Resampling.LANCZOS)
                    sheet.paste(thumbnail, (x + (width - thumbnail.width) // 2, y + (height - thumbnail.height) // 2))
                draw.text((x + 10, y + height + 5), label + " / " + frame["view"], fill="white", font=font)
                draw.text((x + 10, y + height + 23), "Actual " + config["engine"] + " / " + config["lighting"], fill="#b8c0c8", font=font)
            sheet_path = destination / "contact-sheet.png"
            sheet.save(sheet_path)
            entry = {"label": label, "kind": "Blender capture", "input_manifest": str(folder / "manifest.json"),
                     "input_manifest_sha256": digest(folder / "manifest.json"), "configuration": config,
                     "contact_sheet": sheet_path.relative_to(output).as_posix(), "contact_sheet_sha256": digest(sheet_path),
                     "sampled_contact_sheet_frames": [f["view"] for f in selected], "actual_frame_count": len(frames)}
            if config["sequence"] != "none":
                if [f["path"] for f in frames] != [f"{i+1:06d}.png" for i in range(len(frames))]:
                    raise RuntimeError(f"{label}: sequence is not contiguous")
                encoded_path = folder / "encoded-movie.json"
                command = [ffmpeg, "-v", "error", "-n", "-framerate", str(config["fps"]),
                                         "-i", folder / "%06d.png", "-c:v", "libx264", "-preset", "slow",
                                         "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                                         destination / "inspection.mp4"]
                if encoded_path.exists():
                    encoded = json.loads(encoded_path.read_text(encoding="utf-8"))
                    binding = {"source_sha256": config["source_sha256"], "configuration_sha256": capture["configuration_sha256"],
                               "frames": [{"path": f["path"], "sha256": f["sha256"]} for f in frames]}
                    binding_hash = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
                    encoded_movie = (folder / encoded["path"]).resolve()
                    if encoded["status"] != "passed" or encoded["binding_sha256"] != binding_hash or encoded_movie.parent != folder or digest(encoded_movie) != encoded["sha256"]:
                        raise RuntimeError(f"{label}: encoded sequence is stale or changed")
                    shutil.copy2(encoded_movie, destination / "inspection.mp4")
                    shutil.copy2(encoded_path, destination / "encoded-movie.json")
                    entry["encoded_movie_record_sha256"] = digest(encoded_path)
                    command = None
                entry["movie"] = movie(command, destination / "inspection.mp4", label,
                                        (len(frames), config["size"]))
            manifest["captures"].append(entry)
            save()
        for label, path in args.movie:
            destination = output / (label + ".mp4")
            entry = {"label": label, "kind": "actual runtime capture", "input_path": str(path),
                     "input_sha256": digest(path), "movie": movie(
                         [ffmpeg, "-v", "error", "-n", "-i", path, "-c:v", "libx264", "-preset", "slow",
                          "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", destination],
                         destination, label)}
            manifest["captures"].append(entry)
            save()
        for label, folder in args.runtime:
            process_path = folder / "process.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            scene_key = "assets/vehicles/endurance-sedan/endurance-sedan.generated.tscn"
            if process["status"] != "passed" or process["input_hashes"].get(scene_key) != digest(args.runtime_scene):
                raise RuntimeError(f"{label}: failed native capture or wrong normalized sedan scene")
            if process["input_hashes"] != process["input_hashes_after"]:
                raise RuntimeError(f"{label}: runtime inputs changed during capture")
            destination = output / label
            destination.mkdir()
            retained = []
            for relative, expected_hash in process["output_hashes"].items():
                path = (folder / relative).resolve()
                if not path.is_relative_to(folder) or digest(path) != expected_hash:
                    raise RuntimeError(f"{label}: unsafe path or changed native output {relative}")
                if path.suffix.lower() in (".png", ".json", ".jsonl", ".cfg"):
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    retained.append({"path": target.relative_to(output).as_posix(), "sha256": expected_hash})
            shutil.copy2(process_path, destination / "process.json")
            original_movie = folder / (process["mode"] + ".ogv")
            movie_path = destination / "inspection.mp4"
            entry = {"label": label, "kind": "actual native Godot " + ("historical blockout " if process.get("blockout") else "") + process["mode"],
                     "historical_blockout_revalidation": bool(process.get("blockout")),
                     "process": (destination / "process.json").relative_to(output).as_posix(),
                     "process_sha256": digest(process_path), "normalized_scene_sha256": digest(args.runtime_scene),
                     "retained_outputs": retained, "limitations": process["limitations"],
                     "original_movie_sha256": digest(original_movie), "movie": movie(
                         [ffmpeg, "-v", "error", "-n", "-i", original_movie, "-c:v", "libx264", "-preset", "slow",
                          "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", movie_path],
                         movie_path, label)}
            manifest["captures"].append(entry)
            save()
        sections = []
        for capture in manifest["captures"]:
            label = html.escape(capture["label"])
            section = f'<section><h2>{label}</h2><p>{html.escape(capture["kind"])}</p>'
            config = capture.get("configuration", {})
            if config.get("technical_overlay"):
                overlay = config["technical_overlay"]
                legend = "; ".join(color + ": " + description for color, description in overlay["legend"].items())
                section += '<p>Technical x-ray with temporary materials. ' + html.escape(legend) + '. Rulers: 0.5 m minor ticks, 1 m major ticks.</p>'
            if config.get("inspection_fill_watts"):
                section += '<p>Inspection work light: ' + html.escape(str(config["inspection_fill_watts"])) + ' W, attached to the camera for enclosed assembly visibility.</p>'
            if "swatch_board" in config.get("views", "").split(","):
                section += '<p>Material board, left to right: top row Rubber, Trim, Paint; middle row Fabric, Carpet, Leather; bottom row Glass, Metal, Alloy. Individual full-size swatches are linked below.</p>'
            if config.get("sequence") not in (None, "none"):
                section += '<p>Blender source-control preview. Actual gameplay and runtime instruments appear in the separately labeled Godot captures.</p>'
            if "contact_sheet" in capture:
                sheet = html.escape(capture["contact_sheet"], quote=True)
                section += f'<a href="{sheet}"><img src="{sheet}" alt="{label} contact sheet"></a>'
            if "movie" in capture:
                path = html.escape(capture["movie"]["path"], quote=True)
                section += f'<video controls preload="metadata" src="{path}"></video><p><a href="{path}">Open full movie</a></p>'
            links = []
            for path in sorted((output / capture["label"]).glob("*.png")):
                if path.name == "contact-sheet.png":
                    continue
                links.append(f'<a href="{html.escape(path.relative_to(output).as_posix(), quote=True)}">{html.escape(path.stem)}</a>')
            if links:
                section += '<nav aria-label="Full resolution stills">' + " · ".join(links) + '</nav>'
            section += '</section>'
            sections.append(section)
        page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        page += '<title>Meridian S8R review</title><style>body{max-width:1500px;margin:32px auto;padding:0 24px;background:#17191d;color:#eef0f4;font:17px/1.5 system-ui}a{color:#9fd2ff}img,video{max-width:100%;height:auto}section{margin:48px 0}nav{line-height:2.1}code{overflow-wrap:anywhere}</style>'
        page += '<h1>Meridian S8R review</h1><p>Rendered vehicle inspection. Each group identifies its capture source. Human art, rights, handling and usability review remains open.</p>'
        page += f'<p>Blender source SHA-256: <code>{source_hash}</code></p><p><a href="review.json">Capture provenance and verification</a></p>'
        page += ''.join(sections) + '</html>'
        (output / "index.html").write_text(page, encoding="utf-8", newline="\n")
        manifest["gallery_sha256"] = digest(output / "index.html")
        manifest["status"] = "completed"
    except BaseException as error:
        manifest["status"] = "failed"
        manifest["failure"] = str(error)
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
