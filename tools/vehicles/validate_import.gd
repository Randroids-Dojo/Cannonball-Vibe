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

var _errors: Array[String] = []
var _name_counts := {}


func _source_point(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[2]), -float(value[1]))


func _vector(value: Vector3) -> Array:
	return [value.x, value.y, value.z]


func _check_close(label: String, actual: float, expected: float, tolerance: float) -> void:
	if not is_finite(actual) or absf(actual - expected) > tolerance:
		_fail("%s: measured %.7f, expected %.7f +/- %.7f" % [label, actual, expected, tolerance])


func _mesh_bounds(node: MeshInstance3D, frame: Transform3D) -> AABB:
	var first := true
	var bounds := AABB()
	var transform := frame.affine_inverse() * node.global_transform
	for surface in node.mesh.get_surface_count():
		var arrays := node.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for vertex in vertices:
			var point := transform * vertex
			if first:
				bounds = AABB(point, Vector3.ZERO)
				first = false
			else:
				bounds = bounds.expand(point)
	return bounds


func _validate_sedan(nodes: Dictionary, spec: Dictionary, inventory: Dictionary) -> void:
	var geometry: Dictionary = spec.geometry
	var tolerances: Dictionary = spec.tolerances
	var origin := (nodes.AssetRoot as Node3D).global_transform
	var measurements := {}
	for name in spec.hardpoints_source_m:
		var expected := _source_point(spec.hardpoints_source_m[name])
		var point: Vector3 = origin.affine_inverse() * (nodes[name] as Node3D).global_position
		var error := point.distance_to(expected)
		measurements[name] = {"expected_godot_m": _vector(expected), "measured_godot_m": _vector(point), "error_m": error}
		_check_close("Hardpoint %s" % name, error, 0.0, tolerances.hardpoint_m)
	for suffix in ["FL", "FR", "RL", "RR"]:
		var pivot := nodes["Wheel_" + suffix] as Node3D
		if pivot.get_parent() != nodes["Suspension_" + suffix] or pivot.position.length() > 0.00001:
			_fail("Wheel_%s must be a zero-position child of its Suspension pivot" % suffix)
		var tire_name: String = "LOD0_Tire_" + suffix
		if not nodes.has(tire_name) or not nodes[tire_name] is MeshInstance3D:
			_fail("Cannot measure tire mesh %s" % tire_name)
			continue
		var bounds := _mesh_bounds(nodes[tire_name], origin)
		_check_close(tire_name + " rolling radius Y", bounds.size.y * 0.5, geometry.wheel_radius_m, tolerances.wheelbase_track_radius_m)
		_check_close(tire_name + " rolling radius Z", bounds.size.z * 0.5, geometry.wheel_radius_m, tolerances.wheelbase_track_radius_m)
		_check_close(tire_name + " width", bounds.size.x, geometry.tire_width_m, tolerances.overall_final_m)
	for name in spec.mechanisms:
		var mechanism: Dictionary = spec.mechanisms[name]
		var expected := Basis(Vector3.RIGHT, deg_to_rad(float(mechanism.get("rest_rotation_x_deg", 0.0))))
		var actual := (nodes[name] as Node3D).basis
		for index in 3:
			_check_close("%s rest basis axis %s" % [name, index], rad_to_deg(actual[index].angle_to(expected[index])), 0.0, tolerances.hinge_axis_deg)
	if int(spec.get("specification_revision", 1)) >= 2:
		for side in ["Left", "Right"]:
			var door: Node = nodes["Door_FL" if side == "Left" else "Door_FR"]
			for prefix in ["Mirror_", "MirrorCamera_"]:
				if not door.is_ancestor_of(nodes[prefix + side]):
					_fail("Side mirror surface and camera must follow their front door: " + prefix + side)
	for box in spec.collision_boxes_godot_ground:
		var name: String = "CollisionProxy_" + str(box.name)
		if not nodes.has(name) or not nodes[name] is MeshInstance3D:
			_fail("Missing authored collision box %s" % name)
			continue
		var bounds := _mesh_bounds(nodes[name], origin)
		var expected_center := Vector3(float(box.center[0]), float(box.center[1]), float(box.center[2]))
		var expected_size := Vector3(float(box.size[0]), float(box.size[1]), float(box.size[2]))
		_check_close(name + " center", bounds.get_center().distance_to(expected_center), 0.0, tolerances.hardpoint_m)
		_check_close(name + " dimensions", bounds.size.distance_to(expected_size), 0.0, tolerances.hardpoint_m)
	var first := true
	var body_first := true
	var all_bounds := AABB()
	var body_bounds := AABB()
	for name in nodes:
		if not str(name).begins_with("LOD0_") or not nodes[name] is MeshInstance3D:
			continue
		var bounds := _mesh_bounds(nodes[name], origin)
		all_bounds = bounds if first else all_bounds.merge(bounds)
		first = false
		if not str(name).contains("Mirror") and not str(name).contains("Antenna"):
			body_bounds = bounds if body_first else body_bounds.merge(bounds)
			body_first = false
	_check_close("Overall length", body_bounds.size.z, geometry.length_m, tolerances.overall_final_m)
	_check_close("Body width excluding mirrors", body_bounds.size.x, geometry.body_width_m, tolerances.overall_final_m)
	_check_close("Width including mirrors", all_bounds.size.x, geometry.mirror_width_m, tolerances.overall_final_m)
	if nodes.has("LOD0_Roof"):
		var roof := _mesh_bounds(nodes.LOD0_Roof, origin)
		_check_close("Roof height above source ground", roof.end.y, geometry.roof_height_m, tolerances.overall_final_m)
	else:
		_fail("Missing LOD0_Roof for independent roof-height measurement")
	if (nodes.Light_Head_FL as Node3D).global_position.z >= (nodes.Light_Tail_RL as Node3D).global_position.z:
		_fail("Vehicle front must map to Godot -Z")
	for name in ["AssetRoot", "Chassis", "Visual_LOD0", "Visual_LOD1", "Visual_LOD2"]:
		var node := nodes[name] as Node3D
		if not node.basis.is_equal_approx(Basis.IDENTITY):
			_fail("Semantic frame %s has a nonidentity basis; axes or unapplied scale drifted" % name)
	inventory.hardpoint_measurements = measurements
	inventory.bounds_godot_m = {"minimum": _vector(all_bounds.position), "maximum": _vector(all_bounds.end)}
	inventory.measured_dimensions_m = {"length": body_bounds.size.z, "body_width": body_bounds.size.x, "mirror_width": all_bounds.size.x}
	inventory.axis_mapping_verified = "source (x,y,z) -> Godot (x,z,-y)"
	inventory.mechanism_rest_bases_verified = spec.mechanisms.keys()


