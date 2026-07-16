extends Node

@onready var _action_state: Label = $ActionStateFixture


func _ready() -> void:
	var speed := get_node("PrototypeHud/Speed") as Label
	if speed == null:
		push_error("PlayGodot bootstrap could not find the production HUD speed label")
		get_tree().quit(1)
		return
	speed.text = "60 MPH"


func _process(_delta: float) -> void:
	_action_state.text = "pressed" if Input.is_action_pressed("ui_accept") else "released"
