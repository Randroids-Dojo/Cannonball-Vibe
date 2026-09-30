extends SceneTree

var _failed := false
const SPECULAR_EXTENSION := "KHR_materials_specular"
const SPECULAR_META := "cannonball_specular_response"


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var vehicle := "hero-gt"
	if args.size() == 4 and args[2] == "--vehicle":
		vehicle = args[3]
	elif args.size() != 2:
		push_error("Usage: -- INPUT_SCENE OUTPUT_SCENE [--vehicle hero-gt|endurance-sedan]")
		quit(2)
		return
	if vehicle not in ["hero-gt", "endurance-sedan"]:
		push_error("Unknown vehicle normalization contract: " + vehicle)
		quit(2)
		return
	var specular_plan := _screen_specular_plan(args[0]) if vehicle == "endurance-sedan" else {}
	if _failed:
		quit(1)
		return
	var source := load(args[0]) as PackedScene
	if source == null:
		push_error("Could not load %s" % args[0])
		quit(1)
		return
	var instance := source.instantiate()
	if vehicle == "endurance-sedan":
		_bind_screen_specular(instance, specular_plan)
		if _failed:
			instance.free()
			quit(1)
			return
	_assign_owner(instance, instance)
	var packed := PackedScene.new()
	var pack_error := packed.pack(instance)
	if pack_error != OK:
		push_error("Could not pack normalized scene: %s" % error_string(pack_error))
		quit(1)
		return
	var save_error := ResourceSaver.save(packed, args[1])
	if save_error != OK:
		push_error("Could not save normalized scene: %s" % error_string(save_error))
		quit(1)
		return
	var text := FileAccess.get_file_as_string(args[1])
	if vehicle == "endurance-sedan" and not specular_plan.occurrences.is_empty():
		text = _preserve_screen_specular_precision(text, specular_plan)
		if _failed:
			instance.free()
			quit(1)
			return
	var unique_ids := RegEx.new()
	var regex_error := unique_ids.compile(" unique_id=\\d+")
	if regex_error != OK:
		push_error("Could not compile unique-ID normalizer")
		quit(1)
		return
	text = unique_ids.sub(text, "", true)
	if vehicle == "hero-gt":
		text = _redirect_extracted_textures(text)
	else:
		# Original sedan textures stay beside the vehicle. Import-cache UIDs
		# belong to this staging project, so detach portable paths only.
		text = _strip_texture_uids(text)
	text = _detach_textures(text, args[1].get_basename() + ".textures.json", vehicle)
	if _failed:
		instance.free()
		quit(1)
		return
	var normalized := FileAccess.open(args[1], FileAccess.WRITE)
	if normalized == null:
		push_error("Could not rewrite normalized scene")
		quit(1)
		return
	normalized.store_string(text)
	normalized.close()
	instance.free()
	print("CANNONBALL_PACKED_GLTF_OK output=%s" % args[1])
	quit(0)


func _strip_texture_uids(text: String) -> String:
	var pattern := RegEx.new()
	if pattern.compile("(?m)^(\\[ext_resource type=\"Texture2D\") uid=\"uid://[^\"]*\"") != OK:
		push_error("Could not compile portable texture UID normalizer")
		_failed = true
		return text
	return pattern.sub(text, "$1", true)


# The importer extracts the GLB's embedded textures next to the scene it
# imported from. Those files are Blender-composed bytes of sourced CC0 maps
# (roughness and metalness packed, colour with opacity), so they live with the
# other sourced material under assets/vehicles/sourced/, which the release
# presets exclude until the rights records are approved (Q-023, Q-037). The
# stage's import UIDs are dropped so the repository resolves them by path.
const EXTRACTED_PREFIX := "res://assets/vehicles/hero-gt/hero-gt_"
const SOURCED_PREFIX := "res://assets/vehicles/sourced/hero-gt/hero-gt_"


func _redirect_extracted_textures(text: String) -> String:
	var uid_pattern := RegEx.new()
	if uid_pattern.compile("\\[ext_resource type=\"Texture2D\" uid=\"uid://[^\"]*\" path=\"" + EXTRACTED_PREFIX.replace("/", "\\/")) != OK:
		push_error("Could not compile texture redirect")
		return text
	text = uid_pattern.sub(text, "[ext_resource type=\"Texture2D\" path=\"" + SOURCED_PREFIX, true)
	return text.replace(EXTRACTED_PREFIX, SOURCED_PREFIX)


