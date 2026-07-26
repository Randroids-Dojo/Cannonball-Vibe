using Cannonball.Core.Runs;
using Cannonball.Core.Simulation.Vehicle;
using Cannonball.Game.Input;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Cannonball.Game.Automation;

public sealed class VehicleDynamicsScenario
{
    private const int PhysicsTicksPerSecond = 120;
    private const int SettleFrames = 8;
    private const int StableRecoveryFrames = 24;
    private const int MaximumBrakingFrames = 1_200;
    private const int MaximumInclineFrames = 720;
    private const int MaximumRecoveryFrames = 480;
    private const float FlatCourseCenterX = -250;
    private const float FlatCourseHalfWidth = 120;
    private const float DepartureCourseCenterX = -550;
    private const float DepartureCourseHalfWidth = 40;
    private const float DepartureRoadHalfWidth = 4;
    private const float DepartureReentryHalfWidth = 3.5f;
    private const float BarrierCourseCenterX = 550;
    private const float BarrierCourseHalfWidth = 30;
    private const float BarrierX = BarrierCourseCenterX + 3.5f;
    private const float InclineCourseCenterX = 250;
    private const float InclineCourseHalfWidth = 12;
    private const float InclineStartZ = 10;
    private const float CrestZ = -20;
    private const float LandingEndZ = -50;
    private const float InclineCourseEndZ = -250;

    private static readonly DriveInputState NeutralInput = new(
        0, 0, 0, 0, 0, false, false);

    private readonly CannonballVehicle _vehicle;
    private readonly WorldStreamer _streamer;
    private readonly bool _review;
    private readonly IReadOnlyList<RunDefinition> _runs;
    private readonly Godot.Collections.Dictionary _automationState = new();
    private readonly List<VehicleDynamicsRunResult> _results = [];
    private int _runIndex;
    private int _frames;
    private int _stableRecoveryFrames;
    private int _firstUnsupportedFrame = -1;
    private int _firstRecoveredFrame = -1;
    private float _maximumTiltDegrees;
    private float _maximumPitchDegrees;
    private float _maximumRollDegrees;
    private float _maximumAngularSpeed;
    private float _maximumYawRate;
    private float _maximumSlipAngle;
    private float _maximumLateralAcceleration;
    private float _maximumPathError;
    private int _minimumGroundedWheels = 4;
    private bool _barrierContactObserved;
    private bool _departureEdgeCrossed;
    private int _departureStableFrames;
    private Vector3 _startPosition;
    private Vector3 _previousVelocity;

    public VehicleDynamicsScenario(
        Node parent,
        CannonballVehicle vehicle,
        WorldStreamer streamer,
        bool review,
        IReadOnlyList<AssistProfile> profiles,
        IReadOnlyList<VehicleDynamicsSpeedBand> speedBands,
        IReadOnlyList<VehicleDynamicsFixture> fixtures)
    {
        _vehicle = vehicle;
        _streamer = streamer;
        _review = review;
        _runs = BuildRuns(profiles, speedBands, fixtures);
        _streamer.ProcessMode = Node.ProcessModeEnum.Disabled;
        BuildCourses(parent);
        var semanticNode = new Node { Name = "VehicleDynamicsScenario" };
        semanticNode.SetMeta("automation_id", "vehicle.dynamics.scenario");
        semanticNode.SetMeta("automation_state", _automationState);
        parent.AddChild(semanticNode);
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = NeutralInput;
        _vehicle.Freeze = true;
        UpdateAutomationState();
    }

    public bool Complete { get; private set; }
    public IReadOnlyList<VehicleDynamicsRunResult> Results => _results;
    public string ResultHash { get; private set; } = string.Empty;

    public void AdvancePhysics()
    {
        if (Complete)
        {
            return;
        }

        _frames++;
        if (_frames == SettleFrames)
        {
            BeginRun();
        }
        if (_frames < SettleFrames)
        {
            return;
        }

        var runFrame = _frames - SettleFrames;
        UpdateScriptedInput(runFrame);
        ObserveRun(runFrame);
        UpdateAutomationState();
        if (!RunComplete(runFrame))
        {
            return;
        }

        var result = ValidateAndCapture(runFrame);
        _results.Add(result);
        ValidateReplay(result);
        GD.Print(
            "CANNONBALL_VEHICLE_DYNAMICS_RUN_OK " +
            $"fixture={result.Fixture.ToString().ToLowerInvariant()} " +
            $"profile={result.Profile} band={result.SpeedBandId} " +
            $"speed_mps={result.EntrySpeedMetersPerSecond:0.000} " +
            $"speed_loss_mps={result.SpeedLossMetersPerSecond:0.000} " +
            $"distance_m={result.DistanceMeters:0.000} " +
            $"duration_s={result.DurationSeconds:0.000} " +
            $"path_error_m={result.MaximumPathErrorMeters:0.000} " +
            $"final_lateral_m={Math.Abs(result.FinalPosition.X - _startPosition.X):0.000} " +
            $"unsupported_frames={result.MaximumUnsupportedFrames} " +
            $"min_grounded_wheels={result.MinimumGroundedWheels} " +
            $"tilt_deg={result.MaximumTiltDegrees:0.000} " +
            $"pitch_deg={result.MaximumPitchDegrees:0.000} " +
            $"roll_deg={result.MaximumRollDegrees:0.000} " +
            $"angular_speed_rad_s={result.MaximumAngularSpeedRadiansPerSecond:0.000} " +
            $"yaw_rate_rad_s={result.MaximumYawRateRadiansPerSecond:0.000} " +
            $"slip_deg={result.MaximumSlipAngleDegrees:0.000} " +
            $"lateral_accel_mps2={result.MaximumLateralAccelerationMetersPerSecondSquared:0.000} " +
            $"suspension_travel_m={result.SuspensionTravelMeters:0.000} " +
            $"bottom_out_frames={result.MaximumSuspensionBottomOutFrames} " +
            $"recovery_frames={result.RecoveryFrames}");

        if (_runIndex + 1 < _runs.Count)
        {
            _runIndex++;
            ResetForNextRun();
            return;
        }

        Complete = true;
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = null;
        _vehicle.Freeze = true;
        ResultHash = ComputeResultHash(_results);
        UpdateAutomationState();
        GD.Print(
            "CANNONBALL_VEHICLE_DYNAMICS_SUITE_OK " +
            $"runs={_results.Count} profiles={_runs.Select(run => run.Profile).Distinct().Count()} " +
            $"speed_bands={_runs.Select(run => run.SpeedBand.Id).Distinct().Count()} " +
            $"fixtures={_runs.Select(run => run.Fixture).Distinct().Count()} " +
            $"physics_hz={PhysicsTicksPerSecond} result_hash={ResultHash}");
    }

