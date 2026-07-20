using Godot;

namespace Cannonball.Game.Camera;

public sealed partial class CockpitCameraRig : Node3D
{
    private readonly Godot.Collections.Dictionary _automationState = new();
    private float _lookYawRadians;
    private float _lookPitchRadians;
    private Camera3D _camera = null!;

    public Camera3D Camera => _camera;
    public bool IsActive => _camera.Current;

    [Export(PropertyHint.Range, "0,15,0.5")]
    public float MaximumStabilizationDegrees { get; set; } = 6;

    [Export(PropertyHint.Range, "15,120,1")]
    public float MaximumLookYawDegrees { get; set; } = 72;

    [Export(PropertyHint.Range, "5,45,1")]
    public float MaximumLookPitchDegrees { get; set; } = 24;

    [Export(PropertyHint.Range, "30,180,1")]
    public float LookSpeedDegreesPerSecond { get; set; } = 95;

    [Export(PropertyHint.Range, "30,180,1")]
    public float RecenterSpeedDegreesPerSecond { get; set; } = 70;

    public override void _Ready()
    {
        Name = "CockpitCameraRig";
        _camera = new Camera3D
        {
            Name = "CockpitCamera",
            Current = false,
            Fov = 72,
            Near = 0.08f,
            Position = new Vector3(0, 0.70f, -0.42f),
        };
        AddChild(_camera);
        SetMeta("automation_id", "camera.cockpit.view");
        SetMeta("automation_state", _automationState);
        UpdateAutomationState(0, 0);
    }

    public override void _Process(double delta)
    {
        var yawInput = Godot.Input.GetActionStrength("camera_look_right") -
            Godot.Input.GetActionStrength("camera_look_left");
        var pitchInput = Godot.Input.GetActionStrength("camera_look_down") -
            Godot.Input.GetActionStrength("camera_look_up");
        var step = Mathf.DegToRad(LookSpeedDegreesPerSecond) * (float)Math.Max(0, delta);
        if (Math.Abs(yawInput) > 0.001f)
        {
            _lookYawRadians = Mathf.Clamp(
                _lookYawRadians + yawInput * step,
                -Mathf.DegToRad(MaximumLookYawDegrees),
                Mathf.DegToRad(MaximumLookYawDegrees));
        }
        else
        {
            _lookYawRadians = Mathf.MoveToward(
                _lookYawRadians,
                0,
                Mathf.DegToRad(RecenterSpeedDegreesPerSecond) * (float)Math.Max(0, delta));
        }
        if (Math.Abs(pitchInput) > 0.001f)
        {
            _lookPitchRadians = Mathf.Clamp(
                _lookPitchRadians + pitchInput * step,
                -Mathf.DegToRad(MaximumLookPitchDegrees),
                Mathf.DegToRad(MaximumLookPitchDegrees));
        }
        else
        {
            _lookPitchRadians = Mathf.MoveToward(
                _lookPitchRadians,
                0,
                Mathf.DegToRad(RecenterSpeedDegreesPerSecond) * (float)Math.Max(0, delta));
        }

        var parent = GetParentOrNull<Node3D>();
        var parentEuler = parent?.GlobalBasis.GetEuler() ?? Vector3.Zero;
        var maximumCorrection = Mathf.DegToRad(MaximumStabilizationDegrees);
        var pitchCorrection = -Mathf.Clamp(
            Mathf.Wrap(parentEuler.X, -Mathf.Pi, Mathf.Pi),
            -maximumCorrection,
            maximumCorrection);
        var rollCorrection = -Mathf.Clamp(
            Mathf.Wrap(parentEuler.Z, -Mathf.Pi, Mathf.Pi),
            -maximumCorrection,
            maximumCorrection);
        Rotation = new Vector3(
            _lookPitchRadians + pitchCorrection,
            _lookYawRadians,
            rollCorrection);
        UpdateAutomationState(pitchCorrection, rollCorrection);
    }

    public void SetActive(bool active)
    {
        _camera.Current = active;
        _automationState["active"] = active;
    }

    public CockpitCameraSnapshot CaptureSnapshot()
    {
        var right = _camera.GlobalBasis.X.Normalized();
        var horizonRoll = Mathf.RadToDeg(Mathf.Asin(
            Mathf.Clamp(Math.Abs(right.Dot(Vector3.Up)), 0, 1)));
        return new CockpitCameraSnapshot(
            _camera.Current,
            !TopLevel && GetParentOrNull<Node3D>() is not null,
            Mathf.RadToDeg(_lookYawRadians),
            Mathf.RadToDeg(_lookPitchRadians),
            horizonRoll,
            RotationDegrees.X - Mathf.RadToDeg(_lookPitchRadians),
            RotationDegrees.Z);
    }

    private void UpdateAutomationState(float pitchCorrection, float rollCorrection)
    {
        var snapshot = CaptureSnapshot();
        _automationState["active"] = snapshot.Active;
        _automationState["mode"] = "cockpit";
        _automationState["vehicle_local"] = snapshot.VehicleLocal;
        _automationState["look_yaw_degrees"] = snapshot.LookYawDegrees;
        _automationState["look_pitch_degrees"] = snapshot.LookPitchDegrees;
        _automationState["horizon_roll_degrees"] = snapshot.HorizonRollDegrees;
        _automationState["pitch_stabilization_degrees"] = Mathf.RadToDeg(pitchCorrection);
        _automationState["roll_stabilization_degrees"] = Mathf.RadToDeg(rollCorrection);
        _automationState["maximum_stabilization_degrees"] = MaximumStabilizationDegrees;
        _automationState["maximum_look_yaw_degrees"] = MaximumLookYawDegrees;
        _automationState["maximum_look_pitch_degrees"] = MaximumLookPitchDegrees;
    }
}

public sealed record CockpitCameraSnapshot(
    bool Active,
    bool VehicleLocal,
    double LookYawDegrees,
    double LookPitchDegrees,
    double HorizonRollDegrees,
    double PitchStabilizationDegrees,
    double RollStabilizationDegrees);