# A scene that names a missing ext_resource fails to load outright, so the
# release build, which excludes the sourced folder, would lose the whole
# vehicle. The texture references leave the scene and go to a sidecar next to
# it; VehicleVisualRig binds each one that exists at runtime, and the
# packaged game draws the untextured materials until the rights records clear.
func _detach_textures(text: String, sidecar_path: String, vehicle: String) -> String:
	var ext_pattern := RegEx.new()
	if ext_pattern.compile("^\\[ext_resource type=\"Texture2D\" path=\"([^\"]+)\" id=\"([^\"]+)\"\\]$") != OK:
		push_error("Could not compile texture ext_resource pattern")
		_failed = true
		return text
	var slot_pattern := RegEx.new()
	if slot_pattern.compile("^(\\w+_texture) = ExtResource\\(\"([^\"]+)\"\\)$") != OK:
		push_error("Could not compile texture slot pattern")
		_failed = true
		return text
	var name_pattern := RegEx.new()
	if name_pattern.compile("^resource_name = \"([^\"]+)\"$") != OK:
		push_error("Could not compile resource name pattern")
		_failed = true
		return text
	var paths := {}
	var kept: PackedStringArray = []
	var bindings := {}
	var material := ""
	for line in text.split("\n"):
		var ext := ext_pattern.search(line)
		if ext != null:
			if vehicle == "endurance-sedan" and (not ext.get_string(1).begins_with("res://assets/vehicles/endurance-sedan/") or ext.get_string(1).contains("\\") or ".." in ext.get_string(1).split("/") or not FileAccess.file_exists(ext.get_string(1))):
				push_error("Sedan texture is missing or outside its portable asset directory: " + ext.get_string(1))
				_failed = true
				return text
			paths[ext.get_string(2)] = ext.get_string(1)
			continue
		if line.begins_with("[sub_resource type=\"StandardMaterial3D\""):
			material = ""
		elif line.begins_with("["):
			material = ""
		var named := name_pattern.search(line)
		if named != null:
			material = named.get_string(1)
		var slot := slot_pattern.search(line)
		if slot != null and paths.has(slot.get_string(2)):
			if material.is_empty():
				push_error("Texture slot outside a named material: %s" % line)
				_failed = true
				return text
			if not bindings.has(material):
				bindings[material] = {}
			if bindings[material].has(slot.get_string(1)) and bindings[material][slot.get_string(1)] != paths[slot.get_string(2)]:
				push_error("Named material has conflicting texture bindings: " + material)
				_failed = true
				return text
			bindings[material][slot.get_string(1)] = paths[slot.get_string(2)]
			continue
		kept.append(line)
	var names := bindings.keys()
	names.sort()
	var ordered := {}
	for key in names:
		var slots: Dictionary = bindings[key]
		var slot_names := slots.keys()
		slot_names.sort()
		var ordered_slots := {}
		for slot_name in slot_names:
			ordered_slots[slot_name] = slots[slot_name]
		ordered[key] = ordered_slots
	var sidecar := FileAccess.open(sidecar_path, FileAccess.WRITE)
	if sidecar == null:
		push_error("Could not write texture sidecar %s" % sidecar_path)
		_failed = true
		return text
	sidecar.store_string(JSON.stringify({"schema": 1, "materials": ordered}, "  ") + "\n")
	sidecar.close()
	print("CANNONBALL_PACKED_TEXTURES_DETACHED materials=%d textures=%d sidecar=%s" % [ordered.size(), paths.size(), sidecar_path])
	return "\n".join(kept)


func _assign_owner(node: Node, scene_owner: Node) -> void:
	for child in node.get_children():
		child.owner = scene_owner
		_assign_owner(child, scene_owner)


func _specular_error(message: String) -> Dictionary:
	_failed = true
	push_error("SCREEN_SPECULAR: " + message)
	return {}


func _screen_specular_plan(path: String) -> Dictionary:
	# Read only the original JSON; a second GLTFDocument would duplicate imported images.
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.size() < 20 or bytes.decode_u32(0) != 0x46546c67 or bytes.decode_u32(4) != 2 or bytes.decode_u32(8) != bytes.size():
		return _specular_error("Invalid input GLB header")
	var cursor := 12
	var json_text := ""
	while cursor < bytes.size():
		if cursor + 8 > bytes.size():
			return _specular_error("Truncated GLB chunk header")
		var size := int(bytes.decode_u32(cursor))
		var kind := bytes.decode_u32(cursor + 4)
		if size % 4 != 0 or cursor + 8 + size > bytes.size():
			return _specular_error("Invalid GLB chunk bounds")
		if cursor == 12 and kind != 0x4e4f534a:
			return _specular_error("GLB JSON must be the first chunk")
		if kind == 0x4e4f534a:
			if not json_text.is_empty():
				return _specular_error("Duplicate GLB JSON chunk")
			json_text = bytes.slice(cursor + 8, cursor + 8 + size).get_string_from_utf8()
		cursor += 8 + size
	var parser := JSON.new()
	if parser.parse(json_text) != OK or not parser.data is Dictionary:
		return _specular_error("GLB JSON must be an object")
	return _screen_specular_document(parser.data)


