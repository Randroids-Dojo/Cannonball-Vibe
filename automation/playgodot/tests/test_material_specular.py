from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKER = "tools/vehicles/pack_imported_scene.gd"
VALIDATOR = "tools/vehicles/validate_import.gd"
FACTOR = 0.11999999731779099
META = "cannonball_specular_response"
NATIVE = pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="Requires official Godot")


def _out(tmp_path: Path, label: str) -> Path:
    base = Path(os.environ.get("PLAYGODOT_ARTIFACT_DIR", str(tmp_path)))
    out = base / ("material-specular-" + label)
    out.mkdir(parents=True, exist_ok=False)
    return out


def _run(project: Path, out: Path, label: str, args: list[str], *, rejected: bool = False) -> str:
    command = [os.environ["GODOT_BIN"], "--headless", "--path", str(project), *args]
    env = os.environ.copy()
    env.update(
        {
            "APPDATA": str(out / "user/roaming"),
            "LOCALAPPDATA": str(out / "user/local"),
            "XDG_DATA_HOME": str(out / "user/data"),
            "XDG_CONFIG_HOME": str(out / "user/config"),
        }
    )
    result = subprocess.run(command, env=env, capture_output=True, timeout=60)
    log = result.stdout + result.stderr
    (out / (label + ".log")).write_bytes(log)
    (out / (label + ".command.json")).write_text(
        json.dumps(
            {
                "argv": command,
                "returncode": result.returncode,
                "log_sha256": hashlib.sha256(log).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    text = log.decode(errors="replace")
    assert "v4.7.1.stable.mono.official.a13da4feb" in text, text
    assert result.returncode == (1 if rejected else 0), text
    assert "SCRIPT ERROR:" not in text, text
    if rejected:
        assert "SCREEN_SPECULAR:" in text, text
    else:
        assert "ERROR:" not in text, text
    for bad in ("ObjectDB instances leaked", "resources still in use", "RID allocations", "FATAL"):
        assert bad not in text, text
    return text


def _document(extension: dict | None = None) -> dict:
    material = {
        "name": "Material_Screen",
        "extras": {"cv_shader": "standard"},
        "pbrMetallicRoughness": {
            "metallicFactor": 0,
            "roughnessFactor": 0.32,
            "baseColorFactor": [0.006, 0.010, 0.013, 1],
        },
    }
    if extension is not None:
        material["extensions"] = {"KHR_materials_specular": extension}
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": "AssetRoot", "children": [1, 2, 3]},
            *[{"name": f"LOD{lod}_Screen", "mesh": 0} for lod in range(3)],
        ],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}
                ]
            }
        ],
        "materials": [material],
        "buffers": [{"byteLength": 80}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 36},
            {"buffer": 0, "byteOffset": 72, "byteLength": 6},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 0],
            },
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
    }
    if extension is not None:
        document["extensionsUsed"] = ["KHR_materials_specular"]
    return document


def _glb(document: dict) -> bytes:
    header = json.dumps(document, separators=(",", ":"), allow_nan=False).encode()
    header += b" " * (-len(header) % 4)
    data = struct.pack("<18f3H2x", 0, 0, 0, 1, 0, 0, 0, 1, 0, *([0, 0, 1] * 3), 0, 1, 2)
    return (
        struct.pack("<III", 0x46546C67, 2, 28 + len(header) + len(data))
        + struct.pack("<II", len(header), 0x4E4F534A)
        + header
        + struct.pack("<II", len(data), 0x004E4942)
        + data
    )


def _project(out: Path, document: dict) -> Path:
    project = out / "project"
    project.mkdir()
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Screen scalar fixture"\n',
    )
    for relative in (PACKER, VALIDATOR):
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (project / "screen.glb").write_bytes(_glb(document))
    return project


def _script(project: Path, text: str, name: str = "probe.gd") -> str:
    (project / name).write_text(text)
    return "res://" + name


