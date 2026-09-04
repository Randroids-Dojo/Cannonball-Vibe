extends SceneTree


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		push_error("Usage: -- INPUT_SCENE OUTPUT_SCENE")
		quit(2)
		return
	var source := load(args[0]) as PackedScene
	if source == null:
		push_error("Could not load %s" % args[0])
		quit(1)
		return
	var instance := source.instantiate()
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
	var unique_ids := RegEx.new()
	var regex_error := unique_ids.compile(" unique_id=\\d+")
	if regex_error != OK:
		push_error("Could not compile unique-ID normalizer")
		quit(1)
		return
	text = unique_ids.sub(text, "", true)
	text = _redirect_extracted_textures(text)
	text = _detach_textures(text, args[1].get_basename() + ".textures.json")
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
func _detach_textures(text: String, sidecar_path: String) -> String:
	var ext_pattern := RegEx.new()
	if ext_pattern.compile("^\\[ext_resource type=\"Texture2D\" path=\"([^\"]+)\" id=\"([^\"]+)\"\\]$") != OK:
		push_error("Could not compile texture ext_resource pattern")
		return text
	var slot_pattern := RegEx.new()
	if slot_pattern.compile("^(\\w+_texture) = ExtResource\\(\"([^\"]+)\"\\)$") != OK:
		push_error("Could not compile texture slot pattern")
		return text
	var name_pattern := RegEx.new()
	if name_pattern.compile("^resource_name = \"([^\"]+)\"$") != OK:
		push_error("Could not compile resource name pattern")
		return text
	var paths := {}
	var kept: PackedStringArray = []
	var bindings := {}
	var material := ""
	for line in text.split("\n"):
		var ext := ext_pattern.search(line)
		if ext != null:
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
				return text
			if not bindings.has(material):
				bindings[material] = {}
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
		return text
	sidecar.store_string(JSON.stringify({"schema": 1, "materials": ordered}, "  ") + "\n")
	sidecar.close()
	print("CANNONBALL_PACKED_TEXTURES_DETACHED materials=%d textures=%d sidecar=%s" % [ordered.size(), paths.size(), sidecar_path])
	return "\n".join(kept)


func _assign_owner(node: Node, scene_owner: Node) -> void:
	for child in node.get_children():
		child.owner = scene_owner
		_assign_owner(child, scene_owner)
