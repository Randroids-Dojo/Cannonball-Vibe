from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from cannonball_playgodot import PlayGodotProcess

from .shutdown_support import assert_clean_owned_shutdown

ROOT = Path(__file__).resolve().parents[3]
SHADER = "game/Vehicle/mirror_display.gdshader"

# A single rendered process batches real binding corruptions, two presentations,
# free/recreate and paired original-mesh pixels. The production scenario retains
# the separate moving 3D target, camera/door-follow and mirror scheduling checks.
PROBE = r"""extends Node
const NAMES = ["Left", "Right", "Rear"]
const SIZES = [Vector2i(256, 128), Vector2i(256, 128), Vector2i(384, 128)]
const PAIRS = [[Color(.08, .18, .65), Color(.86, .62, .22)],
	[Color(.16, .74, .28), Color(.74, .22, .85)],
	[Color(.72, .19, .14), Color(.12, .65, .84)]]
const OUTPUT = @OUTPUT@
const START = @START@
var report := {"schema": "mirror-material-native39.v1", "status": "waiting",
	"errors": [], "bindings": [], "negatives": [], "pixels": [], "lifecycle": [], "sources": []}

func _ready() -> void:
	set_meta("automation_id", "mirror-material.root")
	_write()
	_run.call_deferred()

func _write() -> void:
	set_meta("automation_state", {"status": report.status,
		"errors": report.errors.size(), "pixels": report.pixels.size()})
	var file := FileAccess.open(OUTPUT.path_join("native.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t", true, true) + "\n")
	file.close()

func _check(ok: bool, message: String) -> void:
	if not ok: report.errors.append(message)

func _draws(count: int) -> void:
	for i in range(count): await RenderingServer.frame_post_draw

func _rig(body: Node) -> Node:
	return body.get("VisualRig")

func _presenter(body: Node) -> Node:
	return _rig(body).get("Presentation")

func _view(body: Node, name: String) -> SubViewport:
	return _presenter(body).get_node("MirrorViewport_" + name)

func _meshes(body: Node, name: String) -> Array[Node]:
	var anchor: Node = _rig(body).call("ResolveAnchor", "Mirror_" + name)
	return anchor.find_children("*", "MeshInstance3D", true, false)

func _rid(resource: Resource) -> String:
	return str(resource.get_rid().get_id()) if resource != null else "missing"

func _mesh_hash(mesh: Mesh) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	for surface in range(mesh.get_surface_count()):
		hash.update(var_to_bytes(mesh.surface_get_arrays(surface)))
	return hash.finish().hex_encode()

func _snapshot(body: Node) -> Dictionary:
	var result := {"body": str(body.get_instance_id()),
		"world": str(body.get_world_3d().get_instance_id()), "channels": []}
	for index in range(3):
		var name: String = NAMES[index]
		var viewport := _view(body, name)
		var camera := viewport.get_camera_3d()
		var channel := {"name": name, "texture": _rid(viewport.get_texture()),
			"viewport": str(viewport.get_instance_id()),
			"viewport_rid": str(viewport.get_viewport_rid().get_id()),
			"world": str(viewport.find_world_3d().get_instance_id()),
			"size": [viewport.size.x, viewport.size.y], "camera": str(camera.get_instance_id()),
			"fov": camera.fov, "near": camera.near, "far": camera.far,
			"mask": camera.cull_mask, "members": []}
		for node in _meshes(body, name):
			var mesh := node as MeshInstance3D
			var material := mesh.material_override as ShaderMaterial
			var selector: Variant = (
				mesh.get_instance_shader_parameter("mirror_index") if material != null else null)
			var member := {"path": str(_rig(body).get_path_to(mesh)),
				"material": _rid(mesh.material_override),
				"material_instance": (
					str(material.get_instance_id()) if material != null else "missing"),
				"selector_type": typeof(selector), "selector": selector, "layers": mesh.layers,
				"mesh": _mesh_hash(mesh.mesh), "shader": "", "samplers": {}}
			if material != null:
				member.shader = material.shader.resource_path
				for other in NAMES:
					member.samplers[other] = _rid(
						material.get_shader_parameter("mirror_" + other.to_lower()))
			channel.members.append(member)
		result.channels.append(channel)
	return result

func _binding_errors(packet: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	var materials: Dictionary = {}
	var textures: Dictionary = {}
	for index in range(3):
		var channel: Dictionary = packet.channels[index]
		textures[channel.texture] = true
		if channel.name != NAMES[index] or channel.size != [SIZES[index].x, SIZES[index].y]:
			errors.append("channel size/name")
		if channel.world != packet.world: errors.append("different world")
		var expected_fov: float = 30.0 if channel.name == "Rear" else 55.0
		if (channel.fov != expected_fov or absf(channel.near - .035) > 1e-8
			or channel.far != 180.0 or channel.mask & (1 << 18)):
			errors.append("camera contract")
		var lods: Dictionary = {}
		if channel.members.is_empty(): errors.append("empty mirror")
		for member in channel.members:
			materials[member.material] = true
			for lod in range(3):
				if member.path.get_file().begins_with("LOD%d_" % lod): lods[lod] = true
			if member.shader != "res://game/Vehicle/mirror_display.gdshader":
				errors.append("shader")
			if member.selector_type != TYPE_INT or member.selector != index:
				errors.append("selector")
			if member.layers != 1 << 18: errors.append("mirror layer")
			for other in range(3):
				if member.samplers.get(NAMES[other]) != packet.channels[other].texture:
					errors.append("foreign or missing sampler")
		if lods.size() != 3: errors.append("missing LOD descendant")
	if materials.size() != 1 or materials.has("missing"): errors.append("shared material")
	if textures.size() != 3 or textures.has("missing"): errors.append("independent textures")
	return errors

func _positive(body: Node, label: String) -> Dictionary:
	var packet := _snapshot(body)
	var errors := _binding_errors(packet)
	_check(errors.is_empty(), label + ": " + str(errors))
	report.bindings.append({"label": label, "packet": packet, "errors": errors})
	return packet

func _negative(body: Node, label: String) -> void:
	var packet := _snapshot(body)
	var errors := _binding_errors(packet)
	_check(not errors.is_empty(), "negative accepted: " + label)
	report.negatives.append({"label": label, "packet": packet, "errors": errors})

func _outside(body: Node) -> String:
	# Same-call full native arrays and stored material properties of all nonmirror
	# meshes. No copied near-mesh geometry or material-only count proxy.
	var mirrors: Array[Node] = []
	for name in NAMES: mirrors.append_array(_meshes(body, name))
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	var seen: Dictionary = {}
	for node in _rig(body).find_children("*", "MeshInstance3D", true, false):
		if node in mirrors: continue
		var mesh := node as MeshInstance3D
		if mesh.mesh == null: continue
		hash.update(var_to_bytes([
			str(_rig(body).get_path_to(mesh)), mesh.transform, _mesh_hash(mesh.mesh)]))
		for surface in range(mesh.mesh.get_surface_count()):
			# An active override can hide a shared source material that another rig
			# still mutates during creation. Both resource layers must stay exact.
			for binding in ["active", "source"]:
				var material: Material = (mesh.get_active_material(surface) if binding == "active"
					else mesh.mesh.surface_get_material(surface))
				hash.update(var_to_bytes([binding, _rid(material)]))
				if material == null or seen.has(material.get_instance_id()): continue
				seen[material.get_instance_id()] = true
				for field in material.get_property_list():
					if int(field.usage) & PROPERTY_USAGE_STORAGE:
						var value: Variant = material.get(field.name)
						if value is Resource:
							value = [value.get_class(), str(value.get_instance_id()),
								value.resource_path]
						hash.update(var_to_bytes([str(field.name), value]))
	return hash.finish().hex_encode()

func _copy_body(original: Node) -> SubViewport:
	var world := SubViewport.new()
	world.own_world_3d = true
	world.size = Vector2i(32, 32)
	world.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(world)
	var body := RigidBody3D.new()
	body.set_script(load("res://game/Vehicle/CannonballVehicle.cs"))
	body.set("RigSetup", original.get("RigSetup"))
	body.freeze = true
	body.process_mode = Node.PROCESS_MODE_DISABLED
	world.add_child(body)
	return world

func _free_copy(world: SubViewport, packet: Dictionary) -> void:
	var ids := [int(packet.body)]
	var resources: Dictionary = {}
	for channel in packet.channels:
		ids.append(int(channel.viewport))
		ids.append(int(channel.camera))
		for member in channel.members: resources[member.material_instance] = true
	world.queue_free()
	await _draws(5)
	var remaining: Array = []
	for id in ids:
		if is_instance_id_valid(id): remaining.append(str(id))
	for id in resources:
		if is_instance_id_valid(int(id)): remaining.append(id)
	_check(remaining.is_empty(), "removed presentation retained nodes/material: " + str(remaining))
	report.lifecycle.append({"body": packet.body, "removed_node_ids": ids,
		"removed_material_ids": resources.keys(), "remaining": remaining})

func _corners(meshes: Array[Node]) -> Array[Vector3]:
	var sums: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO, Vector3.ZERO, Vector3.ZERO]
	var counts := [0, 0, 0, 0]
	for node in meshes:
		var mesh := node as MeshInstance3D
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface)
			for i in range(arrays[Mesh.ARRAY_VERTEX].size()):
				var uv: Vector2 = arrays[Mesh.ARRAY_TEX_UV][i]
				var u := 0 if absf(uv.x) < .0001 else (1 if absf(uv.x - 1) < .0001 else -1)
				var v := 0 if absf(uv.y) < .0001 else (1 if absf(uv.y - 1) < .0001 else -1)
				if u >= 0 and v >= 0:
					sums[u + 2 * v] += mesh.global_transform * arrays[Mesh.ARRAY_VERTEX][i]
					counts[u + 2 * v] += 1
	for i in range(4):
		_check(counts[i] > 0, "actual UV corner missing")
		if counts[i] > 0: sums[i] /= counts[i]
	return sums

func _render_pair(body: Node, index: int, lod: int, phase: int, wrong_flip: bool = false) -> void:
	var name: String = NAMES[index]
	var source_image := _view(body, name).get_texture().get_image()
	var source_bytes := source_image.get_data()
	var members: Array[Node] = []
	for node in _meshes(body, name):
		if str(node.name).begins_with("LOD%d_" % lod): members.append(node)
	_check(not members.is_empty(), "render actual LOD missing")
	if members.is_empty(): return
	var corners := _corners(members)
	var right := corners[1] - corners[0]
	var down := corners[2] - corners[0]
	var center := (corners[0] + corners[1] + corners[2] + corners[3]) * .25
	var viewport := SubViewport.new()
	viewport.size = Vector2i(512, 256)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(viewport)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color.BLACK
	viewport.add_child(environment)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = maxf(down.length() * 1.4, right.length() * .7)
	camera.near = .001
	viewport.add_child(camera)
	camera.position = center + down.cross(right).normalized()
	camera.look_at(center, -down.normalized())
	camera.make_current()
	var copies: Array[MeshInstance3D] = []
	var candidate: ShaderMaterial = members[0].material_override
	if wrong_flip:
		candidate = candidate.duplicate()
		var shader := Shader.new()
		shader.code = candidate.shader.code.replace("1.0 - UV.x", "UV.x")
		candidate.shader = shader
	for node in members:
		var copy := MeshInstance3D.new()
		copy.mesh = node.mesh
		copy.transform = node.global_transform
		copy.material_override = candidate
		copy.set_instance_shader_parameter("mirror_index", index)
		viewport.add_child(copy)
		copies.append(copy)
	await _draws(3)
	var after := viewport.get_texture().get_image()
	var baseline := StandardMaterial3D.new()
	baseline.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	baseline.albedo_color = Color.WHITE
	baseline.albedo_texture = _view(body, name).get_texture()
	baseline.roughness = 1
	baseline.uv1_scale = Vector3(-1, 1, 1)
	baseline.uv1_offset = Vector3(1, 0, 0)
	for copy in copies: copy.material_override = baseline
	await _draws(3)
	var before := viewport.get_texture().get_image()
	var prefix := "%s-lod%d-phase%d%s" % [name, lod, phase, "-wrong-flip" if wrong_flip else ""]
	_check(before.save_png(OUTPUT.path_join(prefix + "-standard.png")) == OK, "save baseline")
	_check(after.save_png(OUTPUT.path_join(prefix + "-shared.png")) == OK, "save candidate")
	var maximum := 0.0
	var changed := 0
	var foreground := 0
	for y in range(before.get_height()):
		for x in range(before.get_width()):
			var a := before.get_pixel(x, y)
			var b := after.get_pixel(x, y)
			var error := maxf(absf(a.r - b.r), maxf(absf(a.g - b.g), absf(a.b - b.b)))
			maximum = maxf(maximum, error)
			if error > 0: changed += 1
			if maxf(a.r, maxf(a.g, a.b)) > .1: foreground += 1
	var samples: Array = []
	for half in range(2):
		var point := corners[0] + right * (.25 if half == 0 else .75) + down * .5
		var pixel := Vector2i(camera.unproject_position(point))
		var actual := after.get_pixelv(pixel)
		var source_x := int(source_image.get_width() * (.75 if half == 0 else .25))
		var expected := source_image.get_pixel(source_x, source_image.get_height() / 2)
		var error := maxf(absf(actual.r - expected.r),
			maxf(absf(actual.g - expected.g), absf(actual.b - expected.b)))
		if not wrong_flip and phase >= 0:
			_check(error <= .025, "native frozen feed/flip actual surface: " + prefix)
		samples.append({"pixel": [pixel.x, pixel.y], "actual": [actual.r, actual.g, actual.b],
			"expected": [expected.r, expected.g, expected.b], "error": error})
	_check(foreground > 2000, "nonvacuous actual visible surface coverage")
	_check(maximum > .5 if wrong_flip else maximum <= 2.0 / 255.0,
		"paired pixel comparison: " + prefix)
	var same_source := source_bytes == _view(body, name).get_texture().get_image().get_data()
	_check(same_source, "viewport image changed during paired material comparison")
	report.pixels.append({"name": name, "lod": lod, "phase": phase, "negative": wrong_flip,
		"source_pixels_unchanged": same_source, "actual_3d_feed": phase < 0,
		"maximum_rgb_difference": maximum, "changed_pixels": changed,
		"foreground_pixels": foreground, "samples": samples,
		"standard": prefix + "-standard.png", "shared": prefix + "-shared.png",
		"source_meshes": members.map(func(node):
			return {"name": str(node.name), "sha256": _mesh_hash(node.mesh)})})
	viewport.queue_free()
	await _draws(2)
	_write()

func _run() -> void:
	while not FileAccess.file_exists(START): await get_tree().process_frame
	var body: Node = get_parent().get_node("Main/CannonballVehicle")
	var original_mode: int = body.process_mode
	var original_freeze: bool = body.freeze
	body.freeze = true
	body.process_mode = Node.PROCESS_MODE_DISABLED
	await _draws(3)
	report.status = "running"
	report.engine = Engine.get_version_info()
	report.renderer = RenderingServer.get_current_rendering_method()
	report.shader_sha256 = FileAccess.get_file_as_string("res://game/Vehicle/mirror_display.gdshader").sha256_text()
	var presentation := _presenter(body)
	var original_presentation_mode: int = presentation.process_mode
	var original_camera: String = body.get("CurrentCameraMode")
	var original_mirrors: bool = presentation.get("MirrorsEnabled")
	var original_auto_lod: bool = presentation.get("AutoLodEnabled")
	var original_lod: int = _rig(body).get("ActiveLod")
	presentation.set("AutoLodEnabled", false)
	presentation.set("MirrorsEnabled", true)
	body.call("SetCameraMode", true)
	presentation.process_mode = Node.PROCESS_MODE_ALWAYS
	await _draws(12)
	presentation.process_mode = Node.PROCESS_MODE_DISABLED
	for name in NAMES: _view(body, name).render_target_update_mode = SubViewport.UPDATE_DISABLED
	await _draws(2)
	for index in range(3):
		var source := _view(body, NAMES[index]).get_texture().get_image()
		_check(source.save_png(OUTPUT.path_join("original-3d-%s.png" % NAMES[index])) == OK,
			"save original actual 3D mirror feed")
		await _render_pair(body, index, 0, -1)
	var first := _positive(body, "primary-before")
	var outside := _outside(body)
	var copy_world := _copy_body(body)
	var second: Node = copy_world.get_child(0)
	second.call("SetHeadlights", false)
	_check(outside == _outside(body), "dousing second vehicle mutated primary source materials")
	var second_packet := _positive(second, "simultaneous-second")
	_check(first.world != second_packet.world, "simultaneous private World3D")
	_check(first.channels[0].members[0].material != second_packet.channels[0].members[0].material,
		"cross-vehicle material sharing")
	var mesh: MeshInstance3D = _meshes(body, "Left")[0]
	var material := mesh.material_override as ShaderMaterial
	var left := _view(body, "Left").get_texture()
	material.set_shader_parameter("mirror_left", _view(body, "Right").get_texture())
	_negative(body, "swapped-texture")
	material.set_shader_parameter("mirror_left", null)
	_negative(body, "missing-texture")
	material.set_shader_parameter("mirror_left", _view(second, "Left").get_texture())
	_negative(body, "cross-vehicle-feed")
	material.set_shader_parameter("mirror_left", left)
	for change in [{"name": "duplicate-selector", "value": 1},
		{"name": "out-of-range-selector", "value": 3}, {"name": "missing-selector", "value": null}]:
		mesh.set_instance_shader_parameter("mirror_index", change.value)
		_negative(body, change.name)
	mesh.set_instance_shader_parameter("mirror_index", 0)
	var lower: MeshInstance3D
	for node in _meshes(body, "Left"):
		if str(node.name).begins_with("LOD2_"): lower = node
	_check(lower != null, "actual lower member required for omission control")
	if lower != null:
		lower.material_override = null
		_negative(body, "forgotten-lod-descendant")
		lower.material_override = material
	await _free_copy(copy_world, second_packet)
	copy_world = _copy_body(body)
	second = copy_world.get_child(0)
	second.call("SetHeadlights", false)
	_check(outside == _outside(body), "dousing recreated vehicle mutated primary source materials")
	var third := _positive(second, "recreated-second")
	_check(third.channels[0].texture != second_packet.channels[0].texture,
		"recreated viewport reused stale RID")
	var stale := _snapshot(second)
	stale.channels[0].members[0].samplers.Left = second_packet.channels[0].texture
	var stale_errors := _binding_errors(stale)
	_check(not stale_errors.is_empty(), "removed-vehicle sampler accepted")
	report.negatives.append({"label": "removed-vehicle-sampler-observation", "packet": stale,
		"errors": stale_errors, "scope": "reader corruption uses the actually removed prior RID;"
		+ " no dead native resource is dereferenced"})
	await _free_copy(copy_world, third)
	var rects: Array[ColorRect] = []
	var modes: Array[int] = []
	for index in range(3):
		var viewport := _view(body, NAMES[index])
		modes.append(viewport.render_target_update_mode)
		for half in range(2):
			var rect := ColorRect.new()
			rect.position = Vector2(viewport.size.x * half * .5, 0)
			rect.size = Vector2(viewport.size.x * .5, viewport.size.y)
			viewport.add_child(rect)
			rects.append(rect)
	for phase in range(2):
		for index in range(3):
			for half in range(2):
				rects[index * 2 + half].color = PAIRS[index][half]
				rects[index * 2 + half].position.x = SIZES[index].x * ((half + phase) % 2) * .5
			_view(body, NAMES[index]).render_target_update_mode = SubViewport.UPDATE_ALWAYS
		await _draws(3)
		for index in range(3):
			_view(body, NAMES[index]).render_target_update_mode = SubViewport.UPDATE_DISABLED
			var source := _view(body, NAMES[index]).get_texture().get_image()
			_check(source.save_png(OUTPUT.path_join(
				"source-%s-phase%d.png" % [NAMES[index], phase])) == OK, "save frozen source feed")
			var samples: Array = []
			for half in range(2):
				var actual := source.get_pixel(
					int(source.get_width() * (.25 if half == 0 else .75)), source.get_height() / 2)
				var expected: Color = PAIRS[index][(half + phase) % 2]
				var error := maxf(absf(actual.r - expected.r),
					maxf(absf(actual.g - expected.g), absf(actual.b - expected.b)))
				_check(error <= .025, "independent authored midtone source color")
				samples.append({"actual": [actual.r, actual.g, actual.b],
					"expected": [expected.r, expected.g, expected.b], "error": error})
			report.sources.append({"name": NAMES[index], "phase": phase, "samples": samples,
				"width": source.get_width(), "height": source.get_height(),
				"target_rect_x": [rects[index * 2].position.x, rects[index * 2 + 1].position.x]})
			for lod in range(3 if phase == 0 else 1): await _render_pair(body, index, lod, phase)
		if phase == 0: await _render_pair(body, 0, 0, phase, true)
	for rect in rects: rect.queue_free()
	await _draws(2)
	for index in range(3): _view(body, NAMES[index]).render_target_update_mode = modes[index]
	var last := _positive(body, "primary-after")
	report.outside_before = outside
	report.outside_after = _outside(body)
	_check(first == last, "primary full mirror inventory changed after isolation/pixels")
	_check(report.outside_before == report.outside_after, "nonmirror fields/materials/rig changed")
	body.call("SetCameraMode", original_camera == "cockpit")
	presentation.set("MirrorsEnabled", original_mirrors)
	presentation.set("AutoLodEnabled", original_auto_lod)
	presentation.process_mode = original_presentation_mode
	_rig(body).call("SetLod", original_lod)
	body.freeze = original_freeze
	body.process_mode = original_mode
	report.status = "completed" if report.errors.is_empty() else "failed"
	_write()
"""