SNAPSHOT = """
func material_rows(node: Node) -> Array:
    var result: Array = []
    var stack: Array[Node] = [node]
    while not stack.is_empty():
        var item: Node = stack.pop_back()
        for child in item.get_children(): stack.append(child)
        if item is MeshInstance3D:
            for surface in item.mesh.get_surface_count():
                var material: Material = item.get_active_material(surface)
                result.append({"path": str(node.get_path_to(item)), "surface": surface,
                    "rid": material.get_rid().get_id(), "name": material.resource_name,
                    "specular": material.metallic_specular,
                    "roughness": material.roughness, "metallic": material.metallic,
                    "metadata": material.get_meta("cannonball_specular_response")
                        if material.has_meta("cannonball_specular_response") else null})
    return result
func save_result(value: Dictionary) -> void:
    var file := FileAccess.open("res://result.json", FileAccess.WRITE)
    file.store_string(JSON.stringify(value, "  ", true, true) + "\\n")
    file.close()
"""


@NATIVE
@pytest.mark.parametrize(
    "extension",
    [None, {}, {"specularFactor": 0}, {"specularFactor": FACTOR}, {"specularFactor": 1}],
    ids=["absent", "default", "zero", "authored", "one"],
)
def test_specular_adapter_real_pack_and_reload(tmp_path: Path, extension: dict | None) -> None:
    label = (
        "absent"
        if extension is None
        else "factor-" + str(extension.get("specularFactor", "default"))
    )
    out = _out(tmp_path, label)
    project = _project(out, _document(extension))
    _run(project, out, "import", ["--editor", "--import"])
    for name in ("first", "second"):
        _run(
            project,
            out,
            name,
            [
                "--script",
                "res://" + PACKER,
                "--",
                "res://screen.glb",
                "res://" + name + ".tscn",
                "--vehicle",
                "endurance-sedan",
            ],
        )
    assert (project / "first.tscn").read_bytes() == (project / "second.tscn").read_bytes()
    assert (project / "first.textures.json").read_bytes() == (
        project / "second.textures.json"
    ).read_bytes()
    probe = _script(
        project,
        """extends SceneTree
func _init() -> void:
    var raw: Node = load("res://screen.glb").instantiate()
    var adapted: Node = load("res://first.tscn").instantiate()
    var bytes := FileAccess.get_file_as_bytes("res://screen.glb")
    var document: Dictionary = JSON.parse_string(
        bytes.slice(20, 20 + bytes.decode_u32(12)).get_string_from_utf8())
    var source_extension: Dictionary = document.materials[0].get("extensions", {}).get(
        "KHR_materials_specular", {})
    var decoded_factor: float = source_extension.get("specularFactor", 1.0)
    var bits := PackedByteArray()
    bits.resize(8)
    bits.encode_double(0, decoded_factor)
    save_result({"raw": material_rows(raw), "adapted": material_rows(adapted),
        "independent_native_decoded_factor": decoded_factor,
        "source_factor_bits": bits.hex_encode()})
    raw.free()
    adapted.free()
    quit(0)
"""
        + SNAPSHOT,
    )
    _run(project, out, "reload", ["--script", probe])
    result = json.loads((project / "result.json").read_text())
    assert len(result["raw"]) == len(result["adapted"]) == 3
    for before, after in zip(result["raw"], result["adapted"], strict=True):
        assert before["metadata"] is None and before["specular"] == 0.5
        assert {k: v for k, v in before.items() if k not in {"metadata", "rid"}} == {
            k: v for k, v in after.items() if k not in {"metadata", "rid"}
        }
        if extension is None:
            assert after["metadata"] is None
        else:
            assert after["metadata"] == {
                "schema": "khr-specular-f0.v1",
                "specular_factor": result["independent_native_decoded_factor"],
            }
    assert len({r["rid"] for r in result["raw"]}) == len({r["rid"] for r in result["adapted"]})