    private void BeginRun()
    {
        var run = CurrentRun;
        _vehicle.ResetGroundingTelemetry();
        _vehicle.SetAssistProfile(run.Profile);
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = NeutralInput;
        var basis = Basis.Identity;
        var position = new Vector3(FlatCourseCenterX, 0.78f, 400);
        var linearVelocity = Vector3.Forward * run.SpeedBand.SpeedMetersPerSecond;
        var angularVelocity = Vector3.Zero;
        switch (run.Fixture)
        {
            case VehicleDynamicsFixture.Departure:
                position = new Vector3(DepartureCourseCenterX, 0.78f, 400);
                break;
            case VehicleDynamicsFixture.Barrier:
                position = new Vector3(BarrierCourseCenterX, 0.78f, 400);
                linearVelocity += Vector3.Right * 9;
                break;
            case VehicleDynamicsFixture.Incline:
                position = new Vector3(InclineCourseCenterX, 0.78f, 48);
                _vehicle.TargetRoadPoint =
                    new Vector3(InclineCourseCenterX, 0, InclineCourseEndZ);
                break;
            case VehicleDynamicsFixture.Recovery:
                position = new Vector3(FlatCourseCenterX, 0.92f, 120);
                basis = Basis.FromEuler(new Vector3(
                    Mathf.DegToRad(5),
                    Mathf.DegToRad(12),
                    Mathf.DegToRad(18)));
                angularVelocity = new Vector3(0.45f, 1.2f, 0.7f);
                break;
            case VehicleDynamicsFixture.Reset:
                _vehicle.TargetRoadPoint = new Vector3(FlatCourseCenterX, 0, 80);
                _vehicle.TargetRoadForward = Vector3.Forward;
                position = _vehicle.TargetRoadPoint + new Vector3(14, 7, 9);
                basis = Basis.FromEuler(new Vector3(
                    Mathf.DegToRad(20),
                    Mathf.DegToRad(65),
                    Mathf.DegToRad(35)));
                linearVelocity = new Vector3(7, -4, -3);
                angularVelocity = new Vector3(1.5f, 2, 1.2f);
                break;
        }

        _vehicle.TargetRoadForward = Vector3.Forward;
        _vehicle.Freeze = false;
        _vehicle.GlobalTransform = new Transform3D(basis, position);
        _vehicle.LinearVelocity = linearVelocity;
        _vehicle.AngularVelocity = angularVelocity;
        if (run.Fixture == VehicleDynamicsFixture.Reset)
        {
            _vehicle.RequestResetToRoad(
                _vehicle.TargetRoadPoint,
                _vehicle.TargetRoadForward);
        }
        _vehicle.ChaseCameraRig.SnapToTarget();
        _startPosition = position;
        _previousVelocity = linearVelocity;
    }

    private void UpdateScriptedInput(int runFrame)
    {
        var run = CurrentRun;
        _vehicle.AutomationInputOverride = run.Fixture switch
        {
            VehicleDynamicsFixture.Braking => new DriveInputState(
                0, 1, 0, 0, 0, false, false),
            VehicleDynamicsFixture.LaneChange => new DriveInputState(
                0, 0, 0, 0, LaneChangeSteering(runFrame, run.SpeedBand), false, false),
            VehicleDynamicsFixture.Departure => new DriveInputState(
                0, 0, 0, 0, DepartureSteering(run.SpeedBand), false, false),
            VehicleDynamicsFixture.Incline => new DriveInputState(
                0.35f, 0, 0, 0, 0, false, false),
            _ => NeutralInput,
        };
    }

