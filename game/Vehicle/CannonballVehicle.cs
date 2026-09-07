using Cannonball.Core.Runs;
using Cannonball.Core.Simulation.Vehicle;
using Cannonball.Game.Camera;
using Cannonball.Game.Input;
using Godot;

namespace Cannonball.Game.Vehicle;

public sealed partial class CannonballVehicle : RigidBody3D
{
    /// <summary>
    /// Height of the chassis origin above the tyre contact points at static
    /// ride height: the wheel anchor depth plus the spring length that remains
    /// once four springs carry the vehicle mass, plus the tyre radius. The
    /// visual rig hangs this far below the chassis so its design ground plane
    /// is the road, and review placement freezes the car at this height.
    /// </summary>
    public static readonly float VisualRigMountHeightMeters =
        0.18f +
        (VehicleDynamicsProfile.SpringRestLengthMeters -
            VehicleDynamicsProfile.VehicleMassKilograms * VehicleDynamicsProfile.GravityMetersPerSecondSquared /
            (4 * VehicleDynamicsProfile.SpringStrengthNewtonsPerMeter)) +
        VehicleDynamicsProfile.WheelRadiusMeters;

    private static readonly Vector3[] WheelPositions =
    [
        new(-0.82f, -0.18f, -1.42f),
        new(0.82f, -0.18f, -1.42f),
        new(-0.82f, -0.18f, 1.42f),
        new(0.82f, -0.18f, 1.42f),
    ];

    /// <summary>Persistent suspension rays, one per wheel.</summary>
    /// <remarks>
    /// Created once and reused, so the per-tick contact query allocates nothing.
    /// </remarks>
    private readonly RayCast3D[] _suspensionRays = new RayCast3D[4];

    private readonly float[] _wheelCompressionMeters = new float[4];
    private bool _resetRequested;
    private int _consecutiveUnsupportedPhysicsFrames;
    private int _consecutiveSuspensionBottomOutFrames;
    private bool _hasBeenGrounded;
    private float _currentSteerAngleRadians;
    private bool _cameraToggleHeld;
    private Vector3 _supportNormal = Vector3.Up;
    private float _supportRatio;
    private VehicleSetup _setup = VehicleSetup.Starter;

    public VehicleSetup Setup
    {
        get => _setup;
        set => _setup = value ?? throw new ArgumentNullException(nameof(value));
    }

    public bool AutopilotEnabled { get; set; }

    // Reference captures must include the input polling/conditioning cost paid
    // during a real drive, even though autopilot supplies deterministic controls.
    public bool SampleManualInputDuringAutopilot { get; set; }
    public DriveInputState? AutomationInputOverride { get; set; }
    public AssistProfile AssistProfile { get; private set; } = AssistProfile.Balanced;
    public double RouteDistanceMeters { get; set; }
    public Vector3 TargetRoadPoint { get; set; }
    public Vector3 TargetRoadForward { get; set; } = Vector3.Forward;
    public float SpeedMetersPerSecond => LinearVelocity.Length();
    public float AutopilotSpeedLimitMetersPerSecond { get; set; } = 91;
    public int GroundedWheelCount { get; private set; }

    /// <summary>Chassis height above the mean tyre contact point, or NaN airborne.</summary>
    public double RideHeightMeters { get; private set; } = double.NaN;

    /// <summary>
    /// Signed distance from the vehicle to the route centreline it is tracking.
    /// </summary>
    /// <remarks>
    /// WorldStreamer.CurrentLateralOffsetMeters is the lane's own centre offset,
    /// which stays constant while the car sits in a lane and says nothing about
    /// whether it is still on the road.
    /// </remarks>
    public double CrossTrackErrorMeters { get; private set; }

    /// <summary>Times the vehicle has been teleported back onto the route.</summary>
    /// <remarks>
    /// A reset is not neutral for a measurement: the car stops, is repositioned and
    /// its velocity zeroed, so a run containing one is not the steady drive its
    /// other metrics describe.
    /// </remarks>
    public int ResetToRoadCount { get; private set; }

