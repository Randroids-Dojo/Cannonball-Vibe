extends Node

const MAX_VEHICLE_RENDER_RECORDS := 64
const VEHICLE_ASSETS := ["endurance-sedan", "hero-gt", "graybox"]

@onready var _action_state: Label = $ActionStateFixture
var _vehicle_render_generation := 0
var _last_rendered_vehicle := 0
var _pending_vehicle_render: Dictionary = {}


func _ready() -> void:
	var hud := get_node("Main/PrototypeHud") as CanvasLayer
	var speed := hud.get_node("Speed") as Label
	if speed == null:
		push_error("PlayGodot bootstrap could not find the production HUD speed label")
		get_tree().quit(1)
		return
	for fixture_name in [
		"AutomationFixtureButton",
		"DuplicateFixtureA",
		"DuplicateFixtureB",
		"ColorFixture",
		"ActionStateFixture",
	]:
		get_node(fixture_name).reparent(hud)
	if OS.is_debug_build() and OS.get_cmdline_user_args().has("--playgodot"):
		RenderingServer.frame_pre_draw.connect(_before_vehicle_draw)
		RenderingServer.frame_post_draw.connect(_after_vehicle_draw)


func _process(_delta: float) -> void:
	_action_state.text = "pressed" if Input.is_action_pressed("ui_accept") else "released"


func _vehicle_render_identity() -> Dictionary:
	# This is the project fixture, not the generic RPC bridge. The panel belongs
	# to the actual new body and publishes its physical setup during _ready;
	# Main's periodically updated run metadata may still name the previous car.
	var vehicle := get_node_or_null("Main/CannonballVehicle") as Node3D
	if vehicle == null or not vehicle.is_inside_tree() or vehicle.is_queued_for_deletion() or not vehicle.is_visible_in_tree():
		return {}
	var panel := vehicle.get_node_or_null("VehicleInspectionPanel")
	if panel == null or not panel.is_inside_tree() or panel.is_queued_for_deletion() or not panel.has_meta("automation_state"):
		return {}
	var state = panel.get_meta("automation_state")
	if not state is Dictionary or state.get("selected_asset") not in VEHICLE_ASSETS:
		return {}
	var viewport := vehicle.get_viewport()
	var camera := viewport.get_camera_3d()
	if camera == null or not camera.is_inside_tree() or camera.is_queued_for_deletion():
		return {}
	return {
		"asset_id": state["selected_asset"],
		"vehicle_instance_id": vehicle.get_instance_id(),
		"panel_instance_id": panel.get_instance_id(),
		"viewport_instance_id": viewport.get_instance_id(),
		"camera_instance_id": camera.get_instance_id(),
	}


func _before_vehicle_draw() -> void:
	_pending_vehicle_render.clear()
	var identity := _vehicle_render_identity()
	if identity.is_empty() or identity["vehicle_instance_id"] == _last_rendered_vehicle:
		return
	_pending_vehicle_render = identity
	_pending_vehicle_render["pre_draw_usec"] = Time.get_ticks_usec()
	_pending_vehicle_render["pre_process_frame"] = Engine.get_process_frames()
	_pending_vehicle_render["pre_physics_frame"] = Engine.get_physics_frames()
	_pending_vehicle_render["pre_drawn_frame"] = Engine.get_frames_drawn()


func _after_vehicle_draw() -> void:
	if _pending_vehicle_render.is_empty():
		return
	var candidate := _pending_vehicle_render
	_pending_vehicle_render = {}
	var identity := _vehicle_render_identity()
	for key in identity:
		if identity[key] != candidate[key]:
			return
	if identity.is_empty() or candidate["pre_process_frame"] != Engine.get_process_frames() or candidate["pre_physics_frame"] != Engine.get_physics_frames() or candidate["pre_drawn_frame"] != Engine.get_frames_drawn():
		return
	if _vehicle_render_generation >= MAX_VEHICLE_RENDER_RECORDS:
		print("PLAYGODOT_VEHICLE_RENDER_FAILED record limit exceeded")
		_disconnect_vehicle_draw()
		return
	_vehicle_render_generation += 1
	_last_rendered_vehicle = identity["vehicle_instance_id"]
	candidate["generation"] = _vehicle_render_generation
	candidate["post_draw_usec"] = Time.get_ticks_usec()
	candidate["post_process_frame"] = Engine.get_process_frames()
	candidate["post_physics_frame"] = Engine.get_physics_frames()
	candidate["post_drawn_frame"] = Engine.get_frames_drawn()
	# Native software-rendered CI spent 29.36 seconds inside the first Hero draw.
	# This stdout preparation record is emitted after that work completes; it
	# neither services nor extends any live RPC request's normal deadline.
	print("PLAYGODOT_VEHICLE_RENDERED " + JSON.stringify(candidate))


func _disconnect_vehicle_draw() -> void:
	if RenderingServer.frame_pre_draw.is_connected(_before_vehicle_draw):
		RenderingServer.frame_pre_draw.disconnect(_before_vehicle_draw)
	if RenderingServer.frame_post_draw.is_connected(_after_vehicle_draw):
		RenderingServer.frame_post_draw.disconnect(_after_vehicle_draw)
	_pending_vehicle_render.clear()


func _exit_tree() -> void:
	_disconnect_vehicle_draw()
