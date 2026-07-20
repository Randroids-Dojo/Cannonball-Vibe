using Cannonball.Core.Runs;

namespace Cannonball.Core.Simulation.Vehicle;

public enum DrivingInputDevice
{
    None,
    Keyboard,
    Controller,
}

public readonly record struct RawDrivingInput(
    double Throttle,
    double ServiceBrake,
    double Reverse,
    double Handbrake,
    double Steering,
    DrivingInputDevice Device,
    bool Reset = false);

public readonly record struct ConditionedDrivingInput(
    double Throttle,
    double ServiceBrake,
    double Reverse,
    double Handbrake,
    double Steering,
    bool StationaryHold,
    bool Reset,
    DrivingInputDevice Device,
    AssistProfile Profile,
    double RawSteering,
    double SteeringTarget,
    double SteeringAuthority,
    double SteeringResponseSeconds,
    bool SteeringSaturated);

public sealed record DrivingInputTuning(
    double KeyboardRisePerSecond,
    double KeyboardReturnPerSecond,
    double KeyboardDirectionChangePerSecond,
    double ControllerDeadzone,
    double ControllerExponent,
    double ControllerRatePerSecond,
    double HighSpeedStartMetersPerSecond,
    double HighSpeedFullMetersPerSecond,
    double MinimumHighSpeedSteeringAuthority,
    double ThrottleRatePerSecond,
    double BrakeRatePerSecond,
    double StationaryHoldSpeedMetersPerSecond)
{
    private static readonly DrivingInputTuning Accessible = new(
        2.4, 4.0, 3.2,
        0.16, 1.60, 3.0,
        24, 90, 0.26,
        3.5, 6.0, 0.45);
    private static readonly DrivingInputTuning Balanced = new(
        3.2, 4.8, 4.0,
        0.12, 1.35, 4.5,
        28, 90, 0.31,
        5.0, 8.0, 0.35);
    private static readonly DrivingInputTuning Raw = new(
        5.5, 7.0, 6.5,
        0.08, 1.00, 8.0,
        32, 90, 0.40,
        8.0, 10.0, 0.25);

    public static DrivingInputTuning For(AssistProfile profile) => profile switch
    {
        AssistProfile.Accessible => Accessible,
        AssistProfile.Raw => Raw,
        _ => Balanced,
    };
}

public sealed class DrivingInputConditioner
{
    private const double NeutralEpsilon = 0.0001;

    private double _steering;
    private double _throttle;
    private double _serviceBrake;
    private double _reverse;
    private double _handbrake;
    private double _steeringResponseSeconds;

    public ConditionedDrivingInput Current { get; private set; }

    public ConditionedDrivingInput Step(
        RawDrivingInput raw,
        double forwardSpeedMetersPerSecond,
        double deltaSeconds,
        AssistProfile profile,
        bool inputEnabled = true)
    {
        if (!double.IsFinite(forwardSpeedMetersPerSecond))
        {
            throw new ArgumentOutOfRangeException(nameof(forwardSpeedMetersPerSecond));
        }
        if (!double.IsFinite(deltaSeconds) || deltaSeconds < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(deltaSeconds));
        }

        var tuning = DrivingInputTuning.For(profile);
        var delta = Math.Min(deltaSeconds, 0.1);
        if (!inputEnabled)
        {
            Reset();
            Current = Empty(profile);
            return Current;
        }

        var rawSteering = ClampSigned(raw.Steering);
        var shapedSteering = raw.Device == DrivingInputDevice.Controller
            ? ShapeControllerAxis(rawSteering, tuning.ControllerDeadzone, tuning.ControllerExponent)
            : rawSteering;
        var speedRatio = SmoothStep(
            tuning.HighSpeedStartMetersPerSecond,
            tuning.HighSpeedFullMetersPerSecond,
            Math.Abs(forwardSpeedMetersPerSecond));
        var steeringAuthority = Lerp(1, tuning.MinimumHighSpeedSteeringAuthority, speedRatio);
        var steeringTarget = shapedSteering * steeringAuthority;
        var steeringRate = SteeringRate(steeringTarget, tuning, raw.Device);
        _steering = MoveTowards(_steering, steeringTarget, steeringRate * delta);
        _steeringResponseSeconds = Math.Abs(_steering - steeringTarget) > 0.005
            ? _steeringResponseSeconds + delta
            : 0;