    private void ObserveRun(int runFrame)
    {
        var heading = -_vehicle.GlobalBasis.Z.Normalized();
        var right = heading.Cross(Vector3.Up).Normalized();
        var up = _vehicle.GlobalBasis.Y.Normalized();
        var velocity = _vehicle.LinearVelocity;
        var euler = _vehicle.GlobalBasis.GetEuler();
        var tilt = Mathf.RadToDeg(Mathf.Acos(Mathf.Clamp(up.Dot(Vector3.Up), -1, 1)));
        var forwardSpeed = velocity.Dot(heading);
        var lateralSpeed = velocity.Dot(right);
        var lateralAcceleration = runFrame == 0
            ? 0
            : Math.Abs(((velocity - _previousVelocity) * PhysicsTicksPerSecond).Dot(right));
        _previousVelocity = velocity;
        _maximumTiltDegrees = Math.Max(_maximumTiltDegrees, tilt);
        _maximumPitchDegrees = Math.Max(
            _maximumPitchDegrees,
            Math.Abs(Mathf.RadToDeg(euler.X)));
        _maximumRollDegrees = Math.Max(
            _maximumRollDegrees,
            Math.Abs(Mathf.RadToDeg(euler.Z)));
        _maximumAngularSpeed = Math.Max(
            _maximumAngularSpeed,
            _vehicle.AngularVelocity.Length());
        _maximumYawRate = Math.Max(
            _maximumYawRate,
            Math.Abs(_vehicle.AngularVelocity.Y));
        _maximumSlipAngle = Math.Max(
            _maximumSlipAngle,
            (float)VehicleDynamicsForces.SlipAngleDegrees(forwardSpeed, lateralSpeed));
        _maximumLateralAcceleration = Math.Max(
            _maximumLateralAcceleration,
            lateralAcceleration);
        _maximumPathError = Math.Max(
            _maximumPathError,
            Math.Abs(_vehicle.GlobalPosition.X - _startPosition.X));
        if (runFrame >= 12)
        {
            _minimumGroundedWheels = Math.Min(
                _minimumGroundedWheels,
                _vehicle.GroundedWheelCount);
        }
        if (CurrentRun.Fixture == VehicleDynamicsFixture.Barrier &&
            _vehicle.GlobalPosition.X >= BarrierX - 1.3f)
        {
            _barrierContactObserved = true;
        }
        if (CurrentRun.Fixture == VehicleDynamicsFixture.Departure)
        {
            _departureEdgeCrossed |= _maximumPathError >= DepartureRoadHalfWidth;
            var finalLateralError = Math.Abs(
                _vehicle.GlobalPosition.X - _startPosition.X);
            if (_departureEdgeCrossed &&
                finalLateralError <= DepartureReentryHalfWidth &&
                heading.Dot(Vector3.Forward) >= Mathf.Cos(Mathf.DegToRad(5)) &&
                _vehicle.GroundedWheelCount >= 3)
            {
                _departureStableFrames++;
            }
            else
            {
                _departureStableFrames = 0;
            }
        }

        if (_vehicle.HasBeenGrounded && _vehicle.GroundedWheelCount == 0 &&
            _firstUnsupportedFrame < 0)
        {
            _firstUnsupportedFrame = runFrame;
        }
        if (CurrentRun.Fixture == VehicleDynamicsFixture.Recovery &&
            _vehicle.GroundedWheelCount >= 3 &&
            tilt <= 5 &&
            _vehicle.AngularVelocity.Length() <= 0.3f)
        {
            _stableRecoveryFrames++;
            if (_stableRecoveryFrames >= StableRecoveryFrames &&
                _firstRecoveredFrame < 0)
            {
                _firstRecoveredFrame = runFrame - StableRecoveryFrames + 1;
            }
        }
        else if (_firstUnsupportedFrame >= 0 &&
            _vehicle.GroundedWheelCount >= 3 &&
            tilt <= 20)
        {
            _stableRecoveryFrames++;
            if (_stableRecoveryFrames >= StableRecoveryFrames &&
                _firstRecoveredFrame < 0)
            {
                _firstRecoveredFrame = runFrame - StableRecoveryFrames + 1;
            }
        }
        else
        {
            _stableRecoveryFrames = 0;
        }
    }

    private bool RunComplete(int runFrame) => CurrentRun.Fixture switch
    {
        VehicleDynamicsFixture.Straight => runFrame >= PhysicsTicksPerSecond,
        VehicleDynamicsFixture.Braking =>
            (runFrame >= 5 && _vehicle.SpeedMetersPerSecond <= 0.5f) ||
            runFrame >= MaximumBrakingFrames,
        VehicleDynamicsFixture.LaneChange => runFrame >= 180,
        VehicleDynamicsFixture.Departure =>
            (_departureEdgeCrossed && _departureStableFrames >= StableRecoveryFrames) ||
            runFrame >= MaximumBrakingFrames,
        VehicleDynamicsFixture.Barrier => runFrame >= 240,
        VehicleDynamicsFixture.Incline =>
            _vehicle.GlobalPosition.Z <= InclineCourseEndZ + 25 ||
            runFrame >= MaximumInclineFrames,
        VehicleDynamicsFixture.Recovery =>
            _firstRecoveredFrame >= 0 || runFrame >= MaximumRecoveryFrames,
        VehicleDynamicsFixture.Reset =>
            (runFrame >= 30 &&
                _vehicle.GroundedWheelCount >= 3 &&
                _vehicle.SpeedMetersPerSecond <= 0.1f &&
                _vehicle.AngularVelocity.Length() <= 0.1f) ||
            runFrame >= MaximumRecoveryFrames,
        _ => throw new ArgumentOutOfRangeException(),
    };

