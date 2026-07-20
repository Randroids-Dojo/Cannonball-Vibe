using Cannonball.Core.Runs;
using Cannonball.Game.Camera;
using Cannonball.Game.Input;
using Godot;

namespace Cannonball.Game.Vehicle;

public sealed partial class CannonballVehicle : RigidBody3D
{
    private const float SpringRestLength = 0.62f;
    private const float WheelRadius = 0.34f;
    private const float SpringStrength = 42_000.0f;
    private const float SpringDamping = 5_500.0f;
    private const float EngineForce = 25_000.0f;
    private const float BrakeForce = 36_000.0f;
    private const float LateralGrip = 7_800.0f;
    private const float AerodynamicDrag = 0.42f;
    private const float DownforceCoefficient = 9.0f;
    private const float MaximumSteerAngleRadians = 0.38f;

    private static readonly Vector3[] WheelPositions =
    [
        new(-0.82f, -0.18f, -1.42f),
        new(0.82f, -0.18f, -1.42f),
        new(-0.82f, -0.18f, 1.42f),
        new(0.82f, -0.18f, 1.42f),
    ];

    private readonly IDriveInput _driveInput = new GodotDriveInput();
    private readonly float[] _wheelCompressionMeters = new float[4];
    private bool _resetRequested;
    private int _consecutiveUnsupportedPhysicsFrames;
    private bool _hasBeenGrounded;
    private float _currentSteerAngleRadians;
    private bool _cameraToggleHeld;
    private Camera3D _cockpitCamera = null!;
    private readonly Godot.Collections.Dictionary _cockpitCameraAutomationState = new();

    public bool AutopilotEnabled { get; set; }
    public AssistProfile AssistProfile { get; private set; } = AssistProfile.Balanced;
    public double RouteDistanceMeters { get; set; }
    public Vector3 TargetRoadPoint { get; set; }
    public Vector3 TargetRoadForward { get; set; } = Vector3.Forward;
    public float SpeedMetersPerSecond => LinearVelocity.Length();
    public float AutopilotSpeedLimitMetersPerSecond { get; set; } = 91;
    public int GroundedWheelCount { get; private set; }
    public bool HasBeenGrounded => _hasBeenGrounded;
    public int PostGroundingPhysicsFrames { get; private set; }
    public int WellGroundedPhysicsFrames { get; private set; }
    public int MaximumConsecutiveUnsupportedPhysicsFrames { get; private set; }
    public VehicleVisualRig? VisualRig { get; private set; }
    public ChaseCameraRig ChaseCameraRig { get; private set; } = null!;
    public bool UsesGrayboxVisual { get; private set; }
    public bool ForceGrayboxVisual { get; set; }
    public string CurrentCameraMode => ChaseCameraRig.IsActive ? "chase" : "cockpit";

    public override void _Ready()
    {
        Name = "CannonballVehicle";
        Mass = 1_450;
        GravityScale = 1;
        LinearDamp = 0.03f;
        AngularDamp = 0.7f;
        CanSleep = false;
        ContinuousCd = true;
        ContactMonitor = true;
        MaxContactsReported = 12;
        CollisionLayer = 2;
        CollisionMask = 1;
        BuildChassis();
        BuildCamera();
    }

    public override void _PhysicsProcess(double delta)
    {
        UpdateCameraInput();
        var input = AutopilotEnabled ? ReadAutopilot() : _driveInput.Read();
        if (input.Reset || _resetRequested || Position.Y < -20)
        {
            ResetToRoad();
            _resetRequested = false;
            return;
        }

        ApplySuspensionAndTireForces(input);
        ApplyPowerAndStability(input);
        var longitudinalSpeed = LinearVelocity.Dot(-GlobalTransform.Basis.Z.Normalized());
        VisualRig?.ApplyPhysicsState(
            _currentSteerAngleRadians,
            longitudinalSpeed,
            (float)delta,
            _wheelCompressionMeters);
    }

    public void RequestReset() => _resetRequested = true;

    public void RequestResetToRoad(Vector3 point, Vector3 forward)
    {
        TargetRoadPoint = point;
        TargetRoadForward = forward;
        _resetRequested = true;
    }

    public void PlaceForReview(Vector3 point, Vector3 forward)
    {
        Freeze = true;
        Position = point + Vector3.Up * 0.78f;
        Basis = Basis.LookingAt(forward, Vector3.Up);
        LinearVelocity = Vector3.Zero;
        AngularVelocity = Vector3.Zero;
        _resetRequested = false;
    }

    public void ResetGroundingTelemetry()
    {
        GroundedWheelCount = 0;
        PostGroundingPhysicsFrames = 0;
        WellGroundedPhysicsFrames = 0;
        MaximumConsecutiveUnsupportedPhysicsFrames = 0;
        _consecutiveUnsupportedPhysicsFrames = 0;
        _hasBeenGrounded = false;
    }

    public void CycleAssistProfile()
    {
        AssistProfile = AssistProfile switch
        {
            AssistProfile.Accessible => AssistProfile.Balanced,
            AssistProfile.Balanced => AssistProfile.Raw,
            _ => AssistProfile.Accessible,
        };
    }

