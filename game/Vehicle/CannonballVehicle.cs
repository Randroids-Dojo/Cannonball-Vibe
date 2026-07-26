using Cannonball.Core.Runs;
using Cannonball.Core.Simulation.Vehicle;
using Cannonball.Game.Camera;
using Cannonball.Game.Input;
using Godot;

namespace Cannonball.Game.Vehicle;

public sealed partial class CannonballVehicle : RigidBody3D
{
    private static readonly Vector3[] WheelPositions =
    [
        new(-0.82f, -0.18f, -1.42f),
        new(0.82f, -0.18f, -1.42f),
        new(-0.82f, -0.18f, 1.42f),
        new(0.82f, -0.18f, 1.42f),
    ];

    private readonly float[] _wheelCompressionMeters = new float[4];
    private bool _resetRequested;
    private int _consecutiveUnsupportedPhysicsFrames;
    private int _consecutiveSuspensionBottomOutFrames;
    private bool _hasBeenGrounded;
    private float _currentSteerAngleRadians;
    private bool _cameraToggleHeld;
    private Vector3 _supportNormal = Vector3.Up;
    private float _supportRatio;

    public bool AutopilotEnabled { get; set; }
    public DriveInputState? AutomationInputOverride { get; set; }
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
    public float MinimumObservedSuspensionCompressionMeters { get; private set; } =
        VehicleDynamicsProfile.SpringRestLengthMeters;
    public float MaximumObservedSuspensionCompressionMeters { get; private set; }
    public int MaximumConsecutiveSuspensionBottomOutFrames { get; private set; }
    public VehicleVisualRig? VisualRig { get; private set; }
    public DrivingInputController DrivingInputController { get; private set; } = null!;
    public ChaseCameraRig ChaseCameraRig { get; private set; } = null!;
    public CockpitCameraRig CockpitCameraRig { get; private set; } = null!;
    public bool UsesGrayboxVisual { get; private set; }
    public bool ForceGrayboxVisual { get; set; }
    public string CurrentCameraMode => ChaseCameraRig.IsActive ? "chase" : "cockpit";

    public override void _Ready()
    {
        Name = "CannonballVehicle";
        Mass = VehicleDynamicsProfile.VehicleMassKilograms;
        GravityScale = 1;
        LinearDampMode = DampMode.Replace;
        LinearDamp = 0;
        AngularDampMode = DampMode.Replace;
        AngularDamp = 0;
        CanSleep = false;
        ContinuousCd = true;
        CenterOfMassMode = CenterOfMassModeEnum.Custom;
        CenterOfMass = new Vector3(0, VehicleDynamicsProfile.CenterOfMassOffsetMeters, 0);
        ContactMonitor = true;
        MaxContactsReported = 12;
        CollisionLayer = 2;
        CollisionMask = 1;
        BuildChassis();
        DrivingInputController = new DrivingInputController();
        AddChild(DrivingInputController);
        BuildCamera();
    }