    private VehicleDynamicsRunResult ValidateAndCapture(int runFrame)
    {
        var run = CurrentRun;
        var durationSeconds = (double)runFrame / PhysicsTicksPerSecond;
        var distanceMeters = _startPosition.DistanceTo(_vehicle.GlobalPosition);
        var speedLoss = run.SpeedBand.SpeedMetersPerSecond -
            _vehicle.SpeedMetersPerSecond;
        switch (run.Fixture)
        {
            case VehicleDynamicsFixture.Straight:
                Require(
                    speedLoss <= run.SpeedBand.MaximumStraightSpeedLossMetersPerSecond,
                    $"straight speed loss {speedLoss:0.000} m/s exceeds " +
                    $"{run.SpeedBand.MaximumStraightSpeedLossMetersPerSecond:0.000} m/s");
                Require(_maximumPathError <= 0.5f,
                    $"straight path error {_maximumPathError:0.000} m exceeds 0.500 m");
                Require(_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames <= 2,
                    "straight run lost wheel support");
                break;
            case VehicleDynamicsFixture.Braking:
                Require(_vehicle.SpeedMetersPerSecond <= 0.5f,
                    $"braking did not stop; final speed={_vehicle.SpeedMetersPerSecond:0.000} m/s");
                Require(distanceMeters <= run.SpeedBand.MaximumStoppingDistanceMeters,
                    $"stopping distance {distanceMeters:0.000} m exceeds " +
                    $"{run.SpeedBand.MaximumStoppingDistanceMeters:0.000} m");
                Require(durationSeconds <= run.SpeedBand.MaximumStoppingSeconds,
                    $"stopping time {durationSeconds:0.000} s exceeds " +
                    $"{run.SpeedBand.MaximumStoppingSeconds:0.000} s");
                Require(_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames <= 2,
                    "braking run lost wheel support");
                break;
            case VehicleDynamicsFixture.LaneChange:
                ValidateHandlingBand(run.SpeedBand);
                Require(_maximumPathError >= 0.25f,
                    "lane-change input did not produce measurable lateral response");
                Require(_maximumPathError <= 30,
                    $"lane-change path error {_maximumPathError:0.000} m exceeded course bounds");
                Require(_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames <= 4,
                    "lane change lost wheel support for more than four frames");
                break;
            case VehicleDynamicsFixture.Departure:
                ValidateHandlingBand(run.SpeedBand);
                Require(_maximumPathError >= DepartureRoadHalfWidth,
                    $"departure path error {_maximumPathError:0.000} m did not cross " +
                    $"{DepartureRoadHalfWidth:0.000} m road edge");
                Require(_departureStableFrames >= StableRecoveryFrames,
                    "departure did not sustain a grounded paved-road re-entry: " +
                    $"stable_frames={_departureStableFrames} " +
                    $"lateral_m={Math.Abs(_vehicle.GlobalPosition.X - _startPosition.X):0.000} " +
                    $"heading_dot={(-_vehicle.GlobalBasis.Z.Normalized()).Dot(Vector3.Forward):0.000} " +
                    $"grounded={_vehicle.GroundedWheelCount}");
                var finalDepartureError = Math.Abs(
                    _vehicle.GlobalPosition.X - _startPosition.X);
                Require(finalDepartureError <= DepartureReentryHalfWidth,
                    $"departure re-entry retained {finalDepartureError:0.000} m " +
                    "lateral error");
                Require(_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames <= 4,
                    "departure and re-entry lost wheel support for more than four frames");
                break;
            case VehicleDynamicsFixture.Barrier:
                var physicalSafetyBands = VehicleDynamicsProfile.HighSpeedInclineBands;
                Require(_barrierContactObserved,
                    "barrier fixture did not reach the declared contact plane");
                Require(_vehicle.GlobalPosition.X <= BarrierX - 0.5f,
                    $"barrier collision tunneled to x={_vehicle.GlobalPosition.X:0.000}");
                Require(_maximumTiltDegrees <=
                        physicalSafetyBands.MaximumChassisTiltDegrees,
                    $"barrier collision tilt {_maximumTiltDegrees:0.000} deg exceeds " +
                    $"{physicalSafetyBands.MaximumChassisTiltDegrees:0.000} deg");
                Require(_maximumAngularSpeed <=
                        physicalSafetyBands.MaximumAngularSpeedRadiansPerSecond,
                    $"barrier collision angular speed {_maximumAngularSpeed:0.000} rad/s " +
                    "exceeds the shared physical safety band");
                Require(_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames <= 24,
                    "barrier collision lost support for more than 0.2 seconds");
                Require(_vehicle.GroundedWheelCount >= 2,
                    "barrier collision did not recover supported contact");
                break;
            case VehicleDynamicsFixture.Incline:
                var maximumUnsupportedFrames = (int)Math.Ceiling(
                    run.SpeedBand.MaximumInclineUnsupportedSeconds * PhysicsTicksPerSecond);
                var inclineBands = VehicleDynamicsProfile.HighSpeedInclineBands;
                var maximumRecoveryFrames = (int)Math.Ceiling(
                    inclineBands.MaximumLandingRecoverySeconds * PhysicsTicksPerSecond);
                Require(
                    _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames <=
                        maximumUnsupportedFrames,
                    $"incline airtime {_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} " +
                    $"frames exceeds {maximumUnsupportedFrames}");
                Require(_maximumTiltDegrees <= inclineBands.MaximumChassisTiltDegrees,
                    $"incline tilt {_maximumTiltDegrees:0.000} deg exceeds " +
                    $"{inclineBands.MaximumChassisTiltDegrees:0.000} deg");
                Require(
                    _maximumAngularSpeed <= inclineBands.MaximumAngularSpeedRadiansPerSecond,
                    $"incline angular speed {_maximumAngularSpeed:0.000} rad/s exceeds " +
                    $"{inclineBands.MaximumAngularSpeedRadiansPerSecond:0.000} rad/s");
                Require(
                    _firstUnsupportedFrame < 0 ||
                        (_firstRecoveredFrame >= 0 &&
                            UnsupportedRecoveryFrames() <= maximumRecoveryFrames),
                    $"incline recovery {UnsupportedRecoveryFrames()} frames exceeds " +
                    $"{maximumRecoveryFrames}");
                break;
            case VehicleDynamicsFixture.Recovery:
                var currentUp = _vehicle.GlobalBasis.Y.Normalized();
                var currentTilt = Mathf.RadToDeg(Mathf.Acos(
                    Mathf.Clamp(currentUp.Dot(Vector3.Up), -1, 1)));
                Require(_firstRecoveredFrame >= 0,
                    "disturbed chassis did not regain stable contact: " +
                    $"grounded={_vehicle.GroundedWheelCount} " +
                    $"tilt_deg={currentTilt:0.000} " +
                    $"angular_rad_s={_vehicle.AngularVelocity.Length():0.000} " +
                    $"position={_vehicle.GlobalPosition}");
                Require(_maximumTiltDegrees <=
                        VehicleDynamicsProfile.HighSpeedInclineBands
                            .MaximumChassisTiltDegrees,
                    $"recovery tilt {_maximumTiltDegrees:0.000} deg exceeds " +
                    $"{VehicleDynamicsProfile.HighSpeedInclineBands.MaximumChassisTiltDegrees:0.000} deg");
                Require(runFrame <= MaximumRecoveryFrames,
                    $"recovery exceeded {MaximumRecoveryFrames} frames");
                break;
            case VehicleDynamicsFixture.Reset:
                var horizontalError = new Vector2(
                    _vehicle.GlobalPosition.X - _vehicle.TargetRoadPoint.X,
                    _vehicle.GlobalPosition.Z - _vehicle.TargetRoadPoint.Z).Length();
                var rideHeight = _vehicle.GlobalPosition.Y - _vehicle.TargetRoadPoint.Y;
                Require(horizontalError <= 0.1f,
                    $"reset horizontal position differs by {horizontalError:0.000} m");
                Require(rideHeight is >= 0.5f and <= 1.5f,
                    $"reset ride height {rideHeight:0.000} m is outside 0.500-1.500 m");
                Require(_vehicle.GroundedWheelCount >= 3,
                    $"reset retained only {_vehicle.GroundedWheelCount} supported wheels");
                Require(_vehicle.SpeedMetersPerSecond <= 0.1f,
                    $"reset retained {_vehicle.SpeedMetersPerSecond:0.000} m/s velocity");
                Require(_vehicle.AngularVelocity.Length() <= 0.1f,
                    $"reset retained {_vehicle.AngularVelocity.Length():0.000} rad/s rotation");
                break;
        }

        RequireFiniteMetrics();
        var suspensionTravel =
            _vehicle.MaximumObservedSuspensionCompressionMeters -
            _vehicle.MinimumObservedSuspensionCompressionMeters;
        Require(suspensionTravel >= 0,
            $"suspension travel {suspensionTravel:0.000} m is negative");
        Require(
            suspensionTravel <= VehicleDynamicsProfile.MaximumSuspensionTravelMeters,
            $"suspension travel {suspensionTravel:0.000} m exceeds " +
            $"{VehicleDynamicsProfile.MaximumSuspensionTravelMeters:0.000} m");
        Require(
            _vehicle.MaximumConsecutiveSuspensionBottomOutFrames <=
                VehicleDynamicsProfile.MaximumSuspensionBottomOutFrames,
            $"suspension remained near bottom-out for " +
            $"{_vehicle.MaximumConsecutiveSuspensionBottomOutFrames} frames; maximum is " +
            $"{VehicleDynamicsProfile.MaximumSuspensionBottomOutFrames}");
        return new VehicleDynamicsRunResult(
            run.Profile,
            run.SpeedBand.Id,
            run.Fixture,
            run.ReplayIndex,
            run.SpeedBand.SpeedMetersPerSecond,
            durationSeconds,
            distanceMeters,
            speedLoss,
            _maximumPathError,
            _maximumTiltDegrees,
            _maximumPitchDegrees,
            _maximumRollDegrees,
            _maximumAngularSpeed,
            _maximumYawRate,
            _maximumSlipAngle,
            _maximumLateralAcceleration,
            suspensionTravel,
            _vehicle.MaximumConsecutiveSuspensionBottomOutFrames,
            _minimumGroundedWheels,
            _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames,
            run.Fixture is VehicleDynamicsFixture.Recovery or
                VehicleDynamicsFixture.Departure
                ? runFrame
                : UnsupportedRecoveryFrames(),
            _vehicle.GlobalPosition,
            _vehicle.LinearVelocity,
            _vehicle.AngularVelocity);
    }

