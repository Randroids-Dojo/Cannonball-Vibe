using Cannonball.Core.Runs;
using Cannonball.Core.Simulation.Vehicle;
using Cannonball.Game.Input;
using Godot;

namespace Cannonball.Game.Vehicle;

public sealed partial class DrivingInputController : Node
{
    private const float ActiveInputEpsilon = 0.001f;

    private readonly DrivingInputConditioner _conditioner = new();
    private readonly Godot.Collections.Dictionary _automationState = new();
    private DrivingInputDevice _lastDevice = DrivingInputDevice.Keyboard;
    private long _activeControllerDevice = -1;
    private bool _suppressUntilNeutral;
    private bool _wasPaused;
    private string _suppressionReason = "none";
    private float _forwardSpeedMetersPerSecond;
    private AssistProfile _activeProfile = AssistProfile.Balanced;

    public ConditionedDrivingInput Current => _conditioner.Current;

    public override void _Ready()
    {
        Name = "DrivingInputController";
        ProcessMode = ProcessModeEnum.Always;
        SetProcessInput(true);
        SetMeta("automation_id", "vehicle.input.conditioner");
        SetMeta("automation_state", _automationState);
        Godot.Input.Singleton.JoyConnectionChanged += OnJoyConnectionChanged;
        _wasPaused = GetTree().Paused;
        UpdateAutomationState(Current, new RawDrivingInput());
    }

    public override void _ExitTree()
    {
        Godot.Input.Singleton.JoyConnectionChanged -= OnJoyConnectionChanged;
    }

    public override void _Process(double _delta)
    {
        var paused = GetTree().Paused;
        if (paused && !_wasPaused)
        {
            ClearAndSuppress("pause");
        }
        _wasPaused = paused;
    }

    public override void _Input(InputEvent @event)
    {
        if (@event is InputEventJoypadButton { Pressed: true } button)
        {
            SelectController(button.Device);
        }
        else if (@event is InputEventJoypadMotion motion && IsMeaningfulControllerMotion(motion))
        {
            SelectController(motion.Device);
        }
        else if (@event is InputEventKey { Pressed: true })
        {
            _lastDevice = DrivingInputDevice.Keyboard;
        }
    }

    public override void _Notification(int what)
    {
        if (what == NotificationApplicationFocusOut)
        {
            ClearAndSuppress("focus_loss");
        }
    }

    public DriveInputState Read(
        float forwardSpeedMetersPerSecond,
        double deltaSeconds,
        AssistProfile profile)
    {
        _forwardSpeedMetersPerSecond = forwardSpeedMetersPerSecond;
        _activeProfile = profile;
        var raw = ReadRaw();
        if (_suppressUntilNeutral)
        {
            if (IsNeutral(raw))
            {
                _suppressUntilNeutral = false;
                _suppressionReason = "none";
            }
            else
            {
                var suppressed = _conditioner.Step(
                    raw,
                    forwardSpeedMetersPerSecond,
                    deltaSeconds,
                    profile,
                    inputEnabled: false);
                UpdateAutomationState(suppressed, raw);
                return ToDriveInput(suppressed);
            }
        }

        var conditioned = _conditioner.Step(
            raw,
            forwardSpeedMetersPerSecond,
            deltaSeconds,
            profile);
        UpdateAutomationState(conditioned, raw);
        return ToDriveInput(conditioned);
    }

    public void ClearAndSuppress(string reason)
    {
        _conditioner.Reset();
        _suppressUntilNeutral = true;
        _suppressionReason = reason;
        UpdateAutomationState(Current, new RawDrivingInput());
    }

    private RawDrivingInput ReadRaw()
    {
        var keyboard = new RawDrivingInput(
            Godot.Input.GetActionStrength("accelerate"),
            Godot.Input.GetActionStrength("brake"),
            Godot.Input.GetActionStrength("reverse"),
            Godot.Input.GetActionStrength("handbrake"),
            Godot.Input.GetAxis("steer_left", "steer_right"),
            DrivingInputDevice.Keyboard,
            Godot.Input.IsActionJustPressed("reset_vehicle"));
        var controller = new RawDrivingInput(
            Godot.Input.GetActionStrength("accelerate_controller"),
            Godot.Input.GetActionStrength("brake_controller"),
            Godot.Input.GetActionStrength("reverse_controller"),
            Godot.Input.GetActionStrength("handbrake_controller"),
            Godot.Input.GetAxis("steer_left_controller", "steer_right_controller"),
            DrivingInputDevice.Controller,
            Godot.Input.IsActionJustPressed("reset_vehicle_controller"));
        var keyboardActivity = Activity(keyboard);
        var controllerActivity = ControllerActivity(
            controller,
            DrivingInputTuning.For(_activeProfile).ControllerDeadzone);
        if (controllerActivity > ActiveInputEpsilon && keyboardActivity <= ActiveInputEpsilon)
        {
            _lastDevice = DrivingInputDevice.Controller;
        }
        else if (keyboardActivity > ActiveInputEpsilon && controllerActivity <= ActiveInputEpsilon)
        {
            _lastDevice = DrivingInputDevice.Keyboard;
        }

        return _lastDevice == DrivingInputDevice.Controller
            ? controller
            : keyboard;
    }

