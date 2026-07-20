extends Node

const PROTOCOL_VERSION := "1.0"
const REQUIRED_ENGINE := "4.7.1-stable (official)"
const MAX_REQUEST_BYTES := 65_536
const MAX_RECEIVE_BUFFER_BYTES := 131_072
const MAX_RESPONSE_BYTES := 2_000_000
const MAX_OUTBOUND_BYTES := 4_000_000
const OUTBOUND_TIMEOUT_MS := 5_000
const MAX_REQUESTS_PER_FRAME := 32
const MAX_JSON_DEPTH := 12
const MAX_TREE_DEPTH := 8
const MAX_TREE_NODES := 512
const MAX_SELECTOR_NODES := 10_000
const MAX_STATE_DEPTH := 4
const MAX_STATE_VALUES := 64
const MAX_SCREENSHOT_BYTES := 1_400_000
const MAX_TRANSCRIPT_BYTES := 5_000_000
const HANDSHAKE_TIMEOUT_MS := 5_000
const AUTH_FAILURE_WINDOW_MS := 10_000
const MAX_AUTH_FAILURES_PER_WINDOW := 5
const AUTH_FAILURE_COOLDOWN_MS := 5_000
const MAX_SIGNAL_WAIT_MS := 10_000
const MAX_PENDING_SIGNAL_WAITS := 8
const TARGET_ID_PATTERN := "^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"

var _listener: TCPServer
var _peer: StreamPeerTCP
var _receive_buffer := PackedByteArray()
var _send_buffer := PackedByteArray()
var _send_started_ms := 0
var _token := ""
var _authenticated := false
var _connected_at_ms := 0
var _granted_capabilities: Array[String] = []
var _allowed_capabilities: Array[String] = ["read"]
var _pending_signals: Dictionary = {}
var _signal_results: Dictionary = {}
var _close_after_response := false
var _transcript_path := ""
var _id_regex := RegEx.new()
var _pressed_actions: Array[String] = []
var _pressed_keys: Array[int] = []
var _joy_axes: Dictionary = {}
var _pressed_joy_buttons: Dictionary = {}
var _auth_failures: Array[int] = []
var _auth_blocked_until_ms := 0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	# The debug transport must service bounded requests before the game performs
	# potentially expensive streaming or renderer work on the same main thread.
	# This keeps the control plane responsive without relaxing protocol timeouts.
	process_priority = -1_000_000
	if not _should_start():
		set_process(false)
		return
	if str(Engine.get_version_info()["string"]) != REQUIRED_ENGINE:
		_fail_start("official Godot 4.7.1 is required")
		return
	_id_regex.compile(TARGET_ID_PATTERN)
	_token = OS.get_environment("PLAYGODOT_TOKEN")
	if _token.length() < 32:
		_fail_start("PLAYGODOT_TOKEN must contain at least 32 characters")
		return
	_transcript_path = OS.get_environment("PLAYGODOT_TRANSCRIPT")
	_allowed_capabilities = _parse_allowed_capabilities(
		OS.get_environment("PLAYGODOT_CAPABILITIES")
	)
	_listener = TCPServer.new()
	var error := _listener.listen(0, "127.0.0.1")
	if error != OK:
		_fail_start("loopback listen failed: %s" % error_string(error))
		return
	print("PLAYGODOT_READY " + JSON.stringify({
		"address": "127.0.0.1",
		"port": _listener.get_local_port(),
		"protocol": PROTOCOL_VERSION,
		"engine": Engine.get_version_info()["string"],
	}))


func _should_start() -> bool:
	if OS.get_name() == "Web" or not OS.is_debug_build():
		return false
	return OS.get_cmdline_user_args().has("--playgodot")


func _parse_allowed_capabilities(raw: String) -> Array[String]:
	var result: Array[String] = ["read"]
	for value in raw.split(",", false):
		var capability := value.strip_edges()
		if capability in ["read", "input", "screenshot"] and not result.has(capability):
			result.append(capability)
	return result


func _fail_start(message: String) -> void:
	push_error("PLAYGODOT_START_FAILED " + message)
	set_process(false)


func _process(_delta: float) -> void:
	_accept_connection()
	_poll_connection()
	_poll_pending_signals()
	_flush_outbound()


func _accept_connection() -> void:
	if _listener == null or not _listener.is_connection_available():
		return
	var candidate := _listener.take_connection()
	if Time.get_ticks_msec() < _auth_blocked_until_ms:
		candidate.disconnect_from_host()
		return
	if _peer != null and _peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		candidate.disconnect_from_host()
		return
	if _peer != null:
		_clear_connection()
	_peer = candidate
	_peer.set_no_delay(true)
	_receive_buffer.clear()
	_send_buffer.clear()
	_send_started_ms = 0
	_authenticated = false
	_granted_capabilities.clear()
	_connected_at_ms = Time.get_ticks_msec()