        var throttleTarget = ClampUnit(raw.Throttle);
        var reverseTarget = ClampUnit(raw.Reverse);
        var serviceBrakeTarget = ClampUnit(raw.ServiceBrake);
        var handbrakeTarget = ClampUnit(raw.Handbrake);
        ResolveContradictoryPropulsion(
            ref throttleTarget,
            ref reverseTarget,
            serviceBrakeTarget,
            handbrakeTarget);

        if (serviceBrakeTarget > NeutralEpsilon || handbrakeTarget > NeutralEpsilon)
        {
            _throttle = 0;
            _reverse = 0;
        }
        else
        {
            _throttle = MoveTowards(_throttle, throttleTarget, tuning.ThrottleRatePerSecond * delta);
            _reverse = MoveTowards(_reverse, reverseTarget, tuning.ThrottleRatePerSecond * delta);
        }
        _serviceBrake = MoveTowards(
            _serviceBrake,
            serviceBrakeTarget,
            tuning.BrakeRatePerSecond * delta);
        _handbrake = MoveTowards(_handbrake, handbrakeTarget, tuning.BrakeRatePerSecond * delta);

        var stationaryHold = Math.Abs(forwardSpeedMetersPerSecond) <=
                tuning.StationaryHoldSpeedMetersPerSecond &&
            _throttle <= NeutralEpsilon &&
            _reverse <= NeutralEpsilon;
        Current = new ConditionedDrivingInput(
            _throttle,
            _serviceBrake,
            _reverse,
            _handbrake,
            _steering,
            stationaryHold,
            raw.Reset,
            raw.Device,
            profile,
            rawSteering,
            steeringTarget,
            steeringAuthority,
            _steeringResponseSeconds,
            Math.Abs(shapedSteering) >= 0.999 &&
                Math.Abs(_steering - steeringTarget) <= 0.005);
        return Current;
    }

    public void Reset()
    {
        _steering = 0;
        _throttle = 0;
        _serviceBrake = 0;
        _reverse = 0;
        _handbrake = 0;
        _steeringResponseSeconds = 0;
        Current = default;
    }

    private double SteeringRate(
        double target,
        DrivingInputTuning tuning,
        DrivingInputDevice device)
    {
        var rate = Math.Sign(target) != 0 &&
                Math.Sign(_steering) != 0 &&
                Math.Sign(target) != Math.Sign(_steering)
            ? tuning.KeyboardDirectionChangePerSecond
            : Math.Abs(target) > Math.Abs(_steering)
                ? tuning.KeyboardRisePerSecond
                : tuning.KeyboardReturnPerSecond;
        return device == DrivingInputDevice.Controller
            ? Math.Min(rate, tuning.ControllerRatePerSecond)
            : rate;
    }

    private static double ShapeControllerAxis(double value, double deadzone, double exponent)
    {
        var magnitude = Math.Abs(value);
        if (magnitude <= deadzone)
        {
            return 0;
        }
        var normalized = (magnitude - deadzone) / (1 - deadzone);
        return Math.CopySign(Math.Pow(normalized, exponent), value);
    }

    private static void ResolveContradictoryPropulsion(
        ref double throttle,
        ref double reverse,
        double serviceBrake,
        double handbrake)
    {
        if (serviceBrake > NeutralEpsilon || handbrake > NeutralEpsilon)
        {
            throttle = 0;
            reverse = 0;
            return;
        }
        if (throttle > reverse)
        {
            reverse = 0;
        }
        else if (reverse > throttle)
        {
            throttle = 0;
        }
        else
        {
            throttle = 0;
            reverse = 0;
        }
    }

    private static ConditionedDrivingInput Empty(AssistProfile profile) => new(
        0, 0, 0, 0, 0,
        true, false, DrivingInputDevice.None, profile,
        0, 0, 1, 0, false);

    private static double ClampUnit(double value) =>
        double.IsFinite(value) ? Math.Clamp(value, 0, 1) : 0;

    private static double ClampSigned(double value) =>
        double.IsFinite(value) ? Math.Clamp(value, -1, 1) : 0;

    private static double MoveTowards(double value, double target, double maximumDelta)
    {
        var moved = Math.Abs(target - value) <= maximumDelta
            ? target
            : value + Math.CopySign(maximumDelta, target - value);
        return Math.Abs(target) <= NeutralEpsilon && Math.Abs(moved) <= NeutralEpsilon
            ? 0
            : moved;
    }

    private static double SmoothStep(double start, double end, double value)
    {
        var ratio = Math.Clamp((value - start) / (end - start), 0, 1);
        return ratio * ratio * (3 - 2 * ratio);
    }

    private static double Lerp(double from, double to, double weight) =>
        from + (to - from) * weight;
}
