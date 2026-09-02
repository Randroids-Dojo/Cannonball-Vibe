extends SceneTree

# Instantiates an importer-normalised environment asset scene with official
# Godot, resolves the semantic nodes the contract declares, counts triangles per
# LOD, proves the scene has no build-time dependencies, and writes the Godot
# inventory the manifest validator cross-checks against the Blender inventory.
#
#   godot --headless --path . --script res://tools/environments/validate_generated_scene.gd -- \
#       --scene res://assets/environments/trees/conifer/conifer.generated.tscn \
#       --contract res://data/assets/environments/trees/conifer.contract.json \
#       --import-settings res://data/assets/environments/trees/conifer.glb.import \
#       --glb res://data/assets/environments/trees/derived/conifer.glb \
#       --automation-id environment.asset.conifer \
#       --output reports/assets/conifer.godot.json \
#       --profile res://tools/assets/profiles/godot-4.7.1-v1.json


func _init() -> void:
	call_deferred("_validate")


func _arguments() -> Dictionary:
	var result := {}
	var values := OS.get_cmdline_user_args()
	var index := 0
	while index < values.size():
		if values[index].begins_with("--") and index + 1 < values.size():
			result[values[index].substr(2)] = values[index + 1]
			index += 2
		else:
			index += 1
	return result


func _fail(message: String) -> void:
	push_error(message)
	quit(1)


func _triangles(mesh: Mesh) -> int:
	var total := 0
	for surface_index in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface_index)
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if indices.is_empty():
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			total += vertices.size() / 3
		else:
			total += indices.size() / 3
	return total


func _visit(node: Node, names: Dictionary, lod_triangles: Dictionary, current_lod: String, inventory: Dictionary) -> void:
	names[node.name] = true
	var lod := current_lod
	if String(node.name).begins_with("Visual_LOD"):
		lod = String(node.name)
		lod_triangles[lod] = 0
	if node is MeshInstance3D:
		var mesh := (node as MeshInstance3D).mesh
		if mesh == null:
			_fail("Mesh node %s has no mesh" % node.name)
			return
		inventory.mesh_nodes.append(String(node.name))
		inventory.surface_count += mesh.get_surface_count()
		var triangles := _triangles(mesh)
		inventory.triangle_count += triangles
		if lod != "":
			lod_triangles[lod] += triangles
		for surface_index in mesh.get_surface_count():
			var arrays := mesh.surface_get_arrays(surface_index)
			if arrays[Mesh.ARRAY_COLOR] != null:
				inventory.color_attribute_surfaces += 1
			if arrays[Mesh.ARRAY_TANGENT] != null:
				inventory.tangent_surfaces += 1
	for child in node.get_children():
		_visit(child, names, lod_triangles, lod, inventory)


func _validate() -> void:
	var args := _arguments()
	for required in ["scene", "contract", "import-settings", "glb", "automation-id", "output", "profile"]:
		if not args.has(required):
			_fail("Missing --%s" % required)
			return
	var profile: Variant = JSON.parse_string(FileAccess.get_file_as_string(args.profile))
	if not profile is Dictionary or not profile.has("engine"):
		_fail("Godot import profile is missing its engine identity")
		return
	var version := Engine.get_version_info()
	var flavor := ".mono" if ClassDB.class_exists("CSharpScript") else ""
	var engine_identity := "%d.%d.%d.%s%s.%s.%s" % [
		version.major, version.minor, version.patch, version.status, flavor, version.build,
		str(version.hash).substr(0, 9),
	]
	if engine_identity != profile.engine:
		_fail("Godot identity drift: expected %s, got %s" % [profile.engine, engine_identity])
		return
	var contract: Variant = JSON.parse_string(FileAccess.get_file_as_string(args.contract))
	if not contract is Dictionary or not contract.has("required_nodes"):
		_fail("Asset contract is missing required_nodes")
		return
	var packed := load(args.scene) as PackedScene
	if packed == null:
		_fail("Could not load generated scene %s" % args.scene)
		return
	var instance := packed.instantiate()
	root.add_child(instance)
	var names := {}
	var lod_triangles := {}
	var inventory := {
		"schema_version": 1,
		"asset_id": contract.asset_id,
		"wrapper": args.scene,
		"automation_id": args["automation-id"],
		"mesh_nodes": [],
		"surface_count": 0,
		"triangle_count": 0,
		"color_attribute_surfaces": 0,
		"tangent_surfaces": 0,
	}
	_visit(instance, names, lod_triangles, "", inventory)
	var required: Array = contract.required_nodes
	for name in required:
		if not names.has(name):
			_fail("Generated scene is missing semantic node %s" % name)
			return
	var dependencies := ResourceLoader.get_dependencies(args.scene)
	for dependency in dependencies:
		var path := dependency.get_slice("::", dependency.get_slice_count("::") - 1)
		if path.contains("tools/") or path.ends_with(".blend") or path.ends_with(".glb"):
			_fail("Generated scene has a build-time dependency: %s" % dependency)
			return
	var required_sorted: Array = required.duplicate()
	required_sorted.sort()
	inventory["required_nodes"] = required_sorted
	inventory["all_required_nodes_resolved"] = true
	inventory["lod_triangles"] = lod_triangles
	inventory["lod_count"] = lod_triangles.size()
	inventory["release_dependency_count"] = dependencies.size()
	inventory["release_depends_on_blender"] = false
	inventory["release_depends_on_test_automation"] = false
	inventory["godot_version"] = engine_identity
	inventory["generated_scene_sha256"] = FileAccess.get_sha256(args.scene)
	inventory["glb_sha256"] = FileAccess.get_sha256(args.glb)
	inventory["import_settings_sha256"] = FileAccess.get_sha256(args["import-settings"])
	var output := FileAccess.open(args.output, FileAccess.WRITE)
	if output == null:
		_fail("Could not write %s" % args.output)
		return
	output.store_string(JSON.stringify(inventory, "  ") + "\n")
	output.close()
	instance.free()
	print("CANNONBALL_GENERATED_SCENE_OK asset=%s nodes=%d triangles=%d lods=%d" % [
		contract.asset_id, names.size(), inventory.triangle_count, lod_triangles.size()])
	quit(0)