func _poll_connection() -> void:
	if _peer == null:
		return
	_peer.poll()
	if _peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		_clear_connection()
		return
	if _close_after_response:
		return
	if not _authenticated and Time.get_ticks_msec() - _connected_at_ms > HANDSHAKE_TIMEOUT_MS:
		_send_error(null, -32001, "AUTH_REQUIRED", "Handshake timed out")
		_record(null, "session.hello", "auth_timeout", _connected_at_ms)
		_close_after_response = true
		return
	if _peer.get_available_bytes() > 0 and _receive_buffer.size() < MAX_RECEIVE_BUFFER_BYTES:
		var capacity := MAX_RECEIVE_BUFFER_BYTES - _receive_buffer.size()
		var read_bytes := mini(_peer.get_available_bytes(), capacity)
		var read_result := _peer.get_data(read_bytes)
		if read_result[0] != OK:
			_clear_connection()
			return
		_receive_buffer.append_array(read_result[1])
	if _receive_buffer.size() > MAX_REQUEST_BYTES and _receive_buffer.find(10) < 0:
		_send_error(null, -32006, "LIMIT_EXCEEDED", "Request exceeds byte limit")
		_record(null, "unknown", "limit_exceeded", Time.get_ticks_msec())
		_close_after_response = true
		return
	var processed := 0
	while _receive_buffer.find(10) >= 0 and processed < MAX_REQUESTS_PER_FRAME:
		var newline := _receive_buffer.find(10)
		var line_bytes := _receive_buffer.slice(0, newline)
		_receive_buffer = _receive_buffer.slice(newline + 1)
		var line := line_bytes.get_string_from_utf8()
		if line.to_utf8_buffer() != line_bytes:
			_send_error(null, -32700, "PARSE_ERROR", "Request is not valid UTF-8")
			_record(null, "unknown", "parse_error", Time.get_ticks_msec())
		else:
			_handle_line(line)
		processed += 1
		if _peer == null:
			return
		if _close_after_response:
			break


func _handle_line(line: String) -> void:
	var started := Time.get_ticks_msec()
	if line.to_utf8_buffer().size() > MAX_REQUEST_BYTES:
		_send_error(null, -32006, "LIMIT_EXCEEDED", "Request exceeds byte limit")
		_record(null, "unknown", "limit_exceeded", started)
		return
	var parser := JSON.new()
	if parser.parse(line) != OK:
		_send_error(null, -32700, "PARSE_ERROR", "Malformed JSON")
		_record(null, "unknown", "parse_error", started)
		return
	var request = parser.data
	if not request is Dictionary or _json_depth(request) > MAX_JSON_DEPTH:
		_send_error(null, -32600, "INVALID_REQUEST", "Invalid or over-depth request")
		_record(null, "unknown", "invalid_request", started)
		return
	var request_id = request.get("id")
	var method = request.get("method")
	var params = request.get("params", {})
	if (
		request.get("jsonrpc") != "2.0"
		or not _valid_request_id(request_id)
		or not method is String
		or method.is_empty()
		or not params is Dictionary
	):
		_send_error(request_id, -32600, "INVALID_REQUEST", "Invalid JSON-RPC envelope")
		_record(request_id, str(method), "invalid_request", started)
		return
	request_id = int(request_id)
	if not _authenticated and method != "session.hello":
		_send_error(request_id, -32001, "AUTH_REQUIRED", "session.hello must be first")
		_record(request_id, method, "auth_required", started)
		return
	if _pending_signals.has(str(request_id)):
		_send_error(request_id, -32600, "INVALID_REQUEST", "Request ID is already pending")
		_record(request_id, method, "invalid_request", started)
		return
	var response := _dispatch(method, params, request_id)
	if response.get("pending", false):
		return
	if response.has("error"):
		var error: Dictionary = response["error"]
		_send_error(request_id, error["code"], error["name"], error["message"])
		_record(request_id, method, error["name"].to_lower(), started)
	else:
		_send_result(request_id, response.get("result"))
		_record(request_id, method, "success", started)


func _valid_request_id(value: Variant) -> bool:
	if not (value is int or value is float) or value is bool:
		return false
	var numeric := float(value)
	return numeric == floorf(numeric) and numeric >= 1.0 and numeric <= 9_007_199_254_740_991.0


