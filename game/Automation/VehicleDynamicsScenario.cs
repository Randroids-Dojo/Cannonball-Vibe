using Cannonball.Core.Runs;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game.Automation;

public sealed class VehicleDynamicsScenario
{
    private const int PhysicsTicksPerSecond = 120;
    private const int SettleFrames = 8;
    private const int StableRecoveryFrames = 24;
    private const int MaximumScenarioFrames = 720;
    private const float CourseCenterX = 250;
    private const float CourseHalfWidth = 9;
    private const float InclineStartZ = 10;
    private const float CrestZ = -20;
    private const float LandingEndZ = -50;
    private const float CourseEndZ = -110;

    private readonly CannonballVehicle _vehicle;
    private readonly WorldStreamer _streamer;
    private readonly bool _review;
    private readonly IReadOnlyList<AssistProfile> _profiles;
    private readonly Godot.Collections.Dictionary _automationState = new();
    private readonly VehicleDynamicsAcceptanceBands _bands =
        VehicleDynamicsProfile.HighSpeedInclineBands;
    private int _frames;
    private int _stableRecoveryFrames;
    private int _firstUnsupportedFrame = -1;
    private int _firstRecoveredFrame = -1;
    private int _profileIndex;
    private float _maximumTiltDegrees;
    private float _maximumAngularSpeed;

    public VehicleDynamicsScenario(
        Node parent,
        CannonballVehicle vehicle,
        WorldStreamer streamer,
        bool review,
        IReadOnlyList<AssistProfile> profiles)
    {
        _vehicle = vehicle;
        _streamer = streamer;
        _review = review;
        _profiles = profiles.Count > 0
            ? profiles
            : throw new ArgumentException("At least one assist profile is required.", nameof(profiles));
        _streamer.ProcessMode = Node.ProcessModeEnum.Disabled;
        BuildCourse(parent);
        var semanticNode = new Node { Name = "VehicleDynamicsScenario" };
        semanticNode.SetMeta("automation_id", "vehicle.dynamics.scenario");
        semanticNode.SetMeta("automation_state", _automationState);
        parent.AddChild(semanticNode);
        _vehicle.AutopilotEnabled = false;
        _vehicle.Freeze = true;
        UpdateAutomationState();
    }

    public bool Complete { get; private set; }

    public void Advance()
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

        ObserveRun();
        UpdateAutomationState();
        var reachedRunout = _vehicle.GlobalPosition.Z <= CourseEndZ + 25;
        if (!reachedRunout && _frames < MaximumScenarioFrames)
        {
            return;
        }

        Validate();
        GD.Print(
            "CANNONBALL_VEHICLE_DYNAMICS_OK " +
            $"profile={CurrentProfile} speed_mps={_bands.EntrySpeedMetersPerSecond:0.0} " +
            $"grade={_bands.GradeRise:0.000} " +
            $"unsupported_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} " +
            $"maximum_tilt_deg={_maximumTiltDegrees:0.000} " +
            $"maximum_angular_speed_rad_s={_maximumAngularSpeed:0.000} " +
            $"recovery_frames={RecoveryFrames()}");
        if (_profileIndex + 1 < _profiles.Count)
        {
            _profileIndex++;
            ResetForNextProfile();
            return;
        }