@NATIVE
@pytest.mark.parametrize("wrong_resource", [False, True])
def test_specular_precision_rewrite_preserves_every_unrelated_byte(
    tmp_path: Path,
    wrong_resource: bool,
) -> None:
    out = _out(tmp_path, "precision-isolation-" + str(wrong_resource))
    project = _project(out, _document({"specularFactor": FACTOR}))
    _run(project, out, "import", ["--editor", "--import"])
    probe = _script(
        project,
        """extends "res://tools/vehicles/pack_imported_scene.gd"
func _init() -> void:
    var plan := _screen_specular_plan("res://screen.glb")
    # Deliberate binary64 fixture: force a real shortened-text difference,
    # independently of Godot's one-ULP JSON decoding of the actual source token.
    plan.factor = PackedByteArray([0, 0, 0, 224, 81, 184, 190, 63]).decode_double(0)
    var scene: Node = load("res://screen.glb").instantiate()
    var target: MeshInstance3D = scene.find_child("LOD0_Screen", true, false)
    var material: Material = target.mesh.surface_get_material(0)
    material.set_meta("unrelated", {"specular_factor": plan.factor})
    _bind_screen_specular(scene, plan)
    _assign_owner(scene, scene)
    var packed := PackedScene.new()
    assert(packed.pack(scene) == OK)
    assert(ResourceSaver.save(packed, "res://raw.tscn") == OK)
    var before := FileAccess.get_file_as_string("res://raw.tscn")
    @CHANGE@
    var after := _preserve_screen_specular_precision(before, plan)
    save_result({"before": before, "after": after, "failed": _failed})
    scene.free()
    quit(1 if _failed else 0)
""".replace(
            "@CHANGE@",
            "before = before.replace('resource_name = \"Material_Screen\"', "
            "'resource_name = \"Other\"')"
            if wrong_resource
            else "pass",
        )
        + SNAPSHOT,
    )
    _run(project, out, "precision", ["--script", probe], rejected=wrong_resource)
    result = json.loads((project / "result.json").read_text())
    if wrong_resource:
        assert result["failed"] and result["before"] == result["after"]
        return
    before, after = (
        result["before"].splitlines(keepends=True),
        result["after"].splitlines(keepends=True),
    )
    assert len(before) == len(after) and not result["failed"]
    inside = False
    protected = []
    changed = 0
    for original, actual in zip(before, after, strict=True):
        if original.startswith("metadata/" + META + " = {"):
            inside = True
        elif inside and original.startswith('"specular_factor": '):
            assert json.loads(actual.split(": ", 1)[1]) == FACTOR
            changed += original != actual
        else:
            assert original == actual
            if original.startswith('"specular_factor": '):
                protected.append(original)
        if original.rstrip() == "}":
            inside = False
    assert len(protected) == 1, "The same-number unrelated field must be present and unchanged"
    assert changed == 1, "The precision control must exercise an actual reserved-field rewrite"


BAD_DOCUMENTS = [
    "bool",
    "string",
    "null",
    "negative",
    "large",
    "texture",
    "color",
    "unknown",
    "ior",
    "metallic",
    "family",
    "duplicate",
    "reserved",
    "required",
    "unused",
    "materials-type",
    "material-type",
    "json-type",
    "header",
    "chunk",
]


def _invalid_document(case: str) -> bytes:
    document = _document({"specularFactor": FACTOR})
    material = document["materials"][0]
    extension = material["extensions"]["KHR_materials_specular"]
    values = {"bool": True, "string": "0.12", "null": None, "negative": -0.01, "large": 1.01}
    if case in values:
        extension["specularFactor"] = values[case]
    elif case in {"texture", "color", "unknown"}:
        extension[
            {"texture": "specularTexture", "color": "specularColorFactor", "unknown": "other"}[case]
        ] = {"index": 0} if case == "texture" else [1, 1, 1]
    elif case == "ior":
        material["extensions"]["KHR_materials_ior"] = {"ior": 1.5}
    elif case == "metallic":
        material["pbrMetallicRoughness"]["metallicFactor"] = 1
    elif case == "family":
        material["extras"]["cv_shader"] = "glass"
    elif case == "duplicate":
        document["materials"].append(copy.deepcopy(material))
    elif case == "reserved":
        material["extras"][META] = {"schema": "khr-specular-f0.v1", "specular_factor": 0.9}
    elif case == "required":
        document["extensionsRequired"] = ["KHR_materials_specular"]
    elif case == "unused":
        document["extensionsUsed"] = []
    elif case == "materials-type":
        document["materials"] = {}
    elif case == "material-type":
        document["materials"] = [None]
    elif case == "json-type":
        document = []
    data = bytearray(_glb(document))
    if case == "header":
        data[0] = 0
    if case == "chunk":
        struct.pack_into("<I", data, 12, len(data) * 2)
    return bytes(data)