    private void ValidateHandlingBand(VehicleDynamicsSpeedBand band)
    {
        GD.Print(
            "CANNONBALL_VEHICLE_DYNAMICS_HANDLING_METRICS " +
            $"profile={CurrentRun.Profile} band={band.Id} " +
            $"roll_deg={_maximumRollDegrees:0.000} " +
            $"yaw_rate_rad_s={_maximumYawRate:0.000} " +
            $"slip_deg={_maximumSlipAngle:0.000} " +
            $"lateral_accel_mps2={_maximumLateralAcceleration:0.000}");
        Require(_maximumRollDegrees <= band.MaximumRollDegrees,
            $"roll {_maximumRollDegrees:0.000} deg exceeds {band.MaximumRollDegrees:0.000} deg");
        Require(_maximumYawRate <= band.MaximumYawRateRadiansPerSecond,
            $"yaw rate {_maximumYawRate:0.000} rad/s exceeds " +
            $"{band.MaximumYawRateRadiansPerSecond:0.000} rad/s");
        Require(_maximumSlipAngle <= band.MaximumSlipAngleDegrees,
            $"slip {_maximumSlipAngle:0.000} deg exceeds " +
            $"{band.MaximumSlipAngleDegrees:0.000} deg");
        Require(
            _maximumLateralAcceleration <=
                band.MaximumLateralAccelerationMetersPerSecondSquared,
            $"lateral acceleration {_maximumLateralAcceleration:0.000} m/s2 exceeds " +
            $"{band.MaximumLateralAccelerationMetersPerSecondSquared:0.000} m/s2");
    }

