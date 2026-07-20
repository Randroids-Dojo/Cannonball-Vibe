using Godot;

namespace Cannonball.Game.Camera;

public sealed partial class ChaseCameraRig : Node3D
{
    private const float PositionSharpness = 12.0f;
    private const float HighSpeedMetersPerSecond = 90.0f;
    private const float TeleportSnapDistanceMeters = 20.0f;
    private const float ArmForwardOffsetMeters = 1.5f;

    private readonly Godot.Collections.Dictionary _automationState = new();
    private SpringArm3D _arm = null!;
    private Camera3D _camera = null!;
    private Vector3 _smoothedPosition;
    private Vector3 _smoothedForward = Vector3.Forward;
    private bool _initialized;
    private double _headingChangeElapsed;

    public Node3D Target { get; set; } = null!;
    public bool IsActive => _camera.Current;
    public SpringArm3D Arm => _arm;
    public Camera3D Camera => _camera;

    [Export(PropertyHint.Range, "3,14,0.1")]
    public float FollowDistanceMeters { get; set; } = 7.5f;

    [Export(PropertyHint.Range, "0.5,4,0.05")]
    public float FollowHeightMeters { get; set; } = 1.3f;

    [Export(PropertyHint.Range, "0,12,0.1")]
    public float LookAheadMeters { get; set; } = 1.8f;

    [Export(PropertyHint.Range, "0.5,12,0.1")]
    public float YawDampingSharpness { get; set; } = 4.5f;

    [Export(PropertyHint.Range, "0,0.5,0.01")]
    public float RecenterDelaySeconds { get; set; } = 0.08f;

    [Export(PropertyHint.Range, "1,10,0.1")]
    public float SpeedResponseSharpness { get; set; } = 3.0f;

    [Export(PropertyHint.Range, "3,14,0.1")]
    public float HighSpeedFollowDistanceMeters { get; set; } = 8.25f;

    [Export(PropertyHint.Range, "50,100,0.5")]
    public float BaseFieldOfViewDegrees { get; set; } = 76.0f;

    [Export(PropertyHint.Range, "50,100,0.5")]
    public float HighSpeedFieldOfViewDegrees { get; set; } = 79.0f;

    public override void _Ready()
    {
        if (Target is null)
        {
            throw new InvalidOperationException("A chase-camera target is required.");
        }

        Name = "ChaseCameraRig";
        TopLevel = true;
        _arm = new SpringArm3D
        {
            Name = "ChaseCameraArm",
            Position = new Vector3(0, FollowHeightMeters, ArmForwardOffsetMeters),
            RotationDegrees = new Vector3(LookPitchDegrees(), 0, 0),
            SpringLength = FollowDistanceMeters,
            Margin = 0.15f,
            CollisionMask = 1,
        };
        _camera = new Camera3D
        {
            Name = "ChaseCamera",
            Current = true,
            Fov = BaseFieldOfViewDegrees,
        };
        _arm.AddChild(_camera);
        AddChild(_arm);
        SetMeta("automation_id", "camera.chase.rig");
        SetMeta("automation_state", _automationState);
        SnapToTarget();
    }

    public void SetActive(bool active)
    {
        _camera.Current = active;
        _automationState["active"] = active;
    }

    public override void _Process(double delta)
    {
        if (!GodotObject.IsInstanceValid(Target))
        {
            return;
        }

        var targetPosition = Target.GlobalPosition;
        var targetForward = HorizontalForward(Target.GlobalTransform.Basis);
        if (!_initialized || _smoothedPosition.DistanceTo(targetPosition) > TeleportSnapDistanceMeters)
        {
            SnapToTarget();
            return;
        }

        var positionBlend = DecayBlend(PositionSharpness, delta);
        _smoothedPosition = _smoothedPosition.Lerp(targetPosition, positionBlend);
        var headingDelta = SignedHeadingAngle(_smoothedForward, targetForward);
        _headingChangeElapsed = Math.Abs(headingDelta) > Mathf.DegToRad(0.1f)
            ? _headingChangeElapsed + Math.Max(0, delta)
            : 0;
        var headingBlend = _headingChangeElapsed >= RecenterDelaySeconds
            ? DecayBlend(YawDampingSharpness, delta)
            : 0;
        _smoothedForward = _smoothedForward
            .Rotated(Vector3.Up, headingDelta * headingBlend)
            .Normalized();
        ApplyWorldTransform();

        var speed = Target is RigidBody3D body ? body.LinearVelocity.Length() : 0.0f;
        var speedRatio = Mathf.Clamp(speed / HighSpeedMetersPerSecond, 0, 1);
        var lensBlend = DecayBlend(SpeedResponseSharpness, delta);
        _arm.SpringLength = Mathf.Lerp(
            _arm.SpringLength,
            Mathf.Lerp(FollowDistanceMeters, HighSpeedFollowDistanceMeters, speedRatio),
            lensBlend);
        _camera.Fov = Mathf.Lerp(
            _camera.Fov,
            Mathf.Lerp(BaseFieldOfViewDegrees, HighSpeedFieldOfViewDegrees, speedRatio),
            lensBlend);
        UpdateAutomationState(speed);
    }

