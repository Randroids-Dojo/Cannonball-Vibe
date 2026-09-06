using Cannonball.Game.Camera;
using Cannonball.Game.Input;
using Godot;

namespace Cannonball.Game.Automation;

/// <summary>
/// Constant-speed display-motion probe. A low physics rate exposes a camera
/// following raw physics poses even when every rendered frame arrives on time.
/// </summary>
public sealed partial class CameraInterpolationProbe : Node3D
{
    private ChaseCameraRig _rig = null!;
    private CockpitCameraRig _cockpit = null!;
    private double _elapsed;
    private double _minimum = double.PositiveInfinity;
    private double _maximum = double.NegativeInfinity;
    private double _cockpitMinimum = double.PositiveInfinity;
    private double _cockpitMaximum = double.NegativeInfinity;
    private int _samples;

    public override void _Ready()
    {
        GameInputMap.Configure();
        Engine.PhysicsTicksPerSecond = 20;
        ProcessPriority = 100; // Observe after the real camera's _Process.
        _rig = new ChaseCameraRig { Target = this };
        AddChild(_rig);
        _cockpit = new CockpitCameraRig();
        AddChild(_cockpit);
    }

    public override void _PhysicsProcess(double delta)
    {
        Position += Vector3.Forward * (float)(50 * delta);
    }

    public override void _Process(double delta)
    {
        _elapsed += delta;
        if (_elapsed < 3)
        {
            return;
        }
        var relativeZ = _rig.Camera.GetCameraTransform().Origin.Z -
            GetGlobalTransformInterpolated().Origin.Z;
        _minimum = Math.Min(_minimum, relativeZ);
        _maximum = Math.Max(_maximum, relativeZ);
        var cockpitRelativeZ = _cockpit.Camera.GetCameraTransform().Origin.Z -
            GetGlobalTransformInterpolated().Origin.Z;
        _cockpitMinimum = Math.Min(_cockpitMinimum, cockpitRelativeZ);
        _cockpitMaximum = Math.Max(_cockpitMaximum, cockpitRelativeZ);
        _samples++;
        if (_elapsed < 6)
        {
            return;
        }
        var oscillation = _maximum - _minimum;
        var cockpitOscillation = _cockpitMaximum - _cockpitMinimum;
        // At 50 m/s each 20 Hz tick advances 2.5 m. A correctly aligned
        // render-time follower settles to a constant offset within 2 cm.
        var passed = _samples >= 300 && oscillation <= 0.02 && cockpitOscillation <= 0.02;
        GD.Print($"CANNONBALL_CAMERA_INTERPOLATION_{(passed ? "OK" : "FAILED")} " +
            $"samples={_samples} relative_oscillation_m={oscillation:F6} " +
            $"cockpit_oscillation_m={cockpitOscillation:F6} " +
            "limit_m=0.020 physics_hz=20 render_hz=120");
        GetTree().Quit(passed ? 0 : 1);
    }
}