func _dispatch(method: String, params: Dictionary, request_id: Variant) -> Dictionary:
	match method:
		"session.hello":
			return _session_hello(params)
		"session.ping":
			return {"result": {"ok": true}}
		"session.capabilities":
			return {"result": _capability_document()}
		"session.close":
			_close_after_response = true
			return {"result": {"closed": true}}
		"scene.current":
			return _require("read", func(): return _scene_current())
		"scene.tree":
			return _require("read", func(): return _scene_tree(params))
		"node.find":
			return _require("read", func(): return _node_find(params))
		"node.describe", "ui.describe":
			return _require("read", func(): return _describe_target(params))
		"node.children":
			return _require("read", func(): return _node_children(params))
		"ui.focused":
			return _require("read", func(): return _ui_focused())
		"signal.wait":
			return _require("read", func(): return _signal_wait(params, request_id))
		"input.action":
			return _require("input", func(): return _input_action(params))
		"input.key":
			return _require("input", func(): return _input_key(params))
		"input.joypad_motion":
			return _require("input", func(): return _input_joypad_motion(params))
		"input.joypad_button":
			return _require("input", func(): return _input_joypad_button(params))
		"input.click":
			return _require("input", func(): return _input_click(params))
		"input.drag":
			return _require("input", func(): return _input_drag(params))
		"screenshot.viewport":
			return _require("screenshot", func(): return _screenshot(null))
		"screenshot.node":
			return _require("screenshot", func(): return _screenshot_target(params))
		_:
			return _error(-32601, "METHOD_NOT_FOUND", "Method is not allowlisted")


func _require(capability: String, operation: Callable) -> Dictionary:
	if not _granted_capabilities.has(capability):
		return _error(-32003, "CAPABILITY_DENIED", "Capability is not granted")
	return operation.call()


func _session_hello(params: Dictionary) -> Dictionary:
	if _authenticated:
		return _error(-32600, "INVALID_REQUEST", "Session is already authenticated")
	var requested = params.get("capabilities", [])
	if params.get("token") != _token or params.get("protocol") != PROTOCOL_VERSION:
		_register_auth_failure()
		_close_after_response = true
		return _error(-32002, "AUTH_FAILED", "Authentication or protocol negotiation failed")
	if not requested is Array:
		_close_after_response = true
		return _error(-32602, "INVALID_PARAMS", "capabilities must be an array")
	var granted: Array[String] = []
	for value in requested:
		if not value is String or not _allowed_capabilities.has(value) or granted.has(value):
			_close_after_response = true
			return _error(-32003, "CAPABILITY_DENIED", "Requested capability is unavailable")
		granted.append(value)
	if not granted.has("read"):
		granted.push_front("read")
	_authenticated = true
	_auth_failures.clear()
	_granted_capabilities = granted
	return {"result": {
		"protocol": PROTOCOL_VERSION,
		"engine": Engine.get_version_info()["string"],
		"build": "debug",
		"capabilities": granted,
		"limits": _capability_document()["limits"],
	}}


func _register_auth_failure() -> void:
	var now := Time.get_ticks_msec()
	var recent: Array[int] = []
	for failure in _auth_failures:
		if now - failure <= AUTH_FAILURE_WINDOW_MS:
			recent.append(failure)
	recent.append(now)
	_auth_failures = recent
	if _auth_failures.size() >= MAX_AUTH_FAILURES_PER_WINDOW:
		_auth_blocked_until_ms = now + AUTH_FAILURE_COOLDOWN_MS


func _capability_document() -> Dictionary:
	return {
		"granted": _granted_capabilities,
		"methods": [
			"session.ping", "session.capabilities", "session.close",
			"scene.current", "scene.tree", "node.find", "node.describe",
			"node.children", "ui.describe", "ui.focused", "signal.wait",
			"input.action", "input.key", "input.joypad_motion",
			"input.joypad_button", "input.click", "input.drag",
			"screenshot.viewport", "screenshot.node",
		],
		"limits": {
			"request_bytes": MAX_REQUEST_BYTES,
			"receive_buffer_bytes": MAX_RECEIVE_BUFFER_BYTES,
			"requests_per_frame": MAX_REQUESTS_PER_FRAME,
			"response_bytes": MAX_RESPONSE_BYTES,
			"outbound_bytes": MAX_OUTBOUND_BYTES,
			"json_depth": MAX_JSON_DEPTH,
			"tree_depth": MAX_TREE_DEPTH,
			"tree_nodes": MAX_TREE_NODES,
			"signal_wait_ms": MAX_SIGNAL_WAIT_MS,
			"pending_signal_waits": MAX_PENDING_SIGNAL_WAITS,
			"screenshot_bytes": MAX_SCREENSHOT_BYTES,
			"transcript_bytes": MAX_TRANSCRIPT_BYTES,
		},
	}