    private void OnJoyConnectionChanged(long device, bool connected)
    {
        if (!connected &&
            _lastDevice == DrivingInputDevice.Controller &&
            device == _activeControllerDevice)
        {
            ReleaseControllerActions();
            _activeControllerDevice = -1;
            ClearAndSuppress("controller_disconnect");
        }
    }

    private void UpdateAutomationState(
        ConditionedDrivingInput conditioned,
        RawDrivingInput raw)
    {
        var tuning = DrivingInputTuning.For(_activeProfile);
        _automationState["device_source"] = conditioned.Device.ToString().ToLowerInvariant();
        _automationState["active_controller_device"] = _activeControllerDevice;
        _automationState["active_profile"] = _activeProfile.ToString().ToLowerInvariant();
        _automationState["keyboard_rise_per_second"] = tuning.KeyboardRisePerSecond;
        _automationState["controller_deadzone"] = tuning.ControllerDeadzone;
        _automationState["controller_exponent"] = tuning.ControllerExponent;
        _automationState["controller_rate_per_second"] = tuning.ControllerRatePerSecond;
        _automationState["high_speed_min_authority"] =
            tuning.MinimumHighSpeedSteeringAuthority;
        _automationState["raw_throttle"] = raw.Throttle;
        _automationState["raw_service_brake"] = raw.ServiceBrake;
        _automationState["raw_reverse"] = raw.Reverse;
        _automationState["raw_handbrake"] = raw.Handbrake;
        _automationState["raw_steering"] = conditioned.RawSteering;
        _automationState["conditioned_throttle"] = conditioned.Throttle;
        _automationState["conditioned_service_brake"] = conditioned.ServiceBrake;
        _automationState["conditioned_reverse"] = conditioned.Reverse;
        _automationState["conditioned_handbrake"] = conditioned.Handbrake;
        _automationState["conditioned_steering"] = conditioned.Steering;
        _automationState["steering_target"] = conditioned.SteeringTarget;
        _automationState["steering_authority"] = conditioned.SteeringAuthority;
        _automationState["response_time_ms"] = conditioned.SteeringResponseSeconds * 1_000;
        _automationState["steering_saturated"] = conditioned.SteeringSaturated;
        _automationState["stationary_hold"] = conditioned.StationaryHold;
        _automationState["forward_speed_mps"] = _forwardSpeedMetersPerSecond;
        _automationState["input_suppressed"] = _suppressUntilNeutral;
        _automationState["suppression_reason"] = _suppressionReason;
    }

    private static float Activity(RawDrivingInput input) => (float)Math.Max(
        input.Reset ? 1 : 0,
        Math.Max(
            Math.Abs(input.Steering),
            Math.Max(
                Math.Max(input.Throttle, input.ServiceBrake),
                Math.Max(input.Reverse, input.Handbrake))));

    private static float ControllerActivity(RawDrivingInput input, double deadzone) =>
        (float)Math.Max(
            input.Reset ? 1 : 0,
            Math.Max(
                DeadzoneActivity(input.Steering, deadzone),
                Math.Max(
                    Math.Max(
                        DeadzoneActivity(input.Throttle, deadzone),
                        DeadzoneActivity(input.ServiceBrake, deadzone)),
                    Math.Max(input.Reverse, input.Handbrake))));

    private static double DeadzoneActivity(double value, double deadzone) =>
        Math.Abs(value) > deadzone ? Math.Abs(value) : 0;

    private bool IsMeaningfulControllerMotion(InputEventJoypadMotion motion)
    {
        var deadzone = DrivingInputTuning.For(_activeProfile).ControllerDeadzone;
        return motion.Axis switch
        {
            JoyAxis.LeftX => Math.Abs(motion.AxisValue) > deadzone,
            JoyAxis.TriggerLeft or JoyAxis.TriggerRight => motion.AxisValue > deadzone,
            _ => false,
        };
    }

    private void SelectController(long device)
    {
        _lastDevice = DrivingInputDevice.Controller;
        _activeControllerDevice = device;
    }

    private static bool IsNeutral(RawDrivingInput input) => Activity(input) <= ActiveInputEpsilon;

    private static void ReleaseControllerActions()
    {
        string[] actions =
        [
            "accelerate_controller",
            "brake_controller",
            "reverse_controller",
            "handbrake_controller",
            "steer_left_controller",
            "steer_right_controller",
            "reset_vehicle_controller",
        ];
        foreach (var action in actions)
        {
            Godot.Input.ActionRelease(action);
        }
    }

    private static DriveInputState ToDriveInput(ConditionedDrivingInput input) => new(
        (float)input.Throttle,
        (float)input.ServiceBrake,
        (float)input.Reverse,
        (float)input.Handbrake,
        (float)input.Steering,
        input.StationaryHold,
        input.Reset);
}