    public override void _PhysicsProcess(double delta)
    {
        UpdateCameraInput();
        var heading = -GlobalTransform.Basis.Z.Normalized();
        var forwardSpeed = LinearVelocity.Dot(heading);
        var input = AutomationInputOverride ?? (AutopilotEnabled
            ? ReadAutopilot()
            : DrivingInputController.Read(forwardSpeed, delta, AssistProfile));
        if (input.Reset || _resetRequested || Position.Y < -20)
        {
            ResetToRoad();
            _resetRequested = false;
            return;
        }

        ApplySuspensionAndTireForces(input);
        ApplyPowerAndStability(input);
        VisualRig?.ApplyPhysicsState(
            _currentSteerAngleRadians,
            forwardSpeed,
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
        MinimumObservedSuspensionCompressionMeters =
            VehicleDynamicsProfile.SpringRestLengthMeters;
        MaximumObservedSuspensionCompressionMeters = 0;
        _consecutiveUnsupportedPhysicsFrames = 0;
        _consecutiveSuspensionBottomOutFrames = 0;
        MaximumConsecutiveSuspensionBottomOutFrames = 0;
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
        CockpitCameraRig.SetActive(cockpit);
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
        return new DriveInputState(throttle, brake, 0, 0, steering, false, false);
    }

    private void ApplySuspensionAndTireForces(DriveInputState input)
    {
        var space = GetWorld3D().DirectSpaceState;
        var chassisUp = GlobalTransform.Basis.Y.Normalized();
        var chassisForward = -GlobalTransform.Basis.Z.Normalized();
        var speed = SpeedMetersPerSecond;
        var steerScale = AutopilotEnabled
            ? Mathf.Lerp(1.0f, 0.24f, Mathf.Clamp(speed / 90.0f, 0, 1))
            : 1.0f;
        var steerResponse = AssistProfile switch
        {
            AssistProfile.Accessible => 0.85f,
            AssistProfile.Raw => 0.85f,
            _ => 1.0f,
        };
        var steerAngle = input.Steering *
            VehicleDynamicsProfile.MaximumSteerAngleRadians * steerScale * steerResponse;
        _currentSteerAngleRadians = steerAngle;
        var groundedWheels = 0;
        var contactNormalSum = Vector3.Zero;
        var contactPositionSum = Vector3.Zero;
        var suspensionBottomedOut = false;
        var tuning = VehicleDynamicsProfile.For(AssistProfile);
        Array.Clear(_wheelCompressionMeters);

        for (var index = 0; index < WheelPositions.Length; index++)
        {
            var wheelOrigin = GlobalTransform * WheelPositions[index];
            var rayStart = wheelOrigin + chassisUp * 0.15f;
            var rayLength = VehicleDynamicsProfile.SpringRestLengthMeters +
                VehicleDynamicsProfile.WheelRadiusMeters + 0.15f;
            var rayEnd = rayStart - chassisUp * rayLength;
            using var query = PhysicsRayQueryParameters3D.Create(
                rayStart,
                rayEnd,
                collisionMask: 1);
            query.Exclude = [GetRid()];
            var hit = space.IntersectRay(query);
            if (hit.Count == 0)
            {
                continue;
            }

            groundedWheels++;
            var contact = (Vector3)hit["position"];
            var normal = ((Vector3)hit["normal"]).Normalized();
            contactNormalSum += normal;
            contactPositionSum += contact;
            var distance = rayStart.DistanceTo(contact) - 0.15f -
                VehicleDynamicsProfile.WheelRadiusMeters;
            var compression = Mathf.Clamp(
                VehicleDynamicsProfile.SpringRestLengthMeters - distance,
                0,
                VehicleDynamicsProfile.SpringRestLengthMeters);
            _wheelCompressionMeters[index] = compression;
            MinimumObservedSuspensionCompressionMeters = Math.Min(
                MinimumObservedSuspensionCompressionMeters,
                compression);
            MaximumObservedSuspensionCompressionMeters = Math.Max(
                MaximumObservedSuspensionCompressionMeters,
                compression);
            suspensionBottomedOut |=
                compression >= VehicleDynamicsProfile.SuspensionBottomOutThresholdMeters;
            var offset = contact - GlobalPosition;
            var pointVelocity = LinearVelocity + AngularVelocity.Cross(offset);
            var suspensionVelocity = pointVelocity.Dot(normal);
            var suspensionForce = VehicleDynamicsForces.SuspensionForceNewtons(
                compression,
                VehicleDynamicsProfile.SpringStrengthNewtonsPerMeter,
                suspensionVelocity,
                VehicleDynamicsProfile.SpringDampingNewtonsPerMeterPerSecond,
                Mass,
                VehicleDynamicsProfile.GravityMetersPerSecondSquared,
                VehicleDynamicsProfile.MaximumSuspensionLoadG,
                WheelPositions.Length);
            ApplyForce(normal * (float)suspensionForce, offset);

            var wheelForward = index < 2
                ? chassisForward.Rotated(normal, -steerAngle).Normalized()
                : chassisForward;
            var wheelRight = wheelForward.Cross(normal).Normalized();
            var lateralSpeed = pointVelocity.Dot(wheelRight);
            var longitudinalSpeed = pointVelocity.Dot(wheelForward);
            var gripScale = Mathf.Lerp(1.0f, 0.68f, Mathf.Clamp(speed / 100.0f, 0, 1));
            var lateralForce = VehicleDynamicsForces.LateralTireForceNewtons(
                lateralSpeed,
                longitudinalSpeed,
                VehicleDynamicsProfile.TireCorneringStiffnessNewtonsPerRadian,
                gripScale * tuning.LateralResponseScale,
                suspensionForce,
                VehicleDynamicsProfile.TireFrictionCoefficient,
                Mass,
                VehicleDynamicsProfile.MaximumLateralAccelerationMetersPerSecondSquared,
                WheelPositions.Length);
            ApplyForce(
                wheelRight * (float)lateralForce,
                offset);
        }

        GroundedWheelCount = groundedWheels;
        _consecutiveSuspensionBottomOutFrames = suspensionBottomedOut
            ? _consecutiveSuspensionBottomOutFrames + 1
            : 0;
        MaximumConsecutiveSuspensionBottomOutFrames = Math.Max(
            MaximumConsecutiveSuspensionBottomOutFrames,
            _consecutiveSuspensionBottomOutFrames);
        _supportRatio = (float)groundedWheels / WheelPositions.Length;
        if (groundedWheels > 0)
        {
            _supportNormal = contactNormalSum.Normalized();
        }
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
            var roadNormal = _supportNormal;
            var roadForward = chassisForward.Slide(roadNormal).Normalized();
            if (roadForward.IsZeroApprox())
            {
                roadForward = chassisForward;
            }
            var contactAuthority = (float)VehicleDynamicsForces.ContactDriveAuthority(
                groundedWheels,
                WheelPositions.Length,
                tuning.ContactDriveResponseExponent);
            var longitudinalSpeed = LinearVelocity.Dot(roadForward);
            var roadRight = roadForward.Cross(roadNormal).Normalized();
            var lateralSpeed = LinearVelocity.Dot(roadRight);
            var driveForce = roadForward * (input.Throttle - input.Reverse) *
                VehicleDynamicsProfile.EngineForceNewtons * contactAuthority;
            var brakingDirection = Math.Abs(longitudinalSpeed) < 0.05f
                ? Vector3.Zero
                : -roadForward * Math.Sign(longitudinalSpeed);
            var brakingForce = (input.Brake * VehicleDynamicsProfile.BrakeForceNewtons +
                input.Handbrake * VehicleDynamicsProfile.BrakeForceNewtons * 0.8f) *
                contactAuthority;
            var propulsionInput = Math.Max(input.Throttle, input.Reverse);
            var coastResistance = VehicleDynamicsForces.CoastResistanceForceNewtons(
                Math.Abs(longitudinalSpeed),
                Mass,
                VehicleDynamicsProfile.GravityMetersPerSecondSquared,
                VehicleDynamicsProfile.RollingResistanceCoefficient,
                VehicleDynamicsProfile.EngineBrakingBaseNewtons,
                VehicleDynamicsProfile.EngineBrakingNewtonsPerMeterPerSecond,
                propulsionInput,
                _supportRatio);
            var resistanceForce = brakingDirection * (float)coastResistance;
            var contactCenterOffset = contactPositionSum / groundedWheels - GlobalPosition;
            ApplyForce(
                driveForce + brakingDirection * brakingForce + resistanceForce,
                contactCenterOffset);
            var slipAngleRadians = Mathf.Atan2(
                lateralSpeed,
                Math.Max(Math.Abs(longitudinalSpeed), 0.5f));
            ApplyTorque(
                -roadNormal * slipAngleRadians *
                VehicleDynamicsProfile.SlipYawStabilityTorqueNewtonMetersPerRadian *
                tuning.SlipYawStabilityScale * _supportRatio);
            if (input.StationaryHold)
            {
                var gravityForce = Vector3.Down *
                    VehicleDynamicsProfile.GravityMetersPerSecondSquared * Mass;
                var gradeForce = gravityForce - roadNormal * gravityForce.Dot(roadNormal);
                ApplyCentralForce(-gradeForce - LinearVelocity * Mass * 8.0f);
            }
            var groundedDownforce = VehicleDynamicsForces.AerodynamicLoadNewtons(
                speed,
                VehicleDynamicsProfile.GroundedDownforceCoefficient,
                Mass,
                VehicleDynamicsProfile.GravityMetersPerSecondSquared,
                VehicleDynamicsProfile.MaximumGroundedDownforceG);
            ApplyCentralForce(-roadNormal * (float)groundedDownforce);
        }
    }