    private void ValidateReplay(VehicleDynamicsRunResult result)
    {
        if (result.ReplayIndex == 0)
        {
            return;
        }
        var baseline = _results.First(candidate =>
            candidate.ReplayIndex == 0 &&
            candidate.Profile == result.Profile &&
            candidate.SpeedBandId == result.SpeedBandId &&
            candidate.Fixture == result.Fixture);
        Require(result.FinalPosition.DistanceTo(baseline.FinalPosition) <= 0.01f,
            "deterministic replay position diverged by more than 0.01 m");
        Require(result.FinalVelocity.DistanceTo(baseline.FinalVelocity) <= 0.01f,
            "deterministic replay velocity diverged by more than 0.01 m/s");
        Require(
            result.FinalAngularVelocity.DistanceTo(baseline.FinalAngularVelocity) <= 0.01f,
            "deterministic replay angular velocity diverged by more than 0.01 rad/s");
        Require(Math.Abs(result.MaximumRollDegrees - baseline.MaximumRollDegrees) <= 0.01f,
            "deterministic replay roll metric diverged");
        Require(Math.Abs(result.MaximumSlipAngleDegrees - baseline.MaximumSlipAngleDegrees) <= 0.01f,
            "deterministic replay slip metric diverged");
    }

    private void RequireFiniteMetrics()
    {
        var metrics = new[]
        {
            _maximumTiltDegrees,
            _maximumPitchDegrees,
            _maximumRollDegrees,
            _maximumAngularSpeed,
            _maximumYawRate,
            _maximumSlipAngle,
            _maximumLateralAcceleration,
            _maximumPathError,
            _vehicle.SpeedMetersPerSecond,
        };
        Require(metrics.All(float.IsFinite), "vehicle dynamics produced a non-finite metric");
    }

    private void UpdateAutomationState()
    {
        var run = CurrentRun;
        _automationState["complete"] = Complete;
        _automationState["review"] = _review;
        _automationState["run_index"] = _runIndex;
        _automationState["run_count"] = _runs.Count;
        _automationState["profile"] = run.Profile.ToString();
        _automationState["speed_band"] = run.SpeedBand.Id;
        _automationState["fixture"] = run.Fixture.ToString().ToLowerInvariant();
        _automationState["speed_mps"] = run.SpeedBand.SpeedMetersPerSecond;
        _automationState["grounded_wheels"] = _vehicle.GroundedWheelCount;
        _automationState["maximum_unsupported_frames"] =
            _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames;
        _automationState["maximum_tilt_degrees"] = _maximumTiltDegrees;
        _automationState["maximum_roll_degrees"] = _maximumRollDegrees;
        _automationState["maximum_yaw_rate_rad_s"] = _maximumYawRate;
        _automationState["maximum_slip_angle_degrees"] = _maximumSlipAngle;
        _automationState["maximum_lateral_acceleration_mps2"] =
            _maximumLateralAcceleration;
        _automationState["suspension_travel_m"] =
            _vehicle.MaximumObservedSuspensionCompressionMeters -
            _vehicle.MinimumObservedSuspensionCompressionMeters;
        _automationState["maximum_suspension_bottom_out_frames"] =
            _vehicle.MaximumConsecutiveSuspensionBottomOutFrames;
        _automationState["recovery_frames"] =
            CurrentRun.Fixture is VehicleDynamicsFixture.Recovery or
                VehicleDynamicsFixture.Departure
                ? Math.Max(0, _frames - SettleFrames)
                : UnsupportedRecoveryFrames();
        _automationState["result_hash"] = ResultHash;
    }

    private void BuildCourses(Node parent)
    {
        BuildStrip(
            parent,
            "VehicleDynamicsFlatCourse",
            [
                new Vector3(FlatCourseCenterX, 0, 500),
                new Vector3(FlatCourseCenterX, 0, -500),
            ],
            FlatCourseHalfWidth,
            new Color("283846"));
        BuildStrip(
            parent,
            "VehicleDynamicsDepartureCourse",
            [
                new Vector3(DepartureCourseCenterX, 0, 500),
                new Vector3(DepartureCourseCenterX, 0, -500),
            ],
            DepartureCourseHalfWidth,
            new Color("313b2f"));
        BuildRoadOverlay(
            parent,
            "VehicleDynamicsDepartureRoad",
            DepartureCourseCenterX,
            DepartureRoadHalfWidth);
        BuildStrip(
            parent,
            "VehicleDynamicsBarrierCourse",
            [
                new Vector3(BarrierCourseCenterX, 0, 500),
                new Vector3(BarrierCourseCenterX, 0, -500),
            ],
            BarrierCourseHalfWidth,
            new Color("3e3434"));
        BuildBarrier(parent);
        var crestHeight = (InclineStartZ - CrestZ) *
            VehicleDynamicsProfile.HighSpeedInclineBands.GradeRise;
        BuildStrip(
            parent,
            "VehicleDynamicsInclineCourse",
            [
                new Vector3(InclineCourseCenterX, 0, 60),
                new Vector3(InclineCourseCenterX, 0, InclineStartZ),
                new Vector3(InclineCourseCenterX, crestHeight, CrestZ),
                new Vector3(InclineCourseCenterX, 0, LandingEndZ),
                new Vector3(InclineCourseCenterX, 0, InclineCourseEndZ),
            ],
            InclineCourseHalfWidth,
            new Color("35485b"));
    }