@NATIVE
@pytest.mark.parametrize("case", BAD_DOCUMENTS)
def test_specular_adapter_rejects_before_output_replacement(tmp_path: Path, case: str) -> None:
    out = _out(tmp_path, "bad-source-" + case)
    project = _project(out, _document())
    (project / "screen.glb").write_bytes(_invalid_document(case))
    sentinels = {"saved.tscn": b"preserve-scene\n", "saved.textures.json": b"preserve-sidecar\n"}
    for name, data in sentinels.items():
        (project / name).write_bytes(data)
    _run(
        project,
        out,
        "reject",
        [
            "--script",
            "res://" + PACKER,
            "--",
            "res://screen.glb",
            "res://saved.tscn",
            "--vehicle",
            "endurance-sedan",
        ],
        rejected=True,
    )
    assert all((project / name).read_bytes() == data for name, data in sentinels.items())


BIND_CHANGES = {
    "missing": "target.free()",
    "extra": (
        'var extra := target.duplicate()\n    extra.name = "ExtraScreen"\n'
        "    scene.add_child(extra)"
    ),
    "parent": "target.reparent(scene)",
    "family": 'material.get_meta("extras")["cv_shader"] = "glass"',
    "metallic": "material.metallic = 1",
    "reserved": 'material.set_meta("cannonball_specular_response", {})',
    "wrong-material": 'material.resource_name = "Other"',
    "triangles": "target.mesh = BoxMesh.new()\n    target.mesh.material = material",
}


@NATIVE
@pytest.mark.parametrize("case", BIND_CHANGES)
def test_specular_binding_rejects_actual_membership_drift(tmp_path: Path, case: str) -> None:
    out = _out(tmp_path, "binding-" + case)
    project = _project(out, _document({"specularFactor": FACTOR}))
    _run(project, out, "import", ["--editor", "--import"])
    probe = _script(
        project,
        """extends "res://tools/vehicles/pack_imported_scene.gd"
func _init() -> void:
    var plan := _screen_specular_plan("res://screen.glb")
    var scene: Node = load("res://screen.glb").instantiate()
    var target: MeshInstance3D = scene.find_child("LOD0_Screen", true, false)
    var material: Material = target.mesh.surface_get_material(0)
    @CHANGE@
    var before: Variant = material.get_meta("cannonball_specular_response") \
        if material.has_meta("cannonball_specular_response") else null
    _bind_screen_specular(scene, plan)
    save_result({"failed": _failed, "before": before,
        "after": material.get_meta("cannonball_specular_response")
            if material.has_meta("cannonball_specular_response") else null})
    scene.free()
    quit(1 if _failed else 0)
""".replace("@CHANGE@", BIND_CHANGES[case])
        + SNAPSHOT,
    )
    _run(project, out, "reject", ["--script", probe], rejected=True)
    result = json.loads((project / "result.json").read_text())
    assert result["failed"] and result["before"] == result["after"]


@NATIVE
@pytest.mark.parametrize(
    "case",
    ["valid", "no-op", "missing-lod", "wrong-006", "wrong-012", "wrong-050", "stale", "extra"],
)
def test_specular_validator_uses_raw_source_expectation(tmp_path: Path, case: str) -> None:
    out = _out(tmp_path, "validator-" + case)
    project = _project(out, _document({"specularFactor": FACTOR}))
    _run(project, out, "import", ["--editor", "--import"])
    _run(
        project,
        out,
        "pack",
        [
            "--script",
            "res://" + PACKER,
            "--",
            "res://screen.glb",
            "res://saved.tscn",
            "--vehicle",
            "endurance-sedan",
        ],
    )
    changes = {
        "valid": "pass",
        "no-op": 'material.remove_meta("cannonball_specular_response")',
        "missing-lod": "target.free()",
        "wrong-006": "material.metallic_specular = .06",
        "wrong-012": "material.metallic_specular = .12",
        "wrong-050": "material.metallic_specular = .5",
        "stale": 'material.get_meta("cannonball_specular_response")["specular_factor"] = .13',
        "extra": BIND_CHANGES["extra"],
    }
    probe = _script(
        project,
        """extends "res://tools/vehicles/validate_import.gd"
func _init() -> void:
    var expected := _expected_screen_specular("res://screen.glb")
    var scene: Node = load("res://saved.tscn").instantiate()
    var target: MeshInstance3D = scene.find_child("LOD0_Screen", true, false)
    var material: StandardMaterial3D = target.mesh.surface_get_material(0)
    material.metallic_specular = .5 * sqrt(expected.factor)
    @CHANGE@
    var result := _validate_screen_specular(scene, expected)
    save_result({"errors": _errors, "result": result})
    scene.free()
    quit(0 if _errors.is_empty() else 1)
""".replace("@CHANGE@", changes[case])
        + SNAPSHOT,
    )
    _run(project, out, "check", ["--script", probe], rejected=case != "valid")
    result = json.loads((project / "result.json").read_text())
    if case == "valid":
        assert not result["errors"] and len(result["result"]["surfaces"]) == 3
    else:
        assert result["errors"]