        Complete = true;
        _vehicle.AutopilotEnabled = false;
        _vehicle.Freeze = true;
        UpdateAutomationState();
    }

    private void BeginRun()
    {
        _vehicle.ResetGroundingTelemetry();
        _vehicle.SetAssistProfile(CurrentProfile);
        _vehicle.TargetRoadPoint = new Vector3(CourseCenterX, 0, CourseEndZ);
        _vehicle.TargetRoadForward = Vector3.Forward;
        _vehicle.GlobalTransform = new Transform3D(
            Basis.LookingAt(Vector3.Forward, Vector3.Up),
            new Vector3(CourseCenterX, 0.78f, 48));
        _vehicle.LinearVelocity =
            Vector3.Forward * _bands.EntrySpeedMetersPerSecond;
        _vehicle.AngularVelocity = Vector3.Zero;
        _vehicle.AutopilotSpeedLimitMetersPerSecond =
            _bands.EntrySpeedMetersPerSecond + 2;
        _vehicle.Freeze = false;
        _vehicle.AutopilotEnabled = true;
        _vehicle.ChaseCameraRig.SnapToTarget();
    }

    private void ObserveRun()
    {
        var up = _vehicle.GlobalBasis.Y.Normalized();
        var tilt = Mathf.RadToDeg(Mathf.Acos(Mathf.Clamp(up.Dot(Vector3.Up), -1, 1)));
        _maximumTiltDegrees = Math.Max(_maximumTiltDegrees, tilt);
        _maximumAngularSpeed = Math.Max(
            _maximumAngularSpeed,
            _vehicle.AngularVelocity.Length());

        if (_vehicle.HasBeenGrounded && _vehicle.GroundedWheelCount == 0 &&
            _firstUnsupportedFrame < 0)
        {
            _firstUnsupportedFrame = _frames;
        }
        if (_firstUnsupportedFrame >= 0 && _vehicle.GroundedWheelCount >= 3 &&
            tilt <= 20)
        {
            _stableRecoveryFrames++;
            if (_stableRecoveryFrames >= StableRecoveryFrames &&
                _firstRecoveredFrame < 0)
            {
                _firstRecoveredFrame = _frames - StableRecoveryFrames + 1;
            }
        }
        else
        {
            _stableRecoveryFrames = 0;
        }
    }

    private void Validate()
    {
        var maximumUnsupportedFrames = (int)Math.Ceiling(
            _bands.MaximumUnsupportedSeconds * PhysicsTicksPerSecond);
        if (_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames > maximumUnsupportedFrames)
        {
            throw new InvalidOperationException(
                "High-speed incline airtime exceeded the fixed forgiving-handling band: " +
                $"actual_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} " +
                $"maximum_frames={maximumUnsupportedFrames}.");
        }
        if (_maximumTiltDegrees > _bands.MaximumChassisTiltDegrees)
        {
            throw new InvalidOperationException(
                "High-speed incline landing exceeded the fixed chassis-tilt band: " +
                $"actual_degrees={_maximumTiltDegrees:0.000} " +
                $"maximum_degrees={_bands.MaximumChassisTiltDegrees:0.000}.");
        }
        if (_maximumAngularSpeed > _bands.MaximumAngularSpeedRadiansPerSecond)
        {
            throw new InvalidOperationException(
                "High-speed incline landing exceeded the fixed angular-speed band: " +
                $"actual_rad_s={_maximumAngularSpeed:0.000} " +
                $"maximum_rad_s={_bands.MaximumAngularSpeedRadiansPerSecond:0.000}.");
        }
        var maximumRecoveryFrames = (int)Math.Ceiling(
            _bands.MaximumLandingRecoverySeconds * PhysicsTicksPerSecond);
        if (_firstRecoveredFrame < 0 || RecoveryFrames() > maximumRecoveryFrames)
        {
            throw new InvalidOperationException(
                "High-speed incline landing did not recover stable wheel contact in time: " +
                $"actual_frames={RecoveryFrames()} maximum_frames={maximumRecoveryFrames}.");
        }
    }

    private int RecoveryFrames() =>
        _firstRecoveredFrame < 0 || _firstUnsupportedFrame < 0
            ? int.MaxValue
            : _firstRecoveredFrame - _firstUnsupportedFrame;

    private void UpdateAutomationState()
    {
        _automationState["complete"] = Complete;
        _automationState["review"] = _review;
        _automationState["profile"] = CurrentProfile.ToString();
        _automationState["profile_index"] = _profileIndex;
        _automationState["profile_count"] = _profiles.Count;
        _automationState["speed_mps"] = _bands.EntrySpeedMetersPerSecond;
        _automationState["grade"] = _bands.GradeRise;
        _automationState["grounded_wheels"] = _vehicle.GroundedWheelCount;
        _automationState["maximum_unsupported_frames"] =
            _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames;
        _automationState["maximum_tilt_degrees"] = _maximumTiltDegrees;
        _automationState["maximum_angular_speed_rad_s"] = _maximumAngularSpeed;
        _automationState["recovery_frames"] = RecoveryFrames();
    }

    private void BuildCourse(Node parent)
    {
        var crestHeight = (InclineStartZ - CrestZ) * _bands.GradeRise;
        var rows = new[]
        {
            new Vector3(CourseCenterX, 0, 60),
            new Vector3(CourseCenterX, 0, InclineStartZ),
            new Vector3(CourseCenterX, crestHeight, CrestZ),
            new Vector3(CourseCenterX, 0, LandingEndZ),
            new Vector3(CourseCenterX, 0, CourseEndZ),
        };
        var vertices = new List<Vector3>();
        for (var index = 0; index < rows.Length - 1; index++)
        {
            var firstLeft = rows[index] + Vector3.Left * CourseHalfWidth;
            var firstRight = rows[index] + Vector3.Right * CourseHalfWidth;
            var secondLeft = rows[index + 1] + Vector3.Left * CourseHalfWidth;
            var secondRight = rows[index + 1] + Vector3.Right * CourseHalfWidth;
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
            AlbedoColor = new Color("35485b"),
            Roughness = 0.92f,
            CullMode = BaseMaterial3D.CullModeEnum.Disabled,
        };
        surface.SetMaterial(material);
        foreach (var vertex in vertices)
        {
            surface.SetColor(new Color("35485b"));
            surface.AddVertex(vertex);
        }
        surface.GenerateNormals();
        var mesh = surface.Commit();
        parent.AddChild(new MeshInstance3D
        {
            Name = "VehicleDynamicsCourseMesh",
            Mesh = mesh,
        });
        var body = new StaticBody3D
        {
            Name = "VehicleDynamicsCourseCollision",
            CollisionLayer = 1,
            CollisionMask = 2,
        };
        body.AddChild(new CollisionShape3D { Shape = mesh.CreateTrimeshShape() });
        parent.AddChild(body);
    }

    private AssistProfile CurrentProfile => _profiles[_profileIndex];

    private void ResetForNextProfile()
    {
        _vehicle.AutopilotEnabled = false;
        _vehicle.Freeze = true;
        _frames = 0;
        _stableRecoveryFrames = 0;
        _firstUnsupportedFrame = -1;
        _firstRecoveredFrame = -1;
        _maximumTiltDegrees = 0;
        _maximumAngularSpeed = 0;
        UpdateAutomationState();
    }
}