func _screen_specular_document(document: Dictionary) -> Dictionary:
	var materials: Variant = document.get("materials", [])
	var required: Variant = document.get("extensionsRequired", [])
	var used: Variant = document.get("extensionsUsed", [])
	if not materials is Array or not required is Array or not used is Array or SPECULAR_EXTENSION in required:
		return _specular_error("Invalid material/extension inventory or required specular extension")
	var source_index := -1
	var factor := 1.0
	var screen_names := 0
	for index in materials.size():
		var material: Variant = materials[index]
		if not material is Dictionary or not material.get("extensions", {}) is Dictionary or not material.get("extras", {}) is Dictionary:
			return _specular_error("Malformed source material")
		var extensions: Dictionary = material.get("extensions", {})
		var extras: Dictionary = material.get("extras", {})
		if material.get("name", "") == "Material_Screen":
			screen_names += 1
		if extras.has(SPECULAR_META) or material.has(SPECULAR_META):
			return _specular_error("Reserved source specular metadata")
		if not extensions.has(SPECULAR_EXTENSION):
			continue
		var scalar: Variant = extensions[SPECULAR_EXTENSION]
		var pbr: Variant = material.get("pbrMetallicRoughness", {})
		if source_index != -1 or not scalar is Dictionary or scalar.size() > 1 or (scalar.size() == 1 and not scalar.has("specularFactor")):
			return _specular_error("Only one scalar-only Screen declaration is supported")
		var value: Variant = scalar.get("specularFactor", 1.0)
		if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(value)) or float(value) < 0.0 or float(value) > 1.0:
			return _specular_error("Specular factor must be a finite number in [0, 1]")
		if material.get("name", "") != "Material_Screen" or extras.get("cv_shader", "") != "standard" or not pbr is Dictionary or typeof(pbr.get("metallicFactor")) not in [TYPE_INT, TYPE_FLOAT] or float(pbr.metallicFactor) != 0.0 or pbr.has("metallicRoughnessTexture"):
			return _specular_error("Specular declaration is outside the standard dielectric Screen domain")
		for unsupported in ["KHR_materials_ior", "KHR_materials_transmission", "KHR_materials_volume", "KHR_materials_pbrSpecularGlossiness", "KHR_materials_unlit"]:
			if extensions.has(unsupported):
				return _specular_error("Unsupported Screen extension combination: " + unsupported)
		source_index = index
		factor = float(value)
	if source_index == -1:
		return {"occurrences": {}}
	if screen_names != 1 or SPECULAR_EXTENSION not in used:
		return _specular_error("Ambiguous Screen name or missing used-extension declaration")
	var nodes: Variant = document.get("nodes")
	var meshes: Variant = document.get("meshes")
	var accessors: Variant = document.get("accessors")
	if not nodes is Array or not meshes is Array or not accessors is Array:
		return _specular_error("Missing source primitive inventory")
	var parents := {}
	for index in nodes.size():
		if not nodes[index] is Dictionary or not nodes[index].get("children", []) is Array:
			return _specular_error("Malformed source node")
		for child in nodes[index].get("children", []):
			if typeof(child) not in [TYPE_INT, TYPE_FLOAT] or float(child) != int(child) or int(child) < 0 or int(child) >= nodes.size() or parents.has(int(child)):
				return _specular_error("Invalid or ambiguous source parent")
			parents[int(child)] = index
	var occurrences := {}
	for index in nodes.size():
		var node: Dictionary = nodes[index]
		if not node.has("mesh"):
			continue
		var mesh_index: Variant = node.mesh
		if typeof(mesh_index) not in [TYPE_INT, TYPE_FLOAT] or float(mesh_index) != int(mesh_index) or int(mesh_index) < 0 or int(mesh_index) >= meshes.size() or not meshes[int(mesh_index)] is Dictionary or not meshes[int(mesh_index)].get("primitives") is Array:
			return _specular_error("Malformed source mesh inventory")
		var primitives: Array = meshes[int(mesh_index)].primitives
		for surface in primitives.size():
			var primitive: Variant = primitives[surface]
			if not primitive is Dictionary:
				return _specular_error("Malformed source primitive")
			if primitive.get("material", -1) != source_index:
				continue
			var names: PackedStringArray = []
			var seen := {}
			var ancestor: int = index
			while ancestor >= 0:
				var name: Variant = nodes[ancestor].get("name")
				if seen.has(ancestor) or not name is String or name.is_empty() or "/" in name or ":" in name or name in [".", ".."]:
					return _specular_error("Invalid source Screen ancestry")
				seen[ancestor] = true
				names.insert(0, name)
				ancestor = int(parents.get(ancestor, -1))
			var attributes: Variant = primitive.get("attributes", {})
			if not attributes is Dictionary:
				return _specular_error("Malformed primitive attributes")
			var accessor: Variant = primitive.get("indices", attributes.get("POSITION", -1))
			if typeof(accessor) not in [TYPE_INT, TYPE_FLOAT] or float(accessor) != int(accessor) or int(accessor) < 0 or int(accessor) >= accessors.size() or not accessors[int(accessor)] is Dictionary:
				return _specular_error("Missing Screen triangle accessor")
			var count: Variant = accessors[int(accessor)].get("count", -1)
			if typeof(count) not in [TYPE_INT, TYPE_FLOAT] or float(count) != int(count) or int(count) <= 0 or int(count) % 3 != 0 or primitive.get("mode", 4) != 4:
				return _specular_error("Screen primitive must contain triangles")
			var path := "/".join(names)
			var key := path + "#" + str(surface)
			if occurrences.has(key):
				return _specular_error("Ambiguous source Screen primitive path")
			occurrences[key] = {"path": path, "surface": surface, "surface_count": primitives.size(), "triangles": int(count) / 3}
	if occurrences.is_empty():
		return _specular_error("Declared Screen has no source primitive")
	return {"occurrences": occurrences, "factor": factor}