WRAPPER_CASES = [
    "absent",
    "zero",
    "authored",
    "one",
    "schema",
    "missing",
    "extra",
    "type",
    "bool",
    "string",
    "null",
    "nan",
    "infinite",
    "negative",
    "large",
    "family",
    "identity",
    "metallic",
    "unshaded",
    "specular-mode",
]


PROPERTY_SNAPSHOT = """
func native_value(value: Variant) -> Variant:
    if value is Resource:
        var result := {"class": value.get_class(), "path": value.resource_path,
            "name": value.resource_name}
        if value is Shader: result["code"] = value.code
        if value is Texture2D:
            result["size"] = [value.get_width(), value.get_height()]
        return result
    if value is Vector2: return [value.x, value.y]
    if value is Vector3: return [value.x, value.y, value.z]
    if value is Color: return [value.r, value.g, value.b, value.a]
    if value is Dictionary:
        var result := {}
        for key in value: result[str(key)] = native_value(value[key])
        return result
    if value is Array:
        var result := []
        for item in value: result.append(native_value(item))
        return result
    if value is float and not is_finite(value): return {"nonfinite": str(value)}
    return value
func native_properties(material: Material) -> Dictionary:
    if material == null: return {"native_class": "null"}
    var result := {"native_class": material.get_class()}
    for field in material.get_property_list():
        if int(field.usage) & PROPERTY_USAGE_STORAGE:
            result[str(field.name)] = native_value(material.get(field.name))
    if material is StandardMaterial3D:
        for key in ["metallic_specular", "metallic", "roughness", "shading_mode",
                "specular_mode", "clearcoat_enabled", "clearcoat", "clearcoat_roughness"]:
            result[key] = material.get(key)
    return result
func shutdown_fixture(body: Node) -> void:
    body.queue_free()
    await process_frame
    await process_frame
    var owner := Node3D.new()
    root.add_child(owner)
    owner.set_script(load("res://game/Main.cs"))
    owner.process_mode = Node.PROCESS_MODE_DISABLED
    owner.notification(Node.NOTIFICATION_WM_CLOSE_REQUEST)
"""