    /// <summary>
    /// How far below its tracked road point the chassis may fall before it
    /// is put back on the road. The terrain margin lies 0.18 m under the
    /// paved surface and the deepest legitimate excursion is a crashed car
    /// on its roof in a shallow cut, so eight metres is unreachable in play.
    /// </summary>
    public const float FallRecoveryDepthMeters = 8f;
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
        // Input conditioning, suspension and drivetrain: the hero vehicle's
        // per-tick cost, which ADR-0023 layer 2 budgets separately from the road.
        using var region = Cannonball.Core.Performance.SubsystemProfiler.Measure(
            Cannonball.Core.Performance.SubsystemProfiler.Subsystem.Vehicle);
        UpdateCameraInput();
        var heading = -GlobalTransform.Basis.Z.Normalized();
        var forwardSpeed = LinearVelocity.Dot(heading);
        if (AutopilotEnabled && SampleManualInputDuringAutopilot)
        {
            _ = DrivingInputController.Read(forwardSpeed, delta, AssistProfile);
        }
        var input = AutomationInputOverride ?? (AutopilotEnabled
            ? ReadAutopilot()
            : DrivingInputController.Read(forwardSpeed, delta, AssistProfile));
        if (GetTree().Paused)
        {
            // Main keeps this subtree in ProcessMode.Always, so these callbacks
            // continue while the tree is paused - but a paused tree deactivates
            // the physics server, so the space never steps. Any force applied
            // here would accumulate for the whole pause and integrate as a
            // single impulse on resume: a 0.5 s trip-map pause measurably
            // launched the vehicle upward at ~5 m/s on CI, scaling with pause
            // length. Input conditioning above still runs so pause suppression
            // can observe neutral input; everything that pushes the body must
            // wait for the simulation to actually run.
            return;
        }
        // The recovery depth is measured from the road the car is tracking.
        // The old plane at local Y = -20 was relative to the rebased origin, so
        // a fall on a descending route could last far longer than the two
        // seconds it implied, and never fired on a route that climbed.
        if (input.Reset || _resetRequested ||
            Position.Y < TargetRoadPoint.Y - FallRecoveryDepthMeters)
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