    public void SnapToTarget()
    {
        _smoothedPosition = Target.GlobalPosition;
        _smoothedForward = HorizontalForward(Target.GlobalTransform.Basis);
        _headingChangeElapsed = 0;
        _initialized = true;
        ApplyWorldTransform();
        UpdateAutomationState(Target is RigidBody3D body
            ? body.LinearVelocity.Length()
            : 0.0f);
    }

    public ChaseCameraSnapshot CaptureSnapshot()
    {
        var targetForward = GodotObject.IsInstanceValid(Target)
            ? HorizontalForward(Target.GlobalTransform.Basis)
            : _smoothedForward;
        var right = GlobalTransform.Basis.X.Normalized();
        var horizonRollRadians = Mathf.Asin(Mathf.Clamp(Math.Abs(right.Dot(Vector3.Up)), 0, 1));
        var hitLength = _arm.GetHitLength();
        return new ChaseCameraSnapshot(
            _camera.Current,
            TopLevel,
            GodotObject.IsInstanceValid(Target),
            Mathf.RadToDeg(Math.Abs(SignedHeadingAngle(_smoothedForward, targetForward))),
            Mathf.RadToDeg(horizonRollRadians),
            _arm.SpringLength,
            hitLength,
            Math.Max(0, _arm.SpringLength - hitLength),
            GodotObject.IsInstanceValid(Target)
                ? _camera.GlobalPosition.DistanceTo(Target.GlobalPosition)
                : double.PositiveInfinity,
            _camera.Fov);
    }

    private void ApplyWorldTransform()
    {
        GlobalTransform = new Transform3D(
            Basis.LookingAt(_smoothedForward, Vector3.Up),
            _smoothedPosition);
    }

    private void UpdateAutomationState(float speedMetersPerSecond)
    {
        var snapshot = CaptureSnapshot();
        _automationState["mode"] = "chase";
        _automationState["active"] = snapshot.Active;
        _automationState["top_level"] = snapshot.TopLevel;
        _automationState["target_valid"] = snapshot.TargetValid;
        _automationState["inherits_vehicle_rotation"] = false;
        _automationState["heading_lag_degrees"] = snapshot.HeadingLagDegrees;
        _automationState["horizon_roll_degrees"] = snapshot.HorizonRollDegrees;
        _automationState["spring_length_m"] = snapshot.SpringLengthMeters;
        _automationState["spring_hit_length_m"] = snapshot.SpringHitLengthMeters;
        _automationState["collision_compression_m"] = snapshot.CollisionCompressionMeters;
        _automationState["target_distance_m"] = snapshot.TargetDistanceMeters;
        _automationState["field_of_view_degrees"] = snapshot.FieldOfViewDegrees;
        _automationState["follow_distance_m"] = FollowDistanceMeters;
        _automationState["follow_height_m"] = FollowHeightMeters;
        _automationState["look_ahead_m"] = LookAheadMeters;
        _automationState["yaw_damping_sharpness"] = YawDampingSharpness;
        _automationState["recenter_delay_seconds"] = RecenterDelaySeconds;
        _automationState["speed_response_sharpness"] = SpeedResponseSharpness;
        _automationState["speed_mps"] = speedMetersPerSecond;
        _automationState["collision_mask"] = (long)_arm.CollisionMask;
    }

    private static Vector3 HorizontalForward(Basis basis)
    {
        var forward = -basis.Z;
        forward.Y = 0;
        return forward.LengthSquared() > 0.000001f
            ? forward.Normalized()
            : Vector3.Forward;
    }

    private static float SignedHeadingAngle(Vector3 from, Vector3 to) =>
        Mathf.Atan2(from.Cross(to).Y, Mathf.Clamp(from.Dot(to), -1, 1));

    private static float DecayBlend(float sharpness, double delta) =>
        1.0f - (float)Math.Exp(-sharpness * Math.Max(0, delta));

    private float LookPitchDegrees() => -Mathf.RadToDeg(Mathf.Atan2(
        FollowHeightMeters,
        Math.Max(0.1f, FollowDistanceMeters + LookAheadMeters)));
}

public sealed record ChaseCameraSnapshot(
    bool Active,
    bool TopLevel,
    bool TargetValid,
    double HeadingLagDegrees,
    double HorizonRollDegrees,
    double SpringLengthMeters,
    double SpringHitLengthMeters,
    double CollisionCompressionMeters,
    double TargetDistanceMeters,
    double FieldOfViewDegrees);