    private static void BuildStrip(
        Node parent,
        string name,
        IReadOnlyList<Vector3> rows,
        float halfWidth,
        Color color)
    {
        var vertices = new List<Vector3>();
        for (var index = 0; index < rows.Count - 1; index++)
        {
            var firstLeft = rows[index] + Vector3.Left * halfWidth;
            var firstRight = rows[index] + Vector3.Right * halfWidth;
            var secondLeft = rows[index + 1] + Vector3.Left * halfWidth;
            var secondRight = rows[index + 1] + Vector3.Right * halfWidth;
            vertices.AddRange(
            [
                firstLeft, secondRight, firstRight,
                firstLeft, secondLeft, secondRight,
            ]);
        }

        using var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        var material = new StandardMaterial3D
        {
            AlbedoColor = color,
            Roughness = 0.92f,
            CullMode = BaseMaterial3D.CullModeEnum.Disabled,
        };
        surface.SetMaterial(material);
        foreach (var vertex in vertices)
        {
            surface.SetColor(color);
            surface.AddVertex(vertex);
        }
        surface.GenerateNormals();
        var mesh = surface.Commit();
        parent.AddChild(new MeshInstance3D
        {
            Name = $"{name}Mesh",
            Mesh = mesh,
        });
        var body = new StaticBody3D
        {
            Name = $"{name}Collision",
            CollisionLayer = 1,
            CollisionMask = 2,
        };
        body.AddChild(new CollisionShape3D { Shape = mesh.CreateTrimeshShape() });
        parent.AddChild(body);
    }

    private static void BuildRoadOverlay(
        Node parent,
        string name,
        float centerX,
        float halfWidth)
    {
        var mesh = new BoxMesh
        {
            Size = new Vector3(halfWidth * 2, 0.01f, 1_000),
            Material = new StandardMaterial3D
            {
                AlbedoColor = new Color("1d2730"),
                Roughness = 0.95f,
            },
        };
        parent.AddChild(new MeshInstance3D
        {
            Name = name,
            Mesh = mesh,
            Position = new Vector3(centerX, 0.005f, 0),
        });
    }

    private static void BuildBarrier(Node parent)
    {
        var size = new Vector3(0.6f, 1.5f, 1_000);
        var mesh = new BoxMesh
        {
            Size = size,
            Material = new StandardMaterial3D
            {
                AlbedoColor = new Color("8f4b3f"),
                Roughness = 0.85f,
            },
        };
        parent.AddChild(new MeshInstance3D
        {
            Name = "VehicleDynamicsBarrierMesh",
            Mesh = mesh,
            Position = new Vector3(BarrierX, size.Y / 2, 0),
        });
        var body = new StaticBody3D
        {
            Name = "VehicleDynamicsBarrierCollision",
            CollisionLayer = 1,
            CollisionMask = 2,
            Position = new Vector3(BarrierX, size.Y / 2, 0),
        };
        body.AddChild(new CollisionShape3D
        {
            Shape = new BoxShape3D { Size = size },
        });
        parent.AddChild(body);
    }

    private static IReadOnlyList<RunDefinition> BuildRuns(
        IReadOnlyList<AssistProfile> profiles,
        IReadOnlyList<VehicleDynamicsSpeedBand> speedBands,
        IReadOnlyList<VehicleDynamicsFixture> fixtures)
    {
        if (profiles.Count == 0 || speedBands.Count == 0 || fixtures.Count == 0)
        {
            throw new ArgumentException(
                "Vehicle dynamics requires at least one profile, speed band, and fixture.");
        }
        var result = new List<RunDefinition>();
        foreach (var profile in profiles)
        {
            foreach (var speedBand in speedBands)
            {
                foreach (var fixture in fixtures)
                {
                    if (fixture == VehicleDynamicsFixture.Reset &&
                        speedBand != speedBands[0])
                    {
                        continue;
                    }
                    result.Add(new RunDefinition(profile, speedBand, fixture, 0));
                }
            }
        }
        var replay = result.FirstOrDefault(run =>
            run.Profile == AssistProfile.Balanced &&
            string.Equals(run.SpeedBand.Id, "push", StringComparison.Ordinal) &&
            run.Fixture == VehicleDynamicsFixture.LaneChange);
        if (replay is not null)
        {
            result.Add(replay with { ReplayIndex = 1 });
        }
        return result;
    }

    private static float LaneChangeSteering(
        int runFrame,
        VehicleDynamicsSpeedBand speedBand)
    {
        if (runFrame < 30)
        {
            return speedBand.SteeringInput;
        }
        if (runFrame < 90)
        {
            return -speedBand.SteeringInput;
        }
        if (runFrame < 120)
        {
            return speedBand.SteeringInput;
        }
        return 0;
    }