def _wrapper_script(out: Path, case: str) -> Path:
    script = out / "wrapper.gd"
    declaration = json.dumps({"schema": "khr-specular-f0.v1", "specular_factor": FACTOR})
    changes = {
        "absent": 'candidate.remove_meta("cannonball_specular_response")',
        "zero": "declaration.specular_factor = 0",
        "authored": "pass",
        "one": "declaration.specular_factor = 1",
        "schema": 'declaration.schema = "unsupported"',
        "missing": 'declaration.erase("specular_factor")',
        "extra": "declaration.extra = 1",
        "type": 'candidate.set_meta("cannonball_specular_response", "wrong")',
        "bool": "declaration.specular_factor = true",
        "string": 'declaration.specular_factor = ".12"',
        "null": "declaration.specular_factor = null",
        "nan": "declaration.specular_factor = NAN",
        "infinite": "declaration.specular_factor = INF",
        "negative": "declaration.specular_factor = -.01",
        "large": "declaration.specular_factor = 1.01",
        "family": 'candidate.get_meta("extras")["cv_shader"] = "glass"',
        "identity": 'candidate.resource_name = "Other"',
        "metallic": "candidate.metallic = 1",
        "unshaded": "candidate.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED",
        "specular-mode": "candidate.specular_mode = BaseMaterial3D.SPECULAR_DISABLED",
    }
    script.write_text(
        """extends SceneTree
func _initialize() -> void:
    call_deferred("run_fixture")
func run_fixture() -> void:
    var body: Node = load("res://game/Vehicle/Visuals/EnduranceSedan.tscn").instantiate()
    body.process_mode = Node.PROCESS_MODE_DISABLED
    var stack: Array[Node] = [body]
    var candidate: StandardMaterial3D
    var count := 0
    while not stack.is_empty():
        var node: Node = stack.pop_back()
        for child in node.get_children(): stack.append(child)
        if not node is MeshInstance3D or node.mesh == null: continue
        for surface in node.mesh.get_surface_count():
            var material: Material = node.mesh.surface_get_material(surface)
            if material != null and material.resource_name == "Material_Screen":
                if candidate == null:
                    candidate = material.duplicate()
                    candidate.set_meta("extras", {"cv_shader": "standard"})
                    candidate.metallic_specular = .37
                node.mesh.surface_set_material(surface, candidate)
                count += 1
    assert(candidate != null and count > 0)
    var declaration: Dictionary = @DECL@
    candidate.set_meta("cannonball_specular_response", declaration)
    @CHANGE@
    var before := candidate.metallic_specular
    var before_properties := native_properties(candidate)
    root.add_child(body)
    var complete: bool = body.get_meta("automation_state", {}).has("polished_material_surfaces")
    var file := FileAccess.open(@OUT@, FileAccess.WRITE)
    file.store_string(JSON.stringify({"before": before, "after": candidate.metallic_specular,
        "complete": complete, "surfaces": count, "before_properties": before_properties,
        "after_properties": native_properties(candidate)}, "  ", true, true) + "\\n")
    file.close()
    candidate = null
    await shutdown_fixture(body)
""".replace("@DECL@", declaration)
        .replace("@CHANGE@", changes[case])
        .replace("@OUT@", json.dumps(str(out / "result.json").replace("\\", "/")))
        + PROPERTY_SNAPSHOT
    )
    return script


def _managed_run(out: Path, script: Path) -> str:
    # Expected managed declaration failures still require the real production drain and exit 0.
    command = [os.environ["GODOT_BIN"], "--headless", "--path", str(ROOT), "--script", str(script)]
    env = os.environ.copy()
    env.update(
        {
            "APPDATA": str(out / "user/roaming"),
            "LOCALAPPDATA": str(out / "user/local"),
            "XDG_DATA_HOME": str(out / "user/data"),
            "XDG_CONFIG_HOME": str(out / "user/config"),
        }
    )
    run = subprocess.run(command, env=env, capture_output=True, timeout=60)
    log = (run.stdout + run.stderr).decode(errors="replace")
    (out / "native.log").write_text(log)
    (out / "command.json").write_text(
        json.dumps({"argv": command, "returncode": run.returncode}) + "\n"
    )
    assert run.returncode == 0 and "CANNONBALL_SHUTDOWN_OK" in log, log
    assert "v4.7.1.stable.mono.official.a13da4feb" in log, log
    for bad in (
        "ObjectDB instances leaked",
        "resources still in use",
        "RID allocations",
        "FATAL",
        "Parse Error",
    ):
        assert bad not in log, log
    return log


@NATIVE
@pytest.mark.parametrize("case", WRAPPER_CASES)
def test_specular_managed_wrapper_declaration(tmp_path: Path, case: str) -> None:
    """Needs a build of current VehicleVisualRig.cs; the test never rebuilds the DLL."""
    out = _out(tmp_path, "wrapper-" + case)
    log = _managed_run(out, _wrapper_script(out, case))
    result = json.loads((out / "result.json").read_text())
    valid = case in {"absent", "zero", "authored", "one"}
    assert result["complete"] == valid, (result, log)
    if valid:
        assert "ERROR:" not in log, log
        expected = (
            result["before"]
            if case == "absent"
            else 0.5 * math.sqrt({"zero": 0, "authored": FACTOR, "one": 1}[case])
        )
        expected_float32 = struct.unpack("<f", struct.pack("<f", expected))[0]
        assert result["after"] == expected_float32
    else:
        assert "InvalidOperationException" in log and "specular" in log.lower(), log
        assert result["after"] == result["before"]
    assert {
        key: value
        for key, value in result["before_properties"].items()
        if key != "metallic_specular"
    } == {
        key: value
        for key, value in result["after_properties"].items()
        if key != "metallic_specular"
    }