func _scene_current() -> Dictionary:
	var scene := get_tree().current_scene
	return {"result": {
		"path": scene.scene_file_path if scene != null else "",
		"name": str(scene.name) if scene != null else "",
	}}


func _scene_tree(params: Dictionary) -> Dictionary:
	var depth_result := _bounded_integer(params, "max_depth", MAX_TREE_DEPTH, 0, MAX_TREE_DEPTH)
	var nodes_result := _bounded_integer(params, "max_nodes", MAX_TREE_NODES, 1, MAX_TREE_NODES)
	if depth_result.has("error"):
		return depth_result
	if nodes_result.has("error"):
		return nodes_result
	var max_depth: int = depth_result["value"]
	var max_nodes: int = nodes_result["value"]
	var state := {"count": 0, "truncated": false}
	var nodes := _tree_node(get_tree().root, 0, max_depth, max_nodes, state)
	return {"result": {"root": nodes, "count": state["count"], "truncated": state["truncated"]}}


func _tree_node(node: Node, depth: int, max_depth: int, max_nodes: int, state: Dictionary) -> Dictionary:
	state["count"] += 1
	var data := {"name": str(node.name), "class": node.get_class(), "path": str(node.get_path()), "children": []}
	if node.has_meta("automation_id"):
		data["automation_id"] = str(node.get_meta("automation_id"))
	if depth >= max_depth:
		if node.get_child_count() > 0:
			state["truncated"] = true
		return data
	for child in node.get_children():
		if state["count"] >= max_nodes:
			state["truncated"] = true
			break
		data["children"].append(_tree_node(child, depth + 1, max_depth, max_nodes, state))
	return data


func _node_find(params: Dictionary) -> Dictionary:
	var resolved := _resolve_target(params)
	if resolved.has("error"):
		return resolved
	return {"result": _describe(resolved["node"])}


func _describe_target(params: Dictionary) -> Dictionary:
	return _node_find(params)


func _node_children(params: Dictionary) -> Dictionary:
	var resolved := _resolve_target(params)
	if resolved.has("error"):
		return resolved
	var limit_result := _bounded_integer(params, "max_children", MAX_TREE_NODES, 1, MAX_TREE_NODES)
	if limit_result.has("error"):
		return limit_result
	var max_children: int = limit_result["value"]
	var children: Array[Dictionary] = []
	var truncated := false
	for child in resolved["node"].get_children():
		if child.has_meta("automation_id"):
			if children.size() >= max_children:
				truncated = true
				break
			children.append(_describe(child))
	return {"result": {"children": children, "truncated": truncated}}


func _ui_focused() -> Dictionary:
	var focused := get_viewport().gui_get_focus_owner()
	if focused == null or not focused.has_meta("automation_id"):
		return {"result": null}
	return {"result": _describe(focused)}


func _resolve_target(params: Dictionary) -> Dictionary:
	var automation_id = params.get("automation_id")
	if not automation_id is String or _id_regex.search(automation_id) == null:
		return _error(-32602, "INVALID_PARAMS", "A valid automation_id is required")
	var matches: Array[Node] = []
	var scan := {"count": 0, "truncated": false}
	_collect_target_matches(get_tree().root, automation_id, matches, scan)
	if scan["truncated"] and matches.size() < 2:
		return _error(-32006, "LIMIT_EXCEEDED", "Automation target scan exceeded its node limit")
	if matches.is_empty():
		return _error(-32004, "NOT_FOUND", "Automation target was not found")
	if matches.size() > 1:
		return _error(-32005, "DUPLICATE_ID", "Automation ID is not unique")
	return {"node": matches[0]}


func _collect_target_matches(
	node: Node,
	automation_id: String,
	matches: Array[Node],
	state: Dictionary
) -> void:
	if matches.size() > 1:
		return
	if state["count"] >= MAX_SELECTOR_NODES:
		state["truncated"] = true
		return
	state["count"] += 1
	if node.has_meta("automation_id") and str(node.get_meta("automation_id")) == automation_id:
		matches.append(node)
	for child in node.get_children():
		_collect_target_matches(child, automation_id, matches, state)
		if matches.size() > 1 or state["truncated"]:
			return


