extends SceneTree

const REQUIRED_NODES := [
	"AssetRoot",
	"Visual_LOD0",
	"Visual_LOD1",
	"CollisionProxy",
	"Anchor_Origin",
]


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


func _visit(node: Node, names: Dictionary, inventory: Dictionary) -> void:
	names[node.name] = true
	if node is MeshInstance3D:
		var mesh_instance := node as MeshInstance3D
		var mesh := mesh_instance.mesh
		if mesh == null:
			_fail("Mesh node %s has no mesh" % node.name)
		inventory.mesh_nodes.append(node.name)
		inventory.surface_count += mesh.get_surface_count()
		for surface_index in mesh.get_surface_count():
			var arrays := mesh.surface_get_arrays(surface_index)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if indices.is_empty():
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				inventory.triangle_count += vertices.size() / 3
			else:
				inventory.triangle_count += indices.size() / 3
	for child in node.get_children():
		_visit(child, names, inventory)


func _fail(message: String) -> void:
	push_error(message)
	quit(1)


func _validate() -> void:
	var args := _arguments()
	if not args.has("wrapper") or not args.has("output") or not args.has("profile"):
		_fail("Usage: --wrapper res://path.tscn --output path.json --profile path.json")
		return
	var wrapper_path: String = args.wrapper
	var packed := load(wrapper_path) as PackedScene
	if packed == null:
		_fail("Could not load wrapper scene %s" % wrapper_path)
		return
	var instance := packed.instantiate()
	root.add_child(instance)
	var automation_id: String = instance.get_meta("automation_id", "")
	if automation_id != "asset.fixture.graybox-road-module":
		_fail("Wrapper automation ID is missing or unstable")
		return
	var names := {}
	var inventory := {
		"schema_version": 1,
		"asset_id": "graybox-road-module",
		"wrapper": wrapper_path,
		"automation_id": automation_id,
		"mesh_nodes": [],
		"surface_count": 0,
		"triangle_count": 0,
	}
	_visit(instance, names, inventory)
	for required in REQUIRED_NODES:
		if not names.has(required):
			_fail("Imported wrapper is missing semantic node %s" % required)
			return
	var dependencies := ResourceLoader.get_dependencies(wrapper_path)
	for dependency in dependencies:
		var path := dependency.get_slice("::", dependency.get_slice_count("::") - 1)
		if path.contains("tools/") or path.ends_with(".blend"):
			_fail("Release wrapper has a build-time dependency: %s" % dependency)
			return
	inventory["required_nodes"] = REQUIRED_NODES
	inventory["all_required_nodes_resolved"] = true
	inventory["release_dependency_count"] = dependencies.size()
	inventory["release_depends_on_blender"] = false
	inventory["release_depends_on_test_automation"] = false
	inventory["godot_version"] = Engine.get_version_info().string
	inventory["wrapper_sha256"] = FileAccess.get_sha256(wrapper_path)
	inventory["glb_sha256"] = FileAccess.get_sha256(
		"res://assets/pipeline-fixtures/graybox-road-module/graybox-road-module.glb"
	)
	inventory["import_settings_sha256"] = FileAccess.get_sha256(
		"res://assets/pipeline-fixtures/graybox-road-module/graybox-road-module.glb.import"
	)
	inventory["profile_sha256"] = FileAccess.get_sha256(args.profile)
	var output := FileAccess.open(args.output, FileAccess.WRITE)
	if output == null:
		_fail("Could not write Godot import inventory %s" % args.output)
		return
	output.store_string(JSON.stringify(inventory, "  ", true) + "\n")
	output.close()
	print(
		"CANNONBALL_ASSET_IMPORT_OK asset=graybox-road-module nodes=%d triangles=%d" %
		[names.size(), inventory.triangle_count]
	)
	instance.queue_free()
	quit(0)
