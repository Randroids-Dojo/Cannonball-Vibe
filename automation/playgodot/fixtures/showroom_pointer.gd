extends Node

var _viewer: Node
var _out: String
var _record := {"status": "ready", "cases": [], "captures": []}
var _published := {"status": "ready", "case_count": 0, "failed_count": 0, "last_case": ""}
var _started := false

func _ready() -> void:
	if not OS.has_feature("debug") or not OS.get_cmdline_user_args().has("--playgodot"):
		push_error("Pointer probe requires the debug PlayGodot launch")
		get_tree().quit(1)
		return
	_viewer = get_parent().get_node("VehicleShowroom")
	_out = OS.get_environment("CANNONBALL_SHOWROOM_POINTER_REPORT").replace("\\", "/")
	var owned = ProjectSettings.globalize_path("res://reports/").replace("\\", "/")
	if not _out.begins_with(owned) or not DirAccess.dir_exists_absolute(_out):
		push_error("Pointer report directory is not an existing owned report path")
		get_tree().quit(1)
		return
	set_meta("automation_id", "showroom.pointer-probe")
	set_meta("automation_state", _published)
	var start := Button.new()
	start.text = "Run native pointer probe"
	start.size = Vector2(1, 1)
	start.set_meta("automation_id", "showroom.pointer-probe.start")
	add_child(start)
	start.pressed.connect(_run)

func _state() -> Dictionary:
	return _viewer.get_meta("automation_state").duplicate(true)

func _settle() -> void:
	await get_tree().create_timer(0.16).timeout
	await get_tree().process_frame
	await RenderingServer.frame_post_draw

func _check(label: String, ok: bool, details: Dictionary = {}) -> void:
	var item = {"case": label, "passed": ok, "observed": details}
	_record["cases"].append(item)
	_published["case_count"] += 1
	_published["failed_count"] += 0 if ok else 1
	_published["last_case"] = label
	print("CANNONBALL_SHOWROOM_POINTER_CASE " + JSON.stringify(item))

func _key(code: Key) -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = code
		event.physical_keycode = code
		event.pressed = pressed
		get_viewport().push_input(event, true)