func _describe(node: Node) -> Dictionary:
	var data := {
		"automation_id": str(node.get_meta("automation_id")),
		"class": node.get_class(),
		"name": str(node.name),
		"path": str(node.get_path()),
		"visible": node.is_visible_in_tree() if node is CanvasItem else true,
	}
	if node is Control:
		var rect: Rect2 = node.get_global_rect()
		data["bounds"] = {"x": rect.position.x, "y": rect.position.y, "width": rect.size.x, "height": rect.size.y}
		data["focused"] = node.has_focus()
		data["enabled"] = not node.disabled if node is BaseButton else true
		if node is Label or node is Button or node is LineEdit:
			data["text"] = node.text
	if node.has_meta("automation_state"):
		var state_budget := {"count": 0}
		var normalized := _normalize_test_state(node.get_meta("automation_state"), 0, state_budget)
		if normalized["ok"]:
			data["test_state"] = normalized["value"]
	return data


func _bounded_integer(
	params: Dictionary,
	name: String,
	default_value: int,
	minimum: int,
	maximum: int
) -> Dictionary:
	var raw = params.get(name, default_value)
	if not (raw is int or raw is float) or raw is bool or float(raw) != floorf(float(raw)):
		return _error(-32602, "INVALID_PARAMS", "%s must be an integer" % name)
	var value := int(raw)
	if value < minimum or value > maximum:
		return _error(-32602, "INVALID_PARAMS", "%s is outside the allowed range" % name)
	return {"value": value}


func _normalize_test_state(value: Variant, depth: int, budget: Dictionary) -> Dictionary:
	budget["count"] += 1
	if depth > MAX_STATE_DEPTH or budget["count"] > MAX_STATE_VALUES:
		return {"ok": false}
	if value == null or value is bool or value is int or value is float:
		return {"ok": true, "value": value}
	if value is String:
		if value.length() > 1_024:
			return {"ok": false}
		return {"ok": true, "value": value}
	if value is Array:
		var array: Array = []
		for child in value:
			var normalized := _normalize_test_state(child, depth + 1, budget)
			if not normalized["ok"]:
				return {"ok": false}
			array.append(normalized["value"])
		return {"ok": true, "value": array}
	if value is Dictionary:
		var dictionary := {}
		for key in value.keys():
			if not key is String or key.length() > 128:
				return {"ok": false}
			var normalized := _normalize_test_state(value[key], depth + 1, budget)
			if not normalized["ok"]:
				return {"ok": false}
			dictionary[key] = normalized["value"]
		return {"ok": true, "value": dictionary}
	return {"ok": false}


func _signal_wait(params: Dictionary, request_id: Variant) -> Dictionary:
	if _pending_signals.size() >= MAX_PENDING_SIGNAL_WAITS:
		return _error(-32007, "BUSY", "Too many pending waits")
	var resolved := _resolve_target(params)
	if resolved.has("error"):
		return resolved
	var node: Node = resolved["node"]
	var signal_name = params.get("signal")
	var timeout_value = params.get("timeout_ms", 1_000)
	if not signal_name is String or not node.has_signal(signal_name):
		return _error(-32602, "INVALID_PARAMS", "Unknown signal")
	if not (timeout_value is int or timeout_value is float) or float(timeout_value) != floorf(float(timeout_value)):
		return _error(-32602, "INVALID_PARAMS", "timeout_ms must be an integer")
	var timeout_ms := int(timeout_value)
	if timeout_ms <= 0 or timeout_ms > MAX_SIGNAL_WAIT_MS:
		return _error(-32602, "INVALID_PARAMS", "timeout_ms is outside the allowed range")
	var signal_info := node.get_signal_list().filter(func(item): return item["name"] == signal_name)
	if signal_info.is_empty() or not signal_info[0]["args"].is_empty():
		return _error(-32602, "INVALID_PARAMS", "Only zero-argument signals are supported")
	var key := str(request_id)
	if _pending_signals.has(key):
		return _error(-32600, "INVALID_REQUEST", "Request ID is already pending")
	var callback := Callable(self, "_on_pending_signal").bind(key)
	node.connect(signal_name, callback, CONNECT_ONE_SHOT)
	_pending_signals[key] = {
		"id": request_id,
		"node": node,
		"signal": signal_name,
		"callback": callback,
		"started": Time.get_ticks_msec(),
		"deadline": Time.get_ticks_msec() + timeout_ms,
	}
	return {"pending": true}


func _on_pending_signal(key: String) -> void:
	_signal_results[key] = true