def _vehicle_script(out: Path, vehicle: str) -> Path:
    script = out / "vehicle.gd"
    script.write_text(
        """extends SceneTree
func _initialize() -> void:
    call_deferred("run_fixture")
func run_fixture() -> void:
    var mode: String = @MODE@
    var body: Node = load("res://game/Vehicle/CannonballVehicle.cs").new()
    body.set("RigSetup", load("res://game/Vehicle/Setups/EnduranceSedan.tres")
        if mode == "endurance-sedan" else load("res://game/Vehicle/Setups/HeroGt.tres"))
    body.set("ForceGrayboxVisual", mode == "graybox")
    body.set("freeze", true)
    body.process_mode = Node.PROCESS_MODE_DISABLED
    root.add_child(body)
    var rows: Array = []
    var stack: Array[Node] = [body]
    while not stack.is_empty():
        var node: Node = stack.pop_back()
        for child in node.get_children(): stack.append(child)
        if not node is MeshInstance3D or node.mesh == null: continue
        for surface in node.mesh.get_surface_count():
            var material: Material = node.get_active_material(surface)
            var source: Material = node.mesh.surface_get_material(surface)
            rows.append({"path": str(body.get_path_to(node)), "surface": surface,
                "material": native_properties(material),
                "source_name": source.resource_name if source != null else "",
                "override": node.material_override != null,
                "declared": material != null and material.has_meta("cannonball_specular_response")})
    var rig: Node = body.get("VisualRig")
    var result := {"vehicle": mode, "rows": rows, "graybox": body.get("UsesGrayboxVisual"),
        "presentation": rig != null and rig.get_node_or_null("EnduranceSedanPresentation") != null}
    var file := FileAccess.open(@OUT@, FileAccess.WRITE)
    file.store_string(JSON.stringify(result, "  ", true, true) + "\\n")
    file.close()
    await shutdown_fixture(body)
""".replace("@MODE@", json.dumps(vehicle)).replace(
            "@OUT@", json.dumps(str(out / "result.json").replace("\\", "/"))
        )
        + PROPERTY_SNAPSHOT
    )
    return script


@NATIVE
@pytest.mark.parametrize("vehicle", ["endurance-sedan", "hero-gt", "graybox"])
def test_specular_existing_vehicle_inventory(tmp_path: Path, vehicle: str) -> None:
    out = _out(tmp_path, "vehicle-" + vehicle)
    log = _managed_run(out, _vehicle_script(out, vehicle))
    assert "ERROR:" not in log, log
    result = json.loads((out / "result.json").read_text())
    assert result["rows"] and result["vehicle"] == vehicle
    if vehicle == "graybox":
        assert result["graybox"] and len(result["rows"]) == 1
        assert result["rows"][0]["material"]["metallic_specular"] == 0.5
    if vehicle != "endurance-sedan":
        assert all(not row["declared"] for row in result["rows"])
        if vehicle == "hero-gt":
            assert any(
                row["material"]["native_class"] == "ShaderMaterial" for row in result["rows"]
            )
        return
    assert result["presentation"]
    static = [
        row
        for row in result["rows"]
        if row["source_name"] == "Material_Screen" and "/Chassis/" in row["path"]
    ]
    dynamic = [
        row
        for row in result["rows"]
        if row["source_name"] == "Material_Screen" and "/Instrument_Cluster/" in row["path"]
    ]
    assert len(static) == len(dynamic) == 3
    glb = (ROOT / "data/assets/vehicles/derived/endurance-sedan.glb").read_bytes()
    document = json.loads(glb[20 : 20 + struct.unpack_from("<I", glb, 12)[0]])
    screen = [
        material for material in document["materials"] if material["name"] == "Material_Screen"
    ]
    assert len(screen) == 1
    extension = screen[0].get("extensions", {}).get("KHR_materials_specular")
    for row in static:
        assert not row["override"] and row["declared"] == (extension is not None)
        target = 0.5 if extension is None else 0.5 * math.sqrt(extension.get("specularFactor", 1))
        assert (
            row["material"]["metallic_specular"]
            == struct.unpack("<f", struct.pack("<f", target))[0]
        )
    for row in dynamic:
        assert row["override"] and not row["declared"]
        assert row["material"]["shading_mode"] == 0
        assert row["material"]["albedo_texture"]["class"] == "ViewportTexture"