func _mouse(position: Vector2, button: MouseButton, pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.position = position
	event.global_position = position
	event.button_index = button
	event.pressed = pressed
	event.button_mask = (1 << (button - 1)) if pressed and button <= MOUSE_BUTTON_MIDDLE else 0
	get_viewport().push_input(event, true)

func _motion(position: Vector2, relative: Vector2, mask: int = 0) -> void:
	var event := InputEventMouseMotion.new()
	event.position = position
	event.global_position = position
	event.relative = relative
	event.screen_relative = relative
	event.button_mask = mask
	get_viewport().push_input(event, true)

func _control(identity: String) -> Control:
	var stack: Array[Node] = [_viewer]
	while not stack.is_empty():
		var node = stack.pop_back()
		if node is Control and node.get_meta("automation_id", "") == identity:
			return node
		for child in node.get_children():
			stack.append(child)
	return null

func _click(identity: String) -> void:
	var control = _control(identity)
	if control == null:
		_check("missing-control-" + identity, false)
		return
	var center = control.get_global_rect().get_center()
	_mouse(center, MOUSE_BUTTON_LEFT, true)
	_mouse(center, MOUSE_BUTTON_LEFT, false)

func _target(state: Dictionary) -> Vector3:
	return Vector3(state["target_x"], state["target_y"], state["target_z"])

func _capture(label: String) -> void:
	await RenderingServer.frame_post_draw
	var image = get_viewport().get_texture().get_image()
	var path = _out.path_join(label + ".png")
	var code = image.save_png(path)
	_record["captures"].append({"name": label, "path": path, "size": [image.get_width(), image.get_height()], "exit_code": code})
	_check("capture-" + label, code == OK)

func _run() -> void:
	if _started:
		return
	_started = true
	for child in get_children():
		if child is Button:
			child.hide()
	_record["status"] = "running"
	_published["status"] = "running"
	await _settle()
	_key(KEY_R)
	await _settle()
	var original = _state()
	var original_window_size = get_window().size
	_check("actual-sedan-private-world", original.get("asset_id") == "endurance-sedan" and original.get("private_world") and original.get("body_frozen") and original.get("rendered_frames", 0) > 0, original)
	await _capture("01-before")
	var point := Vector2(420, 310)
	_mouse(point, MOUSE_BUTTON_LEFT, true)
	_motion(point + Vector2(100, 40), Vector2(100, 40), MOUSE_BUTTON_MASK_LEFT)
	_mouse(point + Vector2(100, 40), MOUSE_BUTTON_LEFT, false)
	await _settle()
	var orbit = _state()
	_check("relative-left-orbit", abs(orbit["yaw"] - original["yaw"] + .4) < .0001 and abs(orbit["pitch"] - original["pitch"] - .16) < .0001, orbit)
	_motion(point + Vector2(200, 80), Vector2(100, 40))
	await _settle()
	_check("release-stops-orbit", _state()["yaw"] == orbit["yaw"] and _state()["pitch"] == orbit["pitch"], _state())
	await _capture("02-orbit")
	for button in [MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE]:
		var prior = _state()
		var pan_camera = _viewer.find_child("ShowroomViewport", true, false).get_camera_3d()
		var expected = (_target(prior) + (-pan_camera.global_basis.x * 30 + pan_camera.global_basis.y * 15) * prior["distance"] * .001).clamp(Vector3(-2.5, -.6, -3), Vector3(2.5, 2.5, 3))
		_mouse(point, button, true)
		_motion(point + Vector2(30, 15), Vector2(30, 15), 1 << (button - 1))
		_mouse(point + Vector2(30, 15), button, false)
		await _settle()
		var after = _state()
		_check("pan-" + str(button), _target(after).distance_to(_target(prior)) > .02 and _target(after).distance_to(expected) < .00001 and after["yaw"] == prior["yaw"], after)
	_key(KEY_R)
	await _settle()
	var before_wheel = _state()
	_mouse(point, MOUSE_BUTTON_WHEEL_UP, true)
	_mouse(point, MOUSE_BUTTON_WHEEL_UP, false)
	await _settle()
	_check("wheel-zooms-exterior", abs(_state()["distance"] - before_wheel["distance"] * exp(-.12)) < .0001, _state())
	_mouse(point, MOUSE_BUTTON_WHEEL_DOWN, true)
	_mouse(point, MOUSE_BUTTON_WHEEL_DOWN, false)
	await _settle()
	_check("wheel-reverses-exterior", abs(_state()["distance"] - before_wheel["distance"]) < .0001, _state())
	for direction in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
		for step in range(60):
			_mouse(point, direction, true)
			_mouse(point, direction, false)
		await _settle()
		_check("exterior-zoom-limit-" + str(direction), abs(_state()["distance"] - (.7 if direction == MOUSE_BUTTON_WHEEL_UP else 14.0)) < .0001, _state())
	_key(KEY_R)
	await _settle()
	var ui_center = _control("showroom.headlights").get_global_rect().get_center()
	var before_ui = _state()
	_mouse(ui_center, MOUSE_BUTTON_LEFT, true)
	_motion(ui_center + Vector2(30, 10), Vector2(30, 10), MOUSE_BUTTON_MASK_LEFT)
	_mouse(ui_center + Vector2(30, 10), MOUSE_BUTTON_LEFT, false)
	await _settle()
	_check("ui-does-not-start-orbit", _state()["yaw"] == before_ui["yaw"] and _state()["pitch"] == before_ui["pitch"], _state())
	_mouse(point, MOUSE_BUTTON_LEFT, true)
	_mouse(ui_center, MOUSE_BUTTON_LEFT, false)
	_motion(point, Vector2(75, 10))
	await _settle()
	_check("release-over-ui-stops-drag", _state()["yaw"] == before_ui["yaw"], _state())
	_mouse(point, MOUSE_BUTTON_LEFT, true)
	get_tree().root.propagate_notification(NOTIFICATION_APPLICATION_FOCUS_OUT)
	_motion(point + Vector2(90, 5), Vector2(90, 5), MOUSE_BUTTON_MASK_LEFT)
	await _settle()
	_check("focus-loss-clears-drag", _state()["yaw"] == before_ui["yaw"], _state())
	_mouse(point, MOUSE_BUTTON_LEFT, false)
	get_tree().root.propagate_notification(NOTIFICATION_APPLICATION_FOCUS_IN)
	_click("showroom.view.cockpit")
	await _settle()
	var cabin = _state()
	var viewport = _viewer.find_child("ShowroomViewport", true, false)
	var camera = viewport.get_camera_3d()
	var fov = camera.fov
	_mouse(point, MOUSE_BUTTON_WHEEL_UP, true)
	_mouse(point, MOUSE_BUTTON_WHEEL_UP, false)
	await _settle()
	_check("wheel-zooms-cockpit-fov", cabin["view"] == "cockpit" and abs(camera.fov - (fov - .12 * 28)) < .0001 and _state()["distance"] == cabin["distance"], {"before_fov": fov, "after_fov": camera.fov, "state": _state()})
	_mouse(point, MOUSE_BUTTON_LEFT, true)
	_motion(point + Vector2(30, 20), Vector2(30, 20), MOUSE_BUTTON_MASK_LEFT)
	_mouse(point + Vector2(30, 20), MOUSE_BUTTON_LEFT, false)
	await _settle()
	_check("cockpit-drag-direction", abs(_state()["yaw"] - cabin["yaw"] - .12) < .0001 and abs(_state()["pitch"] - cabin["pitch"] + .08) < .0001, _state())
	var before_interior_pan = _state()
	_mouse(point, MOUSE_BUTTON_RIGHT, true)
	_motion(point + Vector2(40, 20), Vector2(40, 20), MOUSE_BUTTON_MASK_RIGHT)
	_mouse(point + Vector2(40, 20), MOUSE_BUTTON_RIGHT, false)
	await _settle()
	_check("cockpit-does-not-pan-through-cabin", _target(_state()) == _target(before_interior_pan), _state())
	for direction in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
		for step in range(60):
			_mouse(point, direction, true)
			_mouse(point, direction, false)
		await _settle()
		_check("cockpit-fov-limit-" + str(direction), abs(camera.fov - (38.0 if direction == MOUSE_BUTTON_WHEEL_UP else 92.0)) < .0001, {"actual_fov": camera.fov})
	_click("showroom.view.cockpit")
	await _settle()
	await _capture("03-cockpit")
	_key(KEY_R)
	await _settle()
	var window = get_window()
	window.size = Vector2i(1600, 900)
	await _settle()
	# The desktop compositor can clamp a requested window to its usable area.
	# A real resize must occur and the private render target must follow it.
	var resized_window = window.size
	_check("live-resize-render-viewport", resized_window.x > 0 and resized_window.y > 0 and resized_window != original_window_size and Vector2i(_state()["viewport_width"], _state()["viewport_height"]) == resized_window, {"requested_window": [1600, 900], "original_window": [original_window_size.x, original_window_size.y], "actual_window": [resized_window.x, resized_window.y], "state": _state()})
	await _capture("04-resized")
	var before_resize_drag = _state()
	_mouse(point, MOUSE_BUTTON_LEFT, true)
	_motion(point + Vector2(40, 0), Vector2(40, 0), MOUSE_BUTTON_MASK_LEFT)
	_mouse(point + Vector2(40, 0), MOUSE_BUTTON_LEFT, false)
	await _settle()
	_check("orbit-after-resize", abs(_state()["yaw"] - before_resize_drag["yaw"] + .16) < .0001, _state())
	window.size = original_window_size
	await _settle()
	_check("restore-window", window.size == original_window_size and _state()["viewport_width"] == original_window_size.x and _state()["viewport_height"] == original_window_size.y, _state())
	_key(KEY_F1)
	await _settle()
	_check("hide-controls-after-pointer", not _state()["ui_visible"], _state())
	await _capture("05-controls-hidden")
	_key(KEY_F1)
	await _settle()
	var final = _state()
	_check("same-frozen-display-survives", original["vehicle_instance_id"] == final["vehicle_instance_id"] and original["world_instance_id"] == final["world_instance_id"] and final["body_frozen"] and final["display_speed_mps"] == 0, final)
	_record["status"] = "passed" if _record["cases"].all(func(row): return row["passed"]) else "failed"
	_record["final"] = final
	var file = FileAccess.open(_out.path_join("native-results.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_record, "\t") + "\n")
	file.close()
	_published["status"] = _record["status"]
	print("CANNONBALL_SHOWROOM_POINTER_COMPLETE " + _record["status"])