func _poll_pending_signals() -> void:
	for key in _pending_signals.keys():
		var pending: Dictionary = _pending_signals[key]
		if _signal_results.has(key):
			_send_result(pending["id"], {"signal": pending["signal"]})
			_record(pending["id"], "signal.wait", "success", pending["started"])
			_pending_signals.erase(key)
			_signal_results.erase(key)
		elif Time.get_ticks_msec() >= pending["deadline"]:
			var node: Node = pending["node"]
			if is_instance_valid(node) and node.is_connected(pending["signal"], pending["callback"]):
				node.disconnect(pending["signal"], pending["callback"])
			_send_error(pending["id"], -32008, "TIMEOUT", "Signal wait timed out")
			_record(pending["id"], "signal.wait", "timeout", pending["started"])
			_pending_signals.erase(key)


func _input_action(params: Dictionary) -> Dictionary:
	var action = params.get("action")
	var state = params.get("state")
	if not action is String or not InputMap.has_action(action) or state not in ["press", "release"]:
		return _error(-32602, "INVALID_PARAMS", "Unknown action or state")
	if state == "press":
		Input.action_press(action)
		if not _pressed_actions.has(action):
			_pressed_actions.append(action)
	else:
		Input.action_release(action)
		_pressed_actions.erase(action)
	return {"result": {"action": action, "state": state}}


func _input_key(params: Dictionary) -> Dictionary:
	var key_name = params.get("key")
	var state = params.get("state")
	if not key_name is String or state not in ["press", "release"]:
		return _error(-32602, "INVALID_PARAMS", "Invalid key or state")
	var keycode := OS.find_keycode_from_string(key_name)
	if keycode == KEY_NONE:
		return _error(-32602, "INVALID_PARAMS", "Unknown key")
	var event := InputEventKey.new()
	event.keycode = keycode
	event.pressed = state == "press"
	Input.parse_input_event(event)
	if event.pressed and not _pressed_keys.has(keycode):
		_pressed_keys.append(keycode)
	elif not event.pressed:
		_pressed_keys.erase(keycode)
	return {"result": {"key": key_name, "state": state}}


func _input_joypad_motion(params: Dictionary) -> Dictionary:
	var axis_name = params.get("axis")
	var value = params.get("value")
	var device := _joypad_device(params)
	var axes := {
		"left_x": JOY_AXIS_LEFT_X,
		"left_y": JOY_AXIS_LEFT_Y,
		"trigger_left": JOY_AXIS_TRIGGER_LEFT,
		"trigger_right": JOY_AXIS_TRIGGER_RIGHT,
	}
	if (
		not axis_name is String
		or not axes.has(axis_name)
		or not (value is int or value is float)
		or value is bool
		or device < 0
		or not is_finite(float(value))
		or absf(float(value)) > 1.0
	):
		return _error(-32602, "INVALID_PARAMS", "Invalid joypad motion")
	var event := InputEventJoypadMotion.new()
	event.device = device
	event.axis = axes[axis_name]
	event.axis_value = float(value)
	Input.parse_input_event(event)
	var key := "%d:%d" % [device, event.axis]
	if absf(event.axis_value) > 0.0001:
		_joy_axes[key] = {"device": device, "axis": event.axis}
	else:
		_joy_axes.erase(key)
	return {"result": {"axis": axis_name, "value": event.axis_value, "device": device}}


func _input_joypad_button(params: Dictionary) -> Dictionary:
	var button_name = params.get("button")
	var state = params.get("state")
	var device := _joypad_device(params)
	var buttons := {
		"a": JOY_BUTTON_A,
		"b": JOY_BUTTON_B,
		"x": JOY_BUTTON_X,
		"y": JOY_BUTTON_Y,
		"left_stick": JOY_BUTTON_LEFT_STICK,
		"right_stick": JOY_BUTTON_RIGHT_STICK,
	}
	if (
		not button_name is String
		or not buttons.has(button_name)
		or state not in ["press", "release"]
		or device < 0
	):
		return _error(-32602, "INVALID_PARAMS", "Invalid joypad button or state")
	var event := InputEventJoypadButton.new()
	event.device = device
	event.button_index = buttons[button_name]
	event.pressed = state == "press"
	Input.parse_input_event(event)
	var key := "%d:%d" % [device, event.button_index]
	if event.pressed:
		_pressed_joy_buttons[key] = {"device": device, "button": event.button_index}
	else:
		_pressed_joy_buttons.erase(key)
	return {"result": {"button": button_name, "state": state, "device": device}}


func _joypad_device(params: Dictionary) -> int:
	var value = params.get("device", 0)
	if not (value is int or value is float) or value is bool:
		return -1
	var numeric := float(value)
	if not is_finite(numeric) or numeric != floorf(numeric) or numeric < 0.0 or numeric > 15.0:
		return -1
	return int(numeric)