    private float DepartureSteering(VehicleDynamicsSpeedBand speedBand)
    {
        if (!_departureEdgeCrossed)
        {
            return speedBand.SteeringInput;
        }
        var heading = -_vehicle.GlobalBasis.Z.Normalized();
        var vehicleRight = heading.Cross(Vector3.Up).Normalized();
        var target = new Vector3(
            DepartureCourseCenterX,
            _vehicle.GlobalPosition.Y,
            _vehicle.GlobalPosition.Z - 100);
        var lateralError = (target - _vehicle.GlobalPosition).Dot(vehicleRight);
        var headingError = -heading.Cross(Vector3.Forward).Y;
        return Mathf.Clamp(
            lateralError * 0.2f +
                headingError * 0.8f -
                _vehicle.AngularVelocity.Y * 0.18f,
            -speedBand.SteeringInput,
            speedBand.SteeringInput);
    }

    private static string ComputeResultHash(
        IReadOnlyList<VehicleDynamicsRunResult> results)
    {
        var stable = string.Join(
            "\n",
            results.Select(StableResult));
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(stable)))
            .ToLowerInvariant();
    }

    private static string StableResult(VehicleDynamicsRunResult result) =>
        string.Join(
            "|",
            result.Profile,
            result.SpeedBandId,
            result.Fixture,
            result.ReplayIndex.ToString(CultureInfo.InvariantCulture),
            result.EntrySpeedMetersPerSecond.ToString("0.000", CultureInfo.InvariantCulture),
            result.DurationSeconds.ToString("0.000", CultureInfo.InvariantCulture),
            result.DistanceMeters.ToString("0.000", CultureInfo.InvariantCulture),
            result.SpeedLossMetersPerSecond.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumPathErrorMeters.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumTiltDegrees.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumPitchDegrees.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumRollDegrees.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumAngularSpeedRadiansPerSecond.ToString(
                "0.000",
                CultureInfo.InvariantCulture),
            result.MaximumYawRateRadiansPerSecond.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumSlipAngleDegrees.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumLateralAccelerationMetersPerSecondSquared.ToString(
                "0.000",
                CultureInfo.InvariantCulture),
            result.SuspensionTravelMeters.ToString("0.000", CultureInfo.InvariantCulture),
            result.MaximumSuspensionBottomOutFrames.ToString(
                CultureInfo.InvariantCulture),
            result.MinimumGroundedWheels.ToString(CultureInfo.InvariantCulture),
            result.MaximumUnsupportedFrames.ToString(CultureInfo.InvariantCulture),
            result.RecoveryFrames.ToString(CultureInfo.InvariantCulture),
            string.Join(
                ",",
                result.FinalPosition.X.ToString("0.000", CultureInfo.InvariantCulture),
                result.FinalPosition.Y.ToString("0.000", CultureInfo.InvariantCulture),
                result.FinalPosition.Z.ToString("0.000", CultureInfo.InvariantCulture)),
            string.Join(
                ",",
                result.FinalVelocity.X.ToString("0.000", CultureInfo.InvariantCulture),
                result.FinalVelocity.Y.ToString("0.000", CultureInfo.InvariantCulture),
                result.FinalVelocity.Z.ToString("0.000", CultureInfo.InvariantCulture)),
            string.Join(
                ",",
                result.FinalAngularVelocity.X.ToString("0.000", CultureInfo.InvariantCulture),
                result.FinalAngularVelocity.Y.ToString("0.000", CultureInfo.InvariantCulture),
                result.FinalAngularVelocity.Z.ToString("0.000", CultureInfo.InvariantCulture)));

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private int UnsupportedRecoveryFrames() =>
        _firstUnsupportedFrame < 0
            ? 0
            : _firstRecoveredFrame < 0
                ? int.MaxValue
                : _firstRecoveredFrame - _firstUnsupportedFrame;

    private RunDefinition CurrentRun => _runs[_runIndex];

    private void ResetForNextRun()
    {
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = NeutralInput;
        _vehicle.Freeze = true;
        _frames = 0;
        _stableRecoveryFrames = 0;
        _firstUnsupportedFrame = -1;
        _firstRecoveredFrame = -1;
        _maximumTiltDegrees = 0;
        _maximumPitchDegrees = 0;
        _maximumRollDegrees = 0;
        _maximumAngularSpeed = 0;
        _maximumYawRate = 0;
        _maximumSlipAngle = 0;
        _maximumLateralAcceleration = 0;
        _maximumPathError = 0;
        _minimumGroundedWheels = 4;
        _barrierContactObserved = false;
        _departureEdgeCrossed = false;
        _departureStableFrames = 0;
        UpdateAutomationState();
    }

    private sealed record RunDefinition(
        AssistProfile Profile,
        VehicleDynamicsSpeedBand SpeedBand,
        VehicleDynamicsFixture Fixture,
        int ReplayIndex);
}

public sealed record VehicleDynamicsRunResult(
    AssistProfile Profile,
    string SpeedBandId,
    VehicleDynamicsFixture Fixture,
    int ReplayIndex,
    float EntrySpeedMetersPerSecond,
    double DurationSeconds,
    double DistanceMeters,
    float SpeedLossMetersPerSecond,
    float MaximumPathErrorMeters,
    float MaximumTiltDegrees,
    float MaximumPitchDegrees,
    float MaximumRollDegrees,
    float MaximumAngularSpeedRadiansPerSecond,
    float MaximumYawRateRadiansPerSecond,
    float MaximumSlipAngleDegrees,
    float MaximumLateralAccelerationMetersPerSecondSquared,
    float SuspensionTravelMeters,
    int MaximumSuspensionBottomOutFrames,
    int MinimumGroundedWheels,
    int MaximumUnsupportedFrames,
    int RecoveryFrames,
    Vector3 FinalPosition,
    Vector3 FinalVelocity,
    Vector3 FinalAngularVelocity);
