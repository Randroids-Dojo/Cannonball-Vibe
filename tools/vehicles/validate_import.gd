extends SceneTree

const REQUIRED_NODES := [
	"AssetRoot", "Chassis", "Visual_LOD0", "Visual_LOD1", "Visual_LOD2",
	"CollisionProxy", "Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR",
	"Suspension_FL", "Suspension_FR", "Suspension_RL", "Suspension_RR",
	"Contact_FL", "Contact_FR", "Contact_RL", "Contact_RR",
	"Camera_ChaseTarget", "Camera_Cockpit", "Light_Head_FL", "Light_Head_FR",
	"Light_Tail_RL", "Light_Tail_RR", "Exhaust_L", "Exhaust_R",
	"Driver_Reference", "MaterialGroup_Body", "MaterialGroup_Glass",
	"MaterialGroup_Wheels", "MaterialGroup_Interior", "MaterialGroup_Lights",
	"Damage_Front", "Damage_Rear", "Damage_Left", "Damage_Right", "Damage_Roof",
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


func _visit(node: Node, nodes: Dictionary, inventory: Dictionary) -> void:
	nodes[node.name] = node
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
		_visit(child, nodes, inventory)


func _fail(message: String) -> void:
	push_error(message)
	quit(1)


func _validate() -> void:
	var args := _arguments()
	for required in ["wrapper", "glb", "import-settings", "output", "profile"]:
		if not args.has(required):
			_fail("Missing --%s" % required)
			return
	var profile: Variant = JSON.parse_string(FileAccess.get_file_as_string(args.profile))
	if not profile is Dictionary or not profile.has("engine"):
		_fail("Godot import profile is missing its engine identity")
		return
	var version := Engine.get_version_info()
	var flavor := ".mono" if ClassDB.class_exists("CSharpScript") else ""
	var identity := "%d.%d.%d.%s%s.%s.%s" % [
		version.major, version.minor, version.patch, version.status, flavor,
		version.build, str(version.hash).substr(0, 9),
	]
	if identity != profile.engine:
		_fail("Godot identity drift: expected %s, got %s" % [profile.engine, identity])
		return
	var packed := load(args.wrapper) as PackedScene
	if packed == null:
		_fail("Could not load wrapper %s" % args.wrapper)
		return
	var imported := load(args.glb) as PackedScene
	if imported == null:
		_fail("Could not load imported GLB %s" % args.glb)
		return
	var instance := imported.instantiate()
	root.add_child(instance)
	var wrapper_text := FileAccess.get_file_as_string(args.wrapper)
	var automation_id := "vehicle.hero-gt.visual-rig"
	if not wrapper_text.contains('metadata/automation_id = "vehicle.hero-gt.visual-rig"'):
		_fail("Wrapper automation ID is missing or unstable")
		return
	var nodes := {}
	var inventory := {
		"schema_version": 1,
		"asset_id": "hero-gt",
		"wrapper": args.wrapper,
		"automation_id": automation_id,
		"mesh_nodes": [],
		"surface_count": 0,
		"triangle_count": 0,
		"script_reference_present": false,
	}
	_visit(instance, nodes, inventory)
	for required in REQUIRED_NODES:
		if not nodes.has(required):
			_fail("Imported wrapper is missing semantic node %s" % required)
			return
	var front_left := nodes.Wheel_FL as Node3D
	var front_right := nodes.Wheel_FR as Node3D
	var rear_left := nodes.Wheel_RL as Node3D
	var wheelbase: float = absf(front_left.global_position.z - rear_left.global_position.z)
	var track: float = absf(front_left.global_position.x - front_right.global_position.x)
	if not is_equal_approx(wheelbase, 2.84) or not is_equal_approx(track, 1.64):
		_fail("Imported wheelbase or track contract drift")
		return
	var dependencies := ResourceLoader.get_dependencies(args.wrapper)
	for dependency in dependencies:
		var path := dependency.get_slice("::", dependency.get_slice_count("::") - 1)
		if path.ends_with("game/Vehicle/VehicleVisualRig.cs"):
			inventory.script_reference_present = true
		if path.contains("tools/") or path.ends_with(".blend"):
			_fail("Release wrapper has a build-time dependency: %s" % dependency)
			return
	if not inventory.script_reference_present:
		_fail("Wrapper does not reference VehicleVisualRig.cs")
		return
	inventory.required_nodes = REQUIRED_NODES
	inventory.all_required_nodes_resolved = true
	inventory.release_dependency_count = dependencies.size()
	inventory.release_depends_on_blender = false
	inventory.release_depends_on_test_automation = false
	inventory.godot_version = identity
	inventory.wrapper_sha256 = FileAccess.get_sha256(args.wrapper)
	inventory.glb_sha256 = FileAccess.get_sha256(args.glb)
	inventory.import_settings_sha256 = FileAccess.get_sha256(args["import-settings"])
	inventory.profile_sha256 = FileAccess.get_sha256(args.profile)
	inventory.wheelbase_meters = wheelbase
	inventory.track_meters = track
	inventory.lod_count = 3
	inventory.damage_zone_count = 5
	var output := FileAccess.open(args.output, FileAccess.WRITE)
	if output == null:
		_fail("Could not write Godot inventory %s" % args.output)
		return
	output.store_string(JSON.stringify(inventory, "  ", true) + "\n")
	output.close()
	print(
		"CANNONBALL_HERO_GT_IMPORT_OK nodes=%d triangles=%d" %
		[nodes.size(), inventory.triangle_count]
	)
	instance.queue_free()
	quit(0)