func _validate_setup(instance: Node, spec: Dictionary, inventory: Dictionary) -> void:
	var setup: Resource = instance.get("RigSetup")
	if setup == null or setup.get("AssetId") != "endurance-sedan":
		_fail("Instantiated sedan wrapper has the wrong physical setup")
		return
	var g: Dictionary = spec.geometry
	var values := {
		"MassKilograms": spec.mass_and_fuel.nominal_fixed_running_mass_kg,
		"WheelbaseMeters": g.wheelbase_m, "FrontTrackMeters": g.front_track_m,
		"RearTrackMeters": g.rear_track_m, "TireRadiusMeters": g.wheel_radius_m,
		"SpringFreeLengthMeters": g.spring_free_length_m, "StaticCompressionMeters": g.static_compression_m,
		"ChassisOriginHeightMeters": g.chassis_origin_height_m,
		"MaximumSteerRadians": deg_to_rad(float(g.steering_lock_deg)),
		"FrontSpringRate": spec.gameplay.front_spring_rate_n_m,
		"RearSpringRate": spec.gameplay.rear_spring_rate_n_m,
		"EngineForceNewtons": spec.gameplay.engine_force_n, "BrakeForceNewtons": spec.gameplay.brake_force_n,
		"GroundedDownforceCoefficient": spec.gameplay.downforce_coefficient_n_per_mps2,
		"MaximumGroundedDownforceG": spec.gameplay.max_downforce_g,
	}
	var actual := {}
	for name in values:
		actual[name] = setup.get(name)
		_check_close("Runtime setup " + str(name), float(actual[name]), float(values[name]), maxf(0.000001, absf(float(values[name])) * 0.000001))
	for box in spec.collision_boxes_godot_ground:
		var prefix: String = "Cabin" if box.name == "Cabin" else ""
		var expected_center := Vector3(float(box.center[0]), float(box.center[1]), float(box.center[2]))
		var expected_size := Vector3(float(box.size[0]), float(box.size[1]), float(box.size[2]))
		var center: Vector3 = setup.get(prefix + "CollisionBoxCenter")
		var size: Vector3 = setup.get(prefix + "CollisionBoxSize")
		center += Vector3.UP * float(setup.get("ChassisOriginHeightMeters"))
		_check_close("Runtime collision center " + str(box.name), center.distance_to(expected_center), 0.0, 0.00001)
		_check_close("Runtime collision size " + str(box.name), size.distance_to(expected_size), 0.0, 0.00001)
	var center_of_mass: Vector3 = setup.get("CenterOfMassOffset")
	_check_close("Runtime CG forward", -center_of_mass.z, g.center_of_mass_forward_m, 0.00001)
	_check_close("Runtime CG height", center_of_mass.y + float(g.chassis_origin_height_m), g.center_of_mass_height_m, 0.00001)
	inventory.runtime_setup_values = actual
	inventory.collision_policy_verified = "authored two-box proxy dimensions match setup; actual RigidBody shape types are checked by the driving scenario"