    public void SetAssistProfile(AssistProfile profile) => AssistProfile = profile;

    public void SetVisualLod(int lod) => VisualRig?.SetLod(lod);

    public void SetDamageHighlight(bool visible) => VisualRig?.SetDamageHighlight(visible);

    public void ToggleCameraMode() => SetCameraMode(CurrentCameraMode != "cockpit");

    public void SetCameraMode(bool cockpit)
    {
        ChaseCameraRig.SetActive(!cockpit);
        _cockpitCamera.Current = cockpit;
        _cockpitCameraAutomationState["active"] = cockpit;
        _cockpitCameraAutomationState["mode"] = "cockpit";
        _cockpitCameraAutomationState["vehicle_local"] = true;
    }

    private void UpdateCameraInput()
    {
        var pressed = Godot.Input.IsActionPressed("toggle_camera");
        if (pressed && !_cameraToggleHeld)
        {
            ToggleCameraMode();
        }
        _cameraToggleHeld = pressed;
    }

    private DriveInputState ReadAutopilot()
    {
        var heading = -GlobalTransform.Basis.Z.Normalized();
        var desiredHeading = TargetRoadForward.Normalized();
        var vehicleRight = heading.Cross(Vector3.Up).Normalized();
        var lateralError = (TargetRoadPoint - GlobalPosition).Dot(vehicleRight);
        var headingError = -heading.Cross(desiredHeading).Y;
        var steering = Mathf.Clamp(
            lateralError * 0.025f + headingError * 1.8f - AngularVelocity.Y * 0.18f,
            -1,
            1);
        var forwardSpeed = LinearVelocity.Dot(heading);
        var speedError = AutopilotSpeedLimitMetersPerSecond - forwardSpeed;
        var speedLimited = AutopilotSpeedLimitMetersPerSecond < 91;
        var throttle = speedLimited
            ? speedError <= 0 ? 0 : Mathf.Clamp(speedError / 5, 0.12f, 1.0f)
            : SpeedMetersPerSecond < 91 ? 1.0f : 0.15f;
        var brake = speedLimited && speedError < 0
            ? Mathf.Clamp(-speedError / 5, 0, 0.35f)
            : 0;
        return new DriveInputState(throttle, brake, steering, false);
    }

    private void ApplySuspensionAndTireForces(DriveInputState input)
    {
        var space = GetWorld3D().DirectSpaceState;
        var chassisUp = GlobalTransform.Basis.Y.Normalized();
        var chassisForward = -GlobalTransform.Basis.Z.Normalized();
        var speed = SpeedMetersPerSecond;
        var steerScale = Mathf.Lerp(1.0f, 0.24f, Mathf.Clamp(speed / 90.0f, 0, 1));
        var steerResponse = AssistProfile switch
        {
            AssistProfile.Accessible => 0.85f,
            AssistProfile.Raw => 1.1f,
            _ => 1.0f,
        };
        var steerAngle = input.Steering * MaximumSteerAngleRadians * steerScale * steerResponse;
        _currentSteerAngleRadians = steerAngle;
        var groundedWheels = 0;
        Array.Clear(_wheelCompressionMeters);

        for (var index = 0; index < WheelPositions.Length; index++)
        {
            var wheelOrigin = GlobalTransform * WheelPositions[index];
            var rayStart = wheelOrigin + chassisUp * 0.15f;
            var rayLength = SpringRestLength + WheelRadius + 0.15f;
            var rayEnd = rayStart - chassisUp * rayLength;
            var query = PhysicsRayQueryParameters3D.Create(rayStart, rayEnd, collisionMask: 1);
            query.Exclude = [GetRid()];
            var hit = space.IntersectRay(query);
            if (hit.Count == 0)
            {
                continue;
            }

            groundedWheels++;
            var contact = (Vector3)hit["position"];
            var normal = ((Vector3)hit["normal"]).Normalized();
            var distance = rayStart.DistanceTo(contact) - 0.15f - WheelRadius;
            var compression = Mathf.Clamp(SpringRestLength - distance, 0, SpringRestLength);
            _wheelCompressionMeters[index] = compression;
            var offset = contact - GlobalPosition;
            var pointVelocity = LinearVelocity + AngularVelocity.Cross(offset);
            var suspensionVelocity = pointVelocity.Dot(normal);
            var suspensionForce = Math.Max(0, compression * SpringStrength - suspensionVelocity * SpringDamping);
            ApplyForce(normal * suspensionForce, offset);

            var wheelForward = index < 2
                ? chassisForward.Rotated(normal, -steerAngle).Normalized()
                : chassisForward;
            var wheelRight = wheelForward.Cross(normal).Normalized();
            var lateralSpeed = pointVelocity.Dot(wheelRight);
            var gripScale = Mathf.Lerp(1.0f, 0.68f, Mathf.Clamp(speed / 100.0f, 0, 1));
            var assistGrip = AssistProfile switch
            {
                AssistProfile.Accessible => 1.25f,
                AssistProfile.Raw => 0.82f,
                _ => 1.0f,
            };
            ApplyForce(-wheelRight * lateralSpeed * LateralGrip * gripScale * assistGrip, offset);
        }

        GroundedWheelCount = groundedWheels;
        if (groundedWheels > 0)
        {
            _hasBeenGrounded = true;
            _consecutiveUnsupportedPhysicsFrames = 0;
        }
        else if (_hasBeenGrounded)
        {
            _consecutiveUnsupportedPhysicsFrames++;
            MaximumConsecutiveUnsupportedPhysicsFrames = Math.Max(
                MaximumConsecutiveUnsupportedPhysicsFrames,
                _consecutiveUnsupportedPhysicsFrames);
        }
        if (_hasBeenGrounded)
        {
            PostGroundingPhysicsFrames++;
            if (groundedWheels >= 3)
            {
                WellGroundedPhysicsFrames++;
            }
        }

        if (groundedWheels > 0)
        {
            var longitudinalSpeed = LinearVelocity.Dot(chassisForward);
            var driveForce = chassisForward * input.Throttle * EngineForce;
            var brakingDirection = Math.Abs(longitudinalSpeed) < 0.5f
                ? Vector3.Zero
                : -chassisForward * Math.Sign(longitudinalSpeed);
            ApplyCentralForce(driveForce + brakingDirection * input.Brake * BrakeForce);
            ApplyCentralForce(-chassisUp * speed * speed * DownforceCoefficient);
        }
    }

