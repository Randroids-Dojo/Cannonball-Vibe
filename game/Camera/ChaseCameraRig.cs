using Godot;

namespace Cannonball.Game.Camera;

public sealed partial class ChaseCameraRig : Node3D
{
    private const float BaseSpringLengthMeters = 7.5f;
    private const float HighSpeedSpringLengthMeters = 8.25f;
    private const float BaseFieldOfViewDegrees = 76.0f;
    private const float HighSpeedFieldOfViewDegrees = 79.0f;
    private const float PositionSharpness = 12.0f;
    private const float HeadingSharpness = 4.5f;
    private const float LensSharpness = 3.0f;
    private const float HighSpeedMetersPerSecond = 90.0f;
    private const float TeleportSnapDistanceMeters = 20.0f;

    private readonly Godot.Collections.Dictionary _automationState = new();
    private SpringArm3D _arm = null!;
    private Camera3D _camera = null!;
    private Vector3 _smoothedPosition;
    private Vector3 _smoothedForward = Vector3.Forward;
    private bool _initialized;

    public Node3D Target { get; set; } = null!;
    public bool IsActive => _camera.Current;

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
            Position = new Vector3(0, 1.3f, 1.5f),
            RotationDegrees = new Vector3(-8, 0, 0),
            SpringLength = BaseSpringLengthMeters,
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
        var headingBlend = DecayBlend(HeadingSharpness, delta);
        _smoothedPosition = _smoothedPosition.Lerp(targetPosition, positionBlend);
        var headingDelta = SignedHeadingAngle(_smoothedForward, targetForward);
        _smoothedForward = _smoothedForward
            .Rotated(Vector3.Up, headingDelta * headingBlend)
            .Normalized();
        ApplyWorldTransform();

        var speed = Target is RigidBody3D body ? body.LinearVelocity.Length() : 0.0f;
        var speedRatio = Mathf.Clamp(speed / HighSpeedMetersPerSecond, 0, 1);
        var lensBlend = DecayBlend(LensSharpness, delta);
        _arm.SpringLength = Mathf.Lerp(
            _arm.SpringLength,
            Mathf.Lerp(BaseSpringLengthMeters, HighSpeedSpringLengthMeters, speedRatio),
            lensBlend);
        _camera.Fov = Mathf.Lerp(
            _camera.Fov,
            Mathf.Lerp(BaseFieldOfViewDegrees, HighSpeedFieldOfViewDegrees, speedRatio),
            lensBlend);
        UpdateAutomationState(targetForward, speed);
    }

    public void SnapToTarget()
    {
        _smoothedPosition = Target.GlobalPosition;
        _smoothedForward = HorizontalForward(Target.GlobalTransform.Basis);
        _initialized = true;
        ApplyWorldTransform();
        UpdateAutomationState(_smoothedForward, Target is RigidBody3D body
            ? body.LinearVelocity.Length()
            : 0.0f);
    }

    private void ApplyWorldTransform()
    {
        GlobalTransform = new Transform3D(
            Basis.LookingAt(_smoothedForward, Vector3.Up),
            _smoothedPosition);
    }

    private void UpdateAutomationState(Vector3 targetForward, float speedMetersPerSecond)
    {
        var right = GlobalTransform.Basis.X.Normalized();
        var horizonRollRadians = Mathf.Asin(Mathf.Clamp(Math.Abs(right.Dot(Vector3.Up)), 0, 1));
        _automationState["mode"] = "chase";
        _automationState["active"] = _camera.Current;
        _automationState["top_level"] = TopLevel;
        _automationState["inherits_vehicle_rotation"] = false;
        _automationState["heading_lag_degrees"] = Mathf.RadToDeg(
            Math.Abs(SignedHeadingAngle(_smoothedForward, targetForward)));
        _automationState["horizon_roll_degrees"] = Mathf.RadToDeg(horizonRollRadians);
        _automationState["spring_length_m"] = _arm.SpringLength;
        _automationState["field_of_view_degrees"] = _camera.Fov;
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
}
