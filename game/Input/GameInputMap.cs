using Godot;

namespace Cannonball.Game.Input;

public static class GameInputMap
{
    public const string PauseMenu = "pause_menu";

    public static void Configure()
    {
        AddKeyAction("accelerate", Key.W);
        AddKeyAction("brake", Key.S);
        AddKeyAction("reverse", Key.Q);
        AddKeyAction("handbrake", Key.Space);
        AddKeyAction("steer_left", Key.A);
        AddKeyAction("steer_right", Key.D);
        AddKeyAction("reset_vehicle", Key.R);
        AddKeyAction("suspend_run", Key.F5);
        AddKeyAction("cycle_assist", Key.Tab);
        AddKeyAction("toggle_camera", Key.V);
        AddKeyAction("look_behind", Key.B);
        AddKeyAction("camera_look_left", Key.J);
        AddKeyAction("camera_look_right", Key.L);
        AddKeyAction("camera_look_up", Key.I);
        AddKeyAction("camera_look_down", Key.K);
        AddKeyAction("toggle_trip_map", Key.M);
        AddKeyAction("trip_map_pan_left", Key.Left);
        AddKeyAction("trip_map_pan_right", Key.Right);
        AddKeyAction("trip_map_pan_up", Key.Up);
        AddKeyAction("trip_map_pan_down", Key.Down);
        AddKeyAction("trip_map_zoom_in", Key.Equal);
        AddKeyAction("trip_map_zoom_out", Key.Minus);
        AddKeyAction("trip_map_recenter", Key.C);
        AddKeyAction("trip_map_previous", Key.Pageup);
        AddKeyAction("trip_map_next", Key.Pagedown);
        AddKeyAction(PauseMenu, Key.Escape);

        // Driving follows the de-facto Xbox/Steam Input gamepad layout.
        AddJoyAxisAction("accelerate_controller", JoyAxis.TriggerRight, 1);
        AddJoyAxisAction("brake_controller", JoyAxis.TriggerLeft, 1);
        AddJoyAxisAction("steer_left_controller", JoyAxis.LeftX, -1);
        AddJoyAxisAction("steer_right_controller", JoyAxis.LeftX, 1);
        AddJoyButtonAction("reverse_controller", JoyButton.B);
        AddJoyButtonAction("handbrake_controller", JoyButton.X);
        AddJoyButtonAction("reset_vehicle_controller", JoyButton.Y);
        AddJoyButtonAction("toggle_camera", JoyButton.RightStick);
        AddJoyButtonAction("look_behind", JoyButton.LeftShoulder);
        AddJoyAxisAction("camera_look_left", JoyAxis.RightX, -1);
        AddJoyAxisAction("camera_look_right", JoyAxis.RightX, 1);
        AddJoyAxisAction("camera_look_up", JoyAxis.RightY, -1);
        AddJoyAxisAction("camera_look_down", JoyAxis.RightY, 1);
        AddJoyButtonAction("toggle_trip_map", JoyButton.Back);
        AddJoyButtonAction(PauseMenu, JoyButton.Start);

        // The trip map uses the right stick and shoulders so its focused buttons
        // remain free to use the standard D-pad/left-stick and A/B UI contract.
        AddJoyAxisAction("trip_map_pan_left", JoyAxis.RightX, -1);
        AddJoyAxisAction("trip_map_pan_right", JoyAxis.RightX, 1);
        AddJoyAxisAction("trip_map_pan_up", JoyAxis.RightY, -1);
        AddJoyAxisAction("trip_map_pan_down", JoyAxis.RightY, 1);
        AddJoyAxisAction("trip_map_zoom_in", JoyAxis.TriggerRight, 1);
        AddJoyAxisAction("trip_map_zoom_out", JoyAxis.TriggerLeft, 1);
        AddJoyButtonAction("trip_map_recenter", JoyButton.Y);
        AddJoyButtonAction("trip_map_previous", JoyButton.LeftShoulder);
        AddJoyButtonAction("trip_map_next", JoyButton.RightShoulder);

        AddJoyButtonAction("ui_accept", JoyButton.A);
        AddJoyButtonAction("ui_cancel", JoyButton.B);
        AddJoyButtonAction("ui_up", JoyButton.DpadUp);
        AddJoyButtonAction("ui_down", JoyButton.DpadDown);
        AddJoyButtonAction("ui_left", JoyButton.DpadLeft);
        AddJoyButtonAction("ui_right", JoyButton.DpadRight);
        AddJoyAxisAction("ui_up", JoyAxis.LeftY, -1, 0.5f);
        AddJoyAxisAction("ui_down", JoyAxis.LeftY, 1, 0.5f);
        AddJoyAxisAction("ui_left", JoyAxis.LeftX, -1, 0.5f);
        AddJoyAxisAction("ui_right", JoyAxis.LeftX, 1, 0.5f);
    }

    private static void AddKeyAction(StringName action, Key key)
    {
        EnsureAction(action, 0.12f);
        using var inputEvent = new InputEventKey { PhysicalKeycode = key };
        AddEventOnce(action, inputEvent);
    }

    private static void AddJoyAxisAction(
        StringName action,
        JoyAxis axis,
        float axisValue,
        float deadzone = 0.0f)
    {
        EnsureAction(action, deadzone);
        using var inputEvent = new InputEventJoypadMotion
        {
            Device = -1,
            Axis = axis,
            AxisValue = axisValue,
        };
        AddEventOnce(action, inputEvent);
    }

    private static void AddJoyButtonAction(StringName action, JoyButton button)
    {
        EnsureAction(action, 0.12f);
        using var inputEvent = new InputEventJoypadButton
        {
            Device = -1,
            ButtonIndex = button,
        };
        AddEventOnce(action, inputEvent);
    }

    private static void EnsureAction(StringName action, float deadzone)
    {
        if (!InputMap.HasAction(action))
        {
            InputMap.AddAction(action, deadzone);
        }
    }

    private static void AddEventOnce(StringName action, InputEvent candidate)
    {
        if (!InputMap.ActionHasEvent(action, candidate))
        {
            InputMap.ActionAddEvent(action, candidate);
        }
    }
}