    public override void _IntegrateForces(PhysicsDirectBodyState3D state)
    {
        if (GroundedWheelCount == 0)
        {
            return;
        }
        // Enforce the road-tangent forward cap in the physics callback. Removing
        // only that component preserves lateral slip and suspension/impact motion
        // normal to the road; airborne and reverse motion are not governed.
        var roadForward = (-state.Transform.Basis.Z).Slide(_supportNormal).Normalized();
        if (roadForward.IsZeroApprox())
        {
            return;
        }
        var velocity = state.LinearVelocity;
        var excess = (float)Setup.ForwardOverspeedMetersPerSecond(velocity.Dot(roadForward));
        if (excess > 0)
        {
            state.LinearVelocity = velocity - roadForward * excess;
        }
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
        // Frozen at the static ride height, so the suspension rays report the
        // same compression a settled car has and the visual wheels sit on the
        // road exactly as they do while driving.
        Position = point + Vector3.Up * VisualRigMountHeightMeters;
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

    public void SetHeadlights(bool on) => VisualRig?.SetHeadlights(on);

    public void ToggleCameraMode() => SetCameraMode(CurrentCameraMode != "cockpit");

    public void SetCameraMode(bool cockpit)
    {
        ChaseCameraRig.SetActive(!cockpit);
        CockpitCameraRig.SetActive(cockpit);
    }

    private void UpdateCameraInput()
    {
        var pressed = Godot.Input.IsActionPressed(GameInputMap.ToggleCamera);
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
        CrossTrackErrorMeters = lateralError;
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
            // A persistent RayCast3D holds its state natively and allocates nothing
            // per query. PhysicsDirectSpaceState3D.IntersectRay allocated a Godot
            // Dictionary for the result and a query object for the request, four
            // times per physics tick - 480 finalizable objects a second. Godot
            // wrappers carry finalizers, so they cannot die in gen0; they are
            // promoted by construction, which is why every collection here was a
            // gen1 collection with a visible pause.
            //
            // The ray rides the chassis, so its transform is set once in
            // BuildChassis; rayStart is the same point in world space, kept for
            // the spring geometry below.
            var ray = _suspensionRays[index];
            ray.ForceRaycastUpdate();
            if (!ray.IsColliding())
            {
                continue;
            }
            var contact = ray.GetCollisionPoint();
            var normal = ray.GetCollisionNormal().Normalized();

            groundedWheels++;
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
        // Chassis height above the mean tyre contact point: the quantity the
        // ride-height work measures, recorded here so a capture can sample it per
        // physics frame instead of reconstructing it.
        RideHeightMeters = groundedWheels > 0
            ? GlobalPosition.Y - (contactPositionSum.Y / groundedWheels)
            : double.NaN;
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
            var forwardDrive = input.Throttle * (float)Setup.ForwardDriveScale(longitudinalSpeed);
            var driveForce = roadForward * (forwardDrive - input.Reverse) *
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
        ResetToRoadCount++;
        Freeze = true;
        Position = TargetRoadPoint + Vector3.Up * 0.78f;
        Basis = Basis.LookingAt(TargetRoadForward, Vector3.Up);
        LinearVelocity = Vector3.Zero;
        AngularVelocity = Vector3.Zero;
        Freeze = false;
        // A reset is a teleport; without this the car is interpolated from where it
        // fell to where it reappears.
        ResetPhysicsInterpolation();
        DrivingInputController.ClearAndSuppress("reset");
        ChaseCameraRig.SnapToTarget();
    }

    private void BuildChassis()
    {
        for (var rayIndex = 0; rayIndex < _suspensionRays.Length; rayIndex++)
        {
            var ray = new RayCast3D
            {
                Name = $"SuspensionRay{rayIndex}",
                Enabled = false,
                CollisionMask = 1,
                ExcludeParent = true,
                // Set once: the ray rides the chassis, so its start (wheel anchor
                // plus 0.15 m up) and downward reach are constants in the chassis
                // frame. Re-marshalling them every physics tick was eight native
                // property sets per tick for values that never change.
                Position = WheelPositions[rayIndex] + new Vector3(0, 0.15f, 0),
                TargetPosition = new Vector3(
                    0,
                    -(VehicleDynamicsProfile.SpringRestLengthMeters +
                        VehicleDynamicsProfile.WheelRadiusMeters + 0.15f),
                    0),
            };
            _suspensionRays[rayIndex] = ray;
            AddChild(ray);
        }
        using var shape = new BoxShape3D { Size = new Vector3(1.86f, 0.64f, 4.45f) };
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
            // The rig's ground plane sits where the road is at static ride
            // height: the chassis origin rests VisualRigMountHeightMeters above
            // the contact points once the springs carry the vehicle.
            VisualRig.Position = new Vector3(0, -VisualRigMountHeightMeters, 0);
            AddChild(VisualRig);
            return;
        }

        // The mesh instance takes its own reference on assignment, so releasing
        // these wrappers here leaves the geometry intact. Left undisposed they
        // survive to finalisation after engine shutdown, which is what produces
        // "Leaked unsafe reference to object" in the Linux smoke.
        using var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("b7172b"),
            Metallic = 0.7f,
            Roughness = 0.24f,
        };
        using var chassisMesh = new BoxMesh { Size = shape.Size };
        AddChild(new MeshInstance3D
        {
            Name = "ChassisMesh",
            Mesh = chassisMesh,
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