func _input_click(params: Dictionary) -> Dictionary:
	var resolved := _resolve_target(params)
	if resolved.has("error"):
		return resolved
	var node: Node = resolved["node"]
	if not node is Control or not node.is_visible_in_tree() or node.get_global_rect().size.x <= 0 or node.get_global_rect().size.y <= 0:
		return _error(-32602, "INVALID_PARAMS", "Target is not a visible Control")
	if node is BaseButton and node.disabled:
		return _error(-32602, "INVALID_PARAMS", "Target is disabled")
	var center: Vector2 = node.get_global_rect().get_center()
	_inject_mouse(center, true)
	_inject_mouse(center, false)
	return {"result": {"automation_id": params["automation_id"], "x": center.x, "y": center.y}}


func _input_drag(params: Dictionary) -> Dictionary:
	var from_result := _resolve_target({"automation_id": params.get("from_automation_id")})
	var to_result := _resolve_target({"automation_id": params.get("to_automation_id")})
	if from_result.has("error"):
		return from_result
	if to_result.has("error"):
		return to_result
	if not from_result["node"] is Control or not to_result["node"] is Control:
		return _error(-32602, "INVALID_PARAMS", "Drag targets must be Controls")
	if not from_result["node"].is_visible_in_tree() or not to_result["node"].is_visible_in_tree():
		return _error(-32602, "INVALID_PARAMS", "Drag targets must be visible")
	if from_result["node"].get_global_rect().has_area() == false or to_result["node"].get_global_rect().has_area() == false:
		return _error(-32602, "INVALID_PARAMS", "Drag targets must have positive bounds")
	var from_center: Vector2 = from_result["node"].get_global_rect().get_center()
	var to_center: Vector2 = to_result["node"].get_global_rect().get_center()
	_inject_mouse(from_center, true)
	var motion := InputEventMouseMotion.new()
	motion.position = to_center
	motion.global_position = to_center
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	get_viewport().push_input(motion, true)
	_inject_mouse(to_center, false)
	return {"result": {
		"from": {"x": from_center.x, "y": from_center.y},
		"to": {"x": to_center.x, "y": to_center.y},
	}}


func _inject_mouse(position: Vector2, pressed: bool) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = position
	motion.global_position = position
	get_viewport().push_input(motion, true)
	var event := InputEventMouseButton.new()
	event.position = position
	event.global_position = position
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = pressed
	get_viewport().push_input(event, true)


func _screenshot_target(params: Dictionary) -> Dictionary:
	var resolved := _resolve_target(params)
	if resolved.has("error"):
		return resolved
	var node: Node = resolved["node"]
	if not node is Control or not node.is_visible_in_tree():
		return _error(-32602, "INVALID_PARAMS", "Screenshot target must be a visible Control")
	return _screenshot(node)


func _screenshot(node: Variant) -> Dictionary:
	var image := get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		return _error(-32009, "CAPTURE_FAILED", "Viewport image is unavailable")
	if node != null:
		var global_rect: Rect2 = node.get_global_rect()
		var visible_rect := get_viewport().get_visible_rect()
		if visible_rect.size.x <= 0 or visible_rect.size.y <= 0:
			return _error(-32009, "CAPTURE_FAILED", "Viewport has no visible logical region")
		var pixel_scale := Vector2(image.get_size()) / visible_rect.size
		var pixel_start := (global_rect.position - visible_rect.position) * pixel_scale
		var pixel_end := (global_rect.end - visible_rect.position) * pixel_scale
		var capture_position := Vector2i(floori(pixel_start.x), floori(pixel_start.y))
		var capture_end := Vector2i(ceili(pixel_end.x), ceili(pixel_end.y))
		var capture_rect := Rect2i(capture_position, capture_end - capture_position)
		var rect := capture_rect.intersection(Rect2i(Vector2i.ZERO, image.get_size()))
		if rect.size.x <= 0 or rect.size.y <= 0:
			return _error(-32009, "CAPTURE_FAILED", "Target has no visible capture region")
		image = image.get_region(rect)
	var png := image.save_png_to_buffer()
	if png.size() > MAX_SCREENSHOT_BYTES:
		return _error(-32006, "LIMIT_EXCEEDED", "Screenshot exceeds byte limit")
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(png)
	var digest := context.finish().hex_encode()
	return {"result": {
		"data": Marshalls.raw_to_base64(png),
		"bytes": png.size(),
		"sha256": digest,
		"width": image.get_width(),
		"height": image.get_height(),
		"format": "png",
	}}