def _files(*consumed: Path) -> list[dict]:
    roots = ("game", "assets/vehicles", "addons/playgodot", ".godot/mono/temp/bin/Debug")
    paths = [ROOT / "project.godot", Path(os.environ["GODOT_BIN"]), Path(__file__), *consumed]
    for relative in roots:
        paths.extend(p for p in (ROOT / relative).rglob("*") if p.is_file())
    return [
        {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(set(paths))
    ]


@pytest.mark.asyncio
@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="Requires built official Godot project")
async def test_shared_mirror_material_pixels_isolation_and_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = (
        Path(os.environ.get("PLAYGODOT_ARTIFACT_DIR", str(tmp_path))).resolve() / "mirror-material"
    )
    out.mkdir(parents=True, exist_ok=False)
    generated = (
        out / "fixture"
        if out.is_relative_to(ROOT)
        else ROOT / "reports/playgodot/mirror-fixtures" / uuid.uuid4().hex
    )
    generated.mkdir(parents=True)
    script = generated / "probe.gd"
    start = out / "start"
    script.write_text(
        PROBE.replace("@OUTPUT@", json.dumps(out.as_posix())).replace(
            "@START@", json.dumps(start.as_posix())
        ),
        newline="\n",
    )
    bootstrap = (ROOT / "addons/playgodot/bootstrap.tscn").read_text()
    assert (
        "load_steps=4" in bootstrap and 'application_quit_owner = NodePath("../Main")' in bootstrap
    )
    uri = "res://" + script.relative_to(ROOT).as_posix()
    resource = f'[ext_resource type="Script" path="{uri}" id="4_probe"]\n'
    bootstrap = bootstrap.replace("load_steps=4", "load_steps=5").replace(
        '[node name="PlayGodotBootstrap"', resource + '\n[node name="PlayGodotBootstrap"', 1
    )
    assert 'id="4_probe"' in bootstrap
    bootstrap += (
        '\n[node name="MirrorProbe" type="Node" parent="."]\nscript = ExtResource("4_probe")\n'
    )
    scene = generated / "fixture.tscn"
    scene.write_text(bootstrap, newline="\n")
    actual_spawn = asyncio.create_subprocess_exec
    commands = []

    async def spawn(*args, **kwargs):
        command = list(args)
        assert command.count("addons/playgodot/bootstrap.tscn") == 1
        command[command.index("addons/playgodot/bootstrap.tscn")] = scene.relative_to(
            ROOT
        ).as_posix()
        commands.append(command)
        return await actual_spawn(*command, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    base = ROOT / ".tools/scenarios/official-corridor"
    route = base / json.loads((base / "current-package.json").read_text())["root_relative_path"]
    renderer = os.environ.get("PLAYGODOT_MIRROR_RENDERER", "gl_compatibility")
    process = PlayGodotProcess(
        ROOT,
        route,
        vehicle="endurance-sedan",
        startup_timeout=60,
        request_timeout=30,
        capabilities=("read",),
        rendering_method=renderer,
        isolate_user_data=True,
        log_path=out / "godot.log",
        transcript=out / "wire.jsonl",
    )
    before = _files(script, scene)
    (out / "inputs-before.json").write_text(json.dumps(before, indent=2) + "\n")
    try:
        async with process as client:
            first_draw = await process.wait_for_vehicle_render(
                "endurance-sedan", after_generation=0, timeout=60
            )
            (out / "first-draw.json").write_text(json.dumps(first_draw, indent=2) + "\n")
            start.write_text("host released after actual secured vehicle draw\n")
            deadline = asyncio.get_running_loop().time() + 120
            while True:
                state = (await client.describe("mirror-material.root"))["test_state"]
                if state["status"] in {"completed", "failed"}:
                    break
                assert asyncio.get_running_loop().time() < deadline, state
                await asyncio.sleep(0.1)
            result = json.loads((out / "native.json").read_text())
            assert result["status"] == "completed" and result["errors"] == [], result
            assert result["renderer"] == renderer
            assert (
                result["shader_sha256"] == hashlib.sha256((ROOT / SHADER).read_bytes()).hexdigest()
            )
            assert len(result["pixels"]) == 16 and sum(r["negative"] for r in result["pixels"]) == 1
            assert sum(row["actual_3d_feed"] for row in result["pixels"]) == 3
            assert all(row["source_pixels_unchanged"] for row in result["pixels"])
            assert len(result["sources"]) == 6
            assert {r["label"] for r in result["negatives"]} == {
                "swapped-texture",
                "missing-texture",
                "cross-vehicle-feed",
                "duplicate-selector",
                "out-of-range-selector",
                "missing-selector",
                "forgotten-lod-descendant",
                "removed-vehicle-sampler-observation",
            }
            assert all(row["errors"] for row in result["negatives"])
            assert len(result["lifecycle"]) == 2 and all(
                not row["remaining"] for row in result["lifecycle"]
            )
            assert len(result["bindings"]) == 4 and all(
                not row["errors"] for row in result["bindings"]
            )
            assert result["outside_before"] == result["outside_after"]
    finally:
        after = _files(script, scene)
        (out / "inputs-after.json").write_text(json.dumps(after, indent=2) + "\n")
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        (out / "teardown.json").write_text(json.dumps(process.teardown_result, indent=2) + "\n")
    assert before == after
    assert_clean_owned_shutdown(process.teardown_result)