func _dependencies(path: String, visited: Dictionary) -> void:
	if visited.has(path):
		return
	visited[path] = FileAccess.get_sha256(path)
	for dependency in ResourceLoader.get_dependencies(path):
		var next: String = dependency.get_slice("::", dependency.get_slice_count("::") - 1)
		if not next.begins_with("res://") or next.contains("/tools/") or next.contains("/game/Automation/") or next.ends_with(".blend"):
			_fail("Release wrapper has a nonportable/build/test dependency: %s" % dependency)
			continue
		if not ResourceLoader.exists(next):
			_fail("Release dependency is missing: %s" % next)
			continue
		_dependencies(next, visited)


func _adapter_inputs(directory: String, hashes: Dictionary) -> void:
	var access := DirAccess.open(directory)
	if access == null:
		_fail("Could not inventory runtime adapter source directory: " + directory)
		return
	access.list_dir_begin()
	var name := access.get_next()
	while name != "":
		var path := directory.path_join(name)
		if access.current_is_dir():
			_adapter_inputs(path, hashes)
		elif name.get_extension() in ["cs", "tres", "tscn", "gdshader", "uid"]:
			hashes[path] = FileAccess.get_sha256(path)
		name = access.get_next()
	access.list_dir_end()


func _init() -> void:
	call_deferred("_validate")


func _arguments() -> Dictionary:
	var result := {}
	var values := OS.get_cmdline_user_args()
	var index := 0
	while index < values.size():
		if values[index].begins_with("--") and values[index].contains("="):
			var separator := values[index].find("=")
			result[values[index].substr(2, separator - 2)] = values[index].substr(separator + 1)
			index += 1
		elif values[index].begins_with("--") and index + 1 < values.size():
			result[values[index].substr(2)] = values[index + 1]
			index += 2
		else:
			index += 1
	return result


func _visit(node: Node, nodes: Dictionary, inventory: Dictionary) -> void:
	_name_counts[node.name] = int(_name_counts.get(node.name, 0)) + 1
	nodes[node.name] = node
	if node is MeshInstance3D:
		var counts: Dictionary = inventory.runtime_generated if node.get_meta("vehicle_runtime_generated", false) else inventory
		var mesh_instance := node as MeshInstance3D
		var mesh := mesh_instance.mesh
		if mesh == null:
			_fail("Mesh node %s has no mesh" % node.name)
		counts.mesh_nodes.append(node.name)
		counts.surface_count += mesh.get_surface_count()
		for surface_index in mesh.get_surface_count():
			var arrays := mesh.surface_get_arrays(surface_index)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if indices.is_empty():
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				counts.triangle_count += vertices.size() / 3
			else:
				counts.triangle_count += indices.size() / 3
	for child in node.get_children():
		_visit(child, nodes, inventory)


func _fail(message: String) -> void:
	_errors.append(message)
	push_error(message)
	quit(1)