    private void ApplyPowerAndStability(DriveInputState input)
    {
        var velocity = LinearVelocity;
        var speed = velocity.Length();
        if (speed > 0.01f)
        {
            ApplyCentralForce(
                -velocity.Normalized() * speed * speed *
                VehicleDynamicsProfile.AerodynamicDragCoefficient);
        }

        var up = GlobalTransform.Basis.Y.Normalized();
        var targetUp = _supportRatio > 0 ? _supportNormal : Vector3.Up;
        var correctionAxis = up.Cross(targetUp);
        var tuning = VehicleDynamicsProfile.For(AssistProfile);
        var yawAngularVelocity = targetUp * AngularVelocity.Dot(targetUp);
        var tiltAngularVelocity = AngularVelocity - yawAngularVelocity;
        ApplyTorque(
            correctionAxis * VehicleDynamicsProfile.UprightTorqueNewtonMeters *
                tuning.UprightTorqueScale -
            tiltAngularVelocity * VehicleDynamicsProfile.TiltDampingNewtonMeterSeconds *
                tuning.TiltDampingScale -
            yawAngularVelocity * VehicleDynamicsProfile.YawDampingNewtonMeterSeconds *
                tuning.YawDampingScale);

        if (_supportRatio <= 0)
        {
            var airborneDownforce = VehicleDynamicsForces.AerodynamicLoadNewtons(
                speed,
                VehicleDynamicsProfile.AirborneDownforceCoefficient,
                Mass,
                VehicleDynamicsProfile.GravityMetersPerSecondSquared,
                VehicleDynamicsProfile.MaximumAirborneDownforceG,
                tuning.AirborneDownforceScale);
            ApplyCentralForce(Vector3.Down * (float)airborneDownforce);
        }

        // Steering yaw comes from the front contact patches. A separate steering
        // torque would rotate the chassis around its center even without support.
    }