    private void ApplyPowerAndStability(DriveInputState input)
    {
        var velocity = LinearVelocity;
        var speed = velocity.Length();
        if (speed > 0.01f)
        {
            ApplyCentralForce(-velocity.Normalized() * speed * speed * AerodynamicDrag);
        }

        var up = GlobalTransform.Basis.Y.Normalized();
        var correctionAxis = up.Cross(Vector3.Up);
        var stability = AssistProfile switch
        {
            AssistProfile.Accessible => 1.3f,
            AssistProfile.Raw => 0.35f,
            _ => 1.0f,
        };
        ApplyTorque(correctionAxis * 9_000.0f * stability - AngularVelocity * 850.0f * stability);

        var speedRatio = Mathf.Clamp(speed / 90.0f, 0, 1);
        var yawAuthority = Mathf.Lerp(7_500.0f, 2_200.0f, speedRatio);
        ApplyTorque(Vector3.Up * -input.Steering * yawAuthority);
    }

    private void ResetToRoad()
    {
        Freeze = true;
        Position = TargetRoadPoint + Vector3.Up * 0.78f;
        Basis = Basis.LookingAt(TargetRoadForward, Vector3.Up);
        LinearVelocity = Vector3.Zero;
        AngularVelocity = Vector3.Zero;
        Freeze = false;
    }

    private void BuildChassis()
    {
        var shape = new BoxShape3D { Size = new Vector3(1.86f, 0.64f, 4.45f) };
        AddChild(new CollisionShape3D { Name = "ChassisCollision", Shape = shape });
        UsesGrayboxVisual = ForceGrayboxVisual ||
            OS.GetCmdlineUserArgs().Contains("--graybox-vehicle", StringComparer.Ordinal);
        if (!UsesGrayboxVisual)
        {
            var wrapper = ResourceLoader.Load<PackedScene>(
                "res://game/Vehicle/Visuals/HeroGt.tscn");
            if (wrapper is null)
            {
                throw new InvalidOperationException("Hero GT wrapper scene could not be loaded.");
            }
            VisualRig = wrapper.Instantiate<VehicleVisualRig>();
            VisualRig.Position = new Vector3(0, -0.76f, 0);
            AddChild(VisualRig);
            return;
        }

        var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("b7172b"),
            Metallic = 0.7f,
            Roughness = 0.24f,
        };
        AddChild(new MeshInstance3D
        {
            Name = "ChassisMesh",
            Mesh = new BoxMesh { Size = shape.Size },
            MaterialOverride = material,
        });
    }

    private void BuildCamera()
    {
        ChaseCameraRig = new ChaseCameraRig
        {
            Target = this,
        };
        AddChild(ChaseCameraRig);
        var cockpitAnchor = VisualRig?.CockpitCameraAnchor;
        if (cockpitAnchor is null)
        {
            cockpitAnchor = new Node3D
            {
                Name = "GrayboxCockpitCameraAnchor",
                Position = new Vector3(0, 0.45f, -0.35f),
            };
            AddChild(cockpitAnchor);
        }
        _cockpitCamera = new Camera3D
        {
            Name = "CockpitCamera",
            Current = false,
            Fov = 72,
            Near = 0.08f,
            Position = new Vector3(0, 0.28f, -0.42f),
        };
        _cockpitCamera.SetMeta("automation_id", "camera.cockpit.view");
        _cockpitCamera.SetMeta("automation_state", _cockpitCameraAutomationState);
        cockpitAnchor.AddChild(_cockpitCamera);
        SetCameraMode(cockpit: false);
    }
}
