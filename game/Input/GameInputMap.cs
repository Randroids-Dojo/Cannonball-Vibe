using Godot;

namespace Cannonball.Game.Input;

public static class GameInputMap
{
    // Godot converts strings to finalizable native wrappers. Intern once, then
    // reuse these handles in input polling and camera updates.
    public static readonly StringName Accelerate = "accelerate";
    public static readonly StringName Brake = "brake";
    public static readonly StringName Reverse = "reverse";
    public static readonly StringName Handbrake = "handbrake";
    public static readonly StringName SteerLeft = "steer_left";
    public static readonly StringName SteerRight = "steer_right";
    public static readonly StringName ResetVehicle = "reset_vehicle";
    public static readonly StringName SuspendRun = "suspend_run";
    public static readonly StringName CycleAssist = "cycle_assist";
    public static readonly StringName ToggleCamera = "toggle_camera";
    public static readonly StringName LookBehind = "look_behind";
    public static readonly StringName CameraLookLeft = "camera_look_left";
    public static readonly StringName CameraLookRight = "camera_look_right";
    public static readonly StringName CameraLookUp = "camera_look_up";
    public static readonly StringName CameraLookDown = "camera_look_down";
    public static readonly StringName ToggleTripMap = "toggle_trip_map";
    public static readonly StringName TripMapPanLeft = "trip_map_pan_left";
    public static readonly StringName TripMapPanRight = "trip_map_pan_right";
    public static readonly StringName TripMapPanUp = "trip_map_pan_up";
    public static readonly StringName TripMapPanDown = "trip_map_pan_down";
    public static readonly StringName TripMapZoomIn = "trip_map_zoom_in";
    public static readonly StringName TripMapZoomOut = "trip_map_zoom_out";
    public static readonly StringName TripMapRecenter = "trip_map_recenter";
    public static readonly StringName TripMapPrevious = "trip_map_previous";
    public static readonly StringName TripMapNext = "trip_map_next";
    public static readonly StringName AccelerateController = "accelerate_controller";
    public static readonly StringName BrakeController = "brake_controller";
    public static readonly StringName SteerLeftController = "steer_left_controller";
    public static readonly StringName SteerRightController = "steer_right_controller";
    public static readonly StringName ReverseController = "reverse_controller";
    public static readonly StringName HandbrakeController = "handbrake_controller";
    public static readonly StringName ResetVehicleController = "reset_vehicle_controller";
    public static readonly StringName UiAccept = "ui_accept";
    public static readonly StringName UiCancel = "ui_cancel";
    public static readonly StringName UiUp = "ui_up";
    public static readonly StringName UiDown = "ui_down";
    public static readonly StringName UiLeft = "ui_left";
    public static readonly StringName UiRight = "ui_right";
    public static readonly StringName PauseMenu = "pause_menu";

    public static void Configure()
    {
        AddKeyAction(Accelerate, Key.W);
        AddKeyAction(Brake, Key.S);
        AddKeyAction(Reverse, Key.Q);
        AddKeyAction(Handbrake, Key.Space);
        AddKeyAction(SteerLeft, Key.A);
        AddKeyAction(SteerRight, Key.D);
        AddKeyAction(ResetVehicle, Key.R);
        AddKeyAction(SuspendRun, Key.F5);
        AddKeyAction(CycleAssist, Key.Tab);
        AddKeyAction(ToggleCamera, Key.V);
        AddKeyAction(LookBehind, Key.B);
        AddKeyAction(CameraLookLeft, Key.J);
        AddKeyAction(CameraLookRight, Key.L);
        AddKeyAction(CameraLookUp, Key.I);
        AddKeyAction(CameraLookDown, Key.K);
        AddKeyAction(ToggleTripMap, Key.M);
        AddKeyAction(TripMapPanLeft, Key.Left);
        AddKeyAction(TripMapPanRight, Key.Right);
        AddKeyAction(TripMapPanUp, Key.Up);
        AddKeyAction(TripMapPanDown, Key.Down);
        AddKeyAction(TripMapZoomIn, Key.Equal);
        AddKeyAction(TripMapZoomOut, Key.Minus);
        AddKeyAction(TripMapRecenter, Key.C);
        AddKeyAction(TripMapPrevious, Key.Pageup);
        AddKeyAction(TripMapNext, Key.Pagedown);
        AddKeyAction(PauseMenu, Key.Escape);

        // Driving follows the de-facto Xbox/Steam Input gamepad layout.
        AddJoyAxisAction(AccelerateController, JoyAxis.TriggerRight, 1);
        AddJoyAxisAction(BrakeController, JoyAxis.TriggerLeft, 1);
        AddJoyAxisAction(SteerLeftController, JoyAxis.LeftX, -1);
        AddJoyAxisAction(SteerRightController, JoyAxis.LeftX, 1);
        AddJoyButtonAction(ReverseController, JoyButton.B);
        AddJoyButtonAction(HandbrakeController, JoyButton.X);
        AddJoyButtonAction(ResetVehicleController, JoyButton.Y);
        AddJoyButtonAction(ToggleCamera, JoyButton.RightStick);
        AddJoyButtonAction(LookBehind, JoyButton.LeftShoulder);
        AddJoyAxisAction(CameraLookLeft, JoyAxis.RightX, -1);
        AddJoyAxisAction(CameraLookRight, JoyAxis.RightX, 1);
        AddJoyAxisAction(CameraLookUp, JoyAxis.RightY, -1);
        AddJoyAxisAction(CameraLookDown, JoyAxis.RightY, 1);
        AddJoyButtonAction(ToggleTripMap, JoyButton.Back);
        AddJoyButtonAction(PauseMenu, JoyButton.Start);

        // The trip map uses the right stick and shoulders so its focused buttons
        // remain free to use the standard D-pad/left-stick and A/B UI contract.
        AddJoyAxisAction(TripMapPanLeft, JoyAxis.RightX, -1);
        AddJoyAxisAction(TripMapPanRight, JoyAxis.RightX, 1);
        AddJoyAxisAction(TripMapPanUp, JoyAxis.RightY, -1);
        AddJoyAxisAction(TripMapPanDown, JoyAxis.RightY, 1);
        AddJoyAxisAction(TripMapZoomIn, JoyAxis.TriggerRight, 1);
        AddJoyAxisAction(TripMapZoomOut, JoyAxis.TriggerLeft, 1);
        AddJoyButtonAction(TripMapRecenter, JoyButton.Y);
        AddJoyButtonAction(TripMapPrevious, JoyButton.LeftShoulder);
        AddJoyButtonAction(TripMapNext, JoyButton.RightShoulder);

        AddJoyButtonAction(UiAccept, JoyButton.A);
        AddJoyButtonAction(UiCancel, JoyButton.B);
        AddJoyButtonAction(UiUp, JoyButton.DpadUp);
        AddJoyButtonAction(UiDown, JoyButton.DpadDown);
        AddJoyButtonAction(UiLeft, JoyButton.DpadLeft);
        AddJoyButtonAction(UiRight, JoyButton.DpadRight);
        AddJoyAxisAction(UiUp, JoyAxis.LeftY, -1, 0.5f);
        AddJoyAxisAction(UiDown, JoyAxis.LeftY, 1, 0.5f);
        AddJoyAxisAction(UiLeft, JoyAxis.LeftX, -1, 0.5f);
        AddJoyAxisAction(UiRight, JoyAxis.LeftX, 1, 0.5f);
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