func _validate() -> void:
	var args := _arguments()
	var vehicle: String = args.get("vehicle", "hero-gt")
	if vehicle not in ["hero-gt", "endurance-sedan"]:
		_fail("Unsupported --vehicle %s" % vehicle)
		return
	var spec := {}
	var required_nodes: Array = REQUIRED_NODES.duplicate()
	if vehicle == "endurance-sedan":
		if not args.has("specification"):
			_fail("The sedan requires its locked --specification")
			return
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(args.specification))
		if not parsed is Dictionary or parsed.get("asset_id") != vehicle:
			_fail("Specification identity does not match the selected vehicle")
			return
		spec = parsed
		required_nodes.append("RigControls")
		for name in spec.hardpoints_source_m:
			if name not in required_nodes:
				required_nodes.append(name)
	for required in ["wrapper", "glb", "generated-scene", "import-settings", "output", "profile"]:
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
	var imported := load(args["generated-scene"]) as PackedScene
	if imported == null:
		_fail("Could not load normalized vehicle scene %s" % args["generated-scene"])
		return
	# Instantiate the actual project-owned wrapper: merely loading its text
	# misses C# _Ready failures and setup/material contract errors.
	var instance := packed.instantiate()
	root.add_child(instance)
	var automation_id := "vehicle.%s.visual-rig" % vehicle
	if instance.get_meta("automation_id", "") != automation_id or not instance.get_meta("vehicle_visual_rig_ready", false):
		_fail("Wrapper automation ID is missing or unstable")
		return
	var nodes := {}
	var inventory := {
		"schema_version": 1,
		"asset_id": vehicle,
		"wrapper": args.wrapper,
		"automation_id": automation_id,
		"mesh_nodes": [],
		"surface_count": 0,
		"triangle_count": 0,
		"script_reference_present": false,
		"wrapper_instantiated": true,
		"runtime_generated": {"mesh_nodes": [], "surface_count": 0, "triangle_count": 0},
	}
	var asset := instance.get_node_or_null("ImportedAsset")
	if asset == null:
		_fail("Instantiated wrapper has no ImportedAsset child")
		return
	_visit(asset, nodes, inventory)
	for required in required_nodes:
		if not nodes.has(required):
			_fail("Imported wrapper is missing semantic node %s" % required)
			return
		if int(_name_counts[required]) != 1:
			_fail("Semantic node %s occurs %d times" % [required, _name_counts[required]])
			return
	var front_left := nodes.Wheel_FL as Node3D
	var front_right := nodes.Wheel_FR as Node3D
	var rear_left := nodes.Wheel_RL as Node3D
	var rear_right := nodes.Wheel_RR as Node3D
	var wheelbase: float = absf(front_left.global_position.z - rear_left.global_position.z)
	var track: float = absf(front_left.global_position.x - front_right.global_position.x)
	var rear_track: float = absf(rear_left.global_position.x - rear_right.global_position.x)
	if vehicle == "hero-gt":
		_check_close("Hero wheelbase", wheelbase, 2.84, 0.0001)
		_check_close("Hero front track", track, 1.64, 0.0001)
		_check_close("Hero rear track", rear_track, 1.64, 0.0001)
	else:
		_check_close("Sedan wheelbase", wheelbase, spec.geometry.wheelbase_m, spec.tolerances.wheelbase_track_radius_m)
		_check_close("Sedan front track", track, spec.geometry.front_track_m, spec.tolerances.wheelbase_track_radius_m)
		_check_close("Sedan rear track", rear_track, spec.geometry.rear_track_m, spec.tolerances.wheelbase_track_radius_m)
		_validate_sedan(nodes, spec, inventory)
		_validate_setup(instance, spec, inventory)
		inventory.specification_sha256 = FileAccess.get_sha256(args.specification)
		var adapter_inputs := {}
		_adapter_inputs("res://game/Vehicle", adapter_inputs)
		inventory.runtime_adapter_input_sha256 = adapter_inputs
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
	var transitive := {}
	_dependencies(args.wrapper, transitive)
	if not _errors.is_empty():
		instance.free()
		return
	inventory.required_nodes = required_nodes
	inventory.semantic_name_counts = _name_counts
	inventory.transitive_release_dependencies = transitive
	inventory.all_required_nodes_resolved = true
	inventory.release_dependency_count = dependencies.size()
	inventory.release_depends_on_blender = false
	inventory.release_depends_on_test_automation = false
	inventory.godot_version = identity
	inventory.wrapper_sha256 = FileAccess.get_sha256(args.wrapper)
	inventory.glb_sha256 = FileAccess.get_sha256(args.glb)
	inventory.generated_scene_sha256 = FileAccess.get_sha256(args["generated-scene"])
	inventory.import_settings_sha256 = FileAccess.get_sha256(args["import-settings"])
	inventory.profile_sha256 = FileAccess.get_sha256(args.profile)
	inventory.validator_sha256 = FileAccess.get_sha256("res://tools/vehicles/validate_import.gd")
	inventory.wheelbase_meters = wheelbase
	inventory.track_meters = track
	inventory.rear_track_meters = rear_track
	inventory.lod_count = 3
	inventory.damage_zone_count = 5
	var output := FileAccess.open(args.output, FileAccess.WRITE)
	if output == null:
		_fail("Could not write Godot inventory %s" % args.output)
		return
	output.store_string(JSON.stringify(inventory, "  ", true) + "\n")
	output.close()
	print(
		"CANNONBALL_%s_IMPORT_OK nodes=%d triangles=%d wrapper_instantiated=true" %
		[vehicle.to_upper().replace("-", "_"), nodes.size(), inventory.triangle_count]
	)
	instance.queue_free()
	quit(0)