func _bind_screen_specular(instance: Node, plan: Dictionary) -> void:
	var remaining: Dictionary = plan.occurrences.duplicate(true)
	var targets := {}
	var stack: Array[Node] = [instance]
	while not stack.is_empty():
		var node := stack.pop_back() as Node
		for child in node.get_children():
			stack.append(child)
		if not node is MeshInstance3D or node.mesh == null:
			continue
		for surface in node.mesh.get_surface_count():
			var material: Material = node.mesh.surface_get_material(surface)
			if material == null:
				continue
			var extras: Variant = material.get_meta("extras", {})
			if material.has_meta(SPECULAR_META) or (extras is Dictionary and extras.has(SPECULAR_META)):
				_specular_error("Imported material already has reserved specular metadata")
				return
			if plan.occurrences.is_empty() or material.resource_name != "Material_Screen":
				continue
			var path := str(instance.get_path_to(node))
			var key := path + "#" + str(surface)
			if not remaining.has(key):
				key = str(instance.name) + "/" + key
			if not remaining.has(key):
				_specular_error("Unexpected imported Screen primitive: " + path)
				return
			var expected: Dictionary = remaining[key]
			var arrays: Array = node.mesh.surface_get_arrays(surface)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var count := vertices.size() if indices.is_empty() else indices.size()
			if not material is StandardMaterial3D or not extras is Dictionary or extras.get("cv_shader", "") != "standard" or material.metallic != 0.0 or material.shading_mode != BaseMaterial3D.SHADING_MODE_PER_PIXEL or material.specular_mode != BaseMaterial3D.SPECULAR_SCHLICK_GGX or node.mesh.get_surface_count() != expected.surface_count or count != expected.triangles * 3 or node.mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES:
				_specular_error("Imported Screen material or primitive differs from source: " + path)
				return
			targets[material.get_instance_id()] = material
			remaining.erase(key)
	if not remaining.is_empty():
		_specular_error("Missing imported Screen primitives: " + str(remaining.keys()))
		return
	# All source/current pairs are validated before any metadata assignment or output write.
	for material in targets.values():
		material.set_meta(SPECULAR_META, {"schema": "khr-specular-f0.v1", "specular_factor": plan.factor})
	plan["bound_materials"] = targets.size()


func _preserve_screen_specular_precision(text: String, plan: Dictionary) -> String:
	# ResourceSaver uses shortened float text for metadata. Preserve the original
	# native-decoded binary64 scalar through its text round-trip; other fields stay exact.
	var lines := text.split("\n")
	var inside := false
	var rewritten := 0
	var standard_resource := false
	var screen_resource := false
	for index in lines.size():
		if lines[index].begins_with("["):
			standard_resource = lines[index].begins_with('[sub_resource type="StandardMaterial3D" ')
			screen_resource = false
		elif standard_resource and lines[index].begins_with("resource_name = "):
			screen_resource = lines[index] == 'resource_name = "Material_Screen"'
		elif lines[index] == "metadata/" + SPECULAR_META + " = {":
			if not standard_resource or not screen_resource:
				_specular_error("Reserved metadata is outside its identified Screen material resource")
				return text
			inside = true
		elif inside and lines[index].begins_with('"specular_factor": '):
			lines[index] = '"specular_factor": ' + JSON.stringify(plan.factor, "", true, true)
			rewritten += 1
		elif inside and lines[index] == "}":
			inside = false
	if inside or rewritten != plan.bound_materials:
		_specular_error("Packed specular metadata did not preserve its complete scalar inventory")
	return "\n".join(lines)
