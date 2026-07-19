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


func _assign_owner(node: Node, scene_owner: Node) -> void:
	for child in node.get_children():
		child.owner = scene_owner
		_assign_owner(child, scene_owner)