func _json_depth(value: Variant, depth := 0) -> int:
	if depth > MAX_JSON_DEPTH:
		return depth
	var maximum := depth
	if value is Dictionary:
		for child in value.values():
			maximum = maxi(maximum, _json_depth(child, depth + 1))
	elif value is Array:
		for child in value:
			maximum = maxi(maximum, _json_depth(child, depth + 1))
	return maximum


func _error(code: int, name: String, message: String) -> Dictionary:
	return {"error": {"code": code, "name": name, "message": message}}


func _send_result(request_id: Variant, result: Variant) -> void:
	_send({"jsonrpc": "2.0", "id": request_id, "result": result})


func _send_error(request_id: Variant, code: int, name: String, message: String) -> void:
	_send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "name": name, "message": message}})


func _send(response: Dictionary) -> void:
	if _peer == null:
		return
	var encoded := (JSON.stringify(response) + "\n").to_utf8_buffer()
	if encoded.size() > MAX_RESPONSE_BYTES:
		encoded = (JSON.stringify({"jsonrpc": "2.0", "id": response.get("id"), "error": {"code": -32006, "name": "LIMIT_EXCEEDED", "message": "Response exceeds byte limit"}}) + "\n").to_utf8_buffer()
	if _send_buffer.size() + encoded.size() > MAX_OUTBOUND_BYTES:
		_close_after_response = true
		return
	if _send_buffer.is_empty():
		_send_started_ms = Time.get_ticks_msec()
	_send_buffer.append_array(encoded)


func _flush_outbound() -> void:
	if _peer == null:
		return
	if not _send_buffer.is_empty():
		if Time.get_ticks_msec() - _send_started_ms > OUTBOUND_TIMEOUT_MS:
			_clear_connection()
			return
		var result := _peer.put_partial_data(_send_buffer)
		if result[0] != OK:
			_clear_connection()
			return
		var sent: int = result[1]
		if sent > 0:
			_send_buffer = _send_buffer.slice(sent)
			if _send_buffer.is_empty():
				_send_started_ms = 0
	if _close_after_response and _send_buffer.is_empty():
		_clear_connection()


func _record(request_id: Variant, method: String, outcome: String, started_ms: int) -> void:
	if _transcript_path.is_empty():
		return
	var file := FileAccess.open(_transcript_path, FileAccess.READ_WRITE)
	if file == null:
		file = FileAccess.open(_transcript_path, FileAccess.WRITE)
	if file == null:
		return
	file.seek_end()
	var safe_method := method if _capability_document()["methods"].has(method) or method == "session.hello" else "unknown"
	var record := JSON.stringify({
		"request_id": request_id,
		"method": safe_method,
		"outcome": outcome,
		"duration_ms": Time.get_ticks_msec() - started_ms,
	})
	if file.get_length() + record.to_utf8_buffer().size() + 1 <= MAX_TRANSCRIPT_BYTES:
		file.store_line(record)
	file.close()


func _clear_connection() -> void:
	for pending in _pending_signals.values():
		var node: Node = pending["node"]
		if is_instance_valid(node) and node.is_connected(pending["signal"], pending["callback"]):
			node.disconnect(pending["signal"], pending["callback"])
		_record(pending["id"], "signal.wait", "cancelled", pending["started"])
	_pending_signals.clear()
	_signal_results.clear()
	if _peer != null:
		_peer.disconnect_from_host()
	for action in _pressed_actions:
		Input.action_release(action)
	_pressed_actions.clear()
	for keycode in _pressed_keys:
		var event := InputEventKey.new()
		event.keycode = keycode
		event.pressed = false
		Input.parse_input_event(event)
	_pressed_keys.clear()
	for injected in _joy_axes.values():
		var motion := InputEventJoypadMotion.new()
		motion.device = injected["device"]
		motion.axis = injected["axis"]
		motion.axis_value = 0.0
		Input.parse_input_event(motion)
	_joy_axes.clear()
	for injected in _pressed_joy_buttons.values():
		var button := InputEventJoypadButton.new()
		button.device = injected["device"]
		button.button_index = injected["button"]
		button.pressed = false
		Input.parse_input_event(button)
	_pressed_joy_buttons.clear()
	_peer = null
	_receive_buffer.clear()
	_send_buffer.clear()
	_send_started_ms = 0
	_authenticated = false
	_granted_capabilities.clear()
	_close_after_response = false


func _exit_tree() -> void:
	_clear_connection()
	if _listener != null:
		_listener.stop()