    private void ResetToRoad()
    {
        Freeze = true;
        Position = TargetRoadPoint + Vector3.Up * 0.78f;
        Basis = Basis.LookingAt(TargetRoadForward, Vector3.Up);
        LinearVelocity = Vector3.Zero;
        AngularVelocity = Vector3.Zero;
        Freeze = false;
        DrivingInputController.ClearAndSuppress("reset");
        ChaseCameraRig.SnapToTarget();
    }

    private void BuildChassis()
    {
        var shape = new BoxShape3D { Size = new Vector3(1.86f, 0.64f, 4.45f) };
        AddChild(new CollisionShape3D { Name = "ChassisCollision", Shape = shape });
        UsesGrayboxVisual = ForceGrayboxVisual ||
            OS.GetCmdlineUserArgs().Contains("--graybox-vehicle", StringComparer.Ordinal);
        if (!UsesGrayboxVisual)
        {
            using var wrapper = ResourceLoader.Load<PackedScene>(
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
        CockpitCameraRig = new CockpitCameraRig();
        cockpitAnchor.AddChild(CockpitCameraRig);
        if (VisualRig is not null)
        {
            VisualRig.ConfigureCockpitCamera(CockpitCameraRig.Camera);
        }
        SetCameraMode(cockpit: false);
    }
}
