extends Node

@onready var _action_state: Label = $ActionStateFixture


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


func _process(_delta: float) -> void:
	_action_state.text = "pressed" if Input.is_action_pressed("ui_accept") else "released"
