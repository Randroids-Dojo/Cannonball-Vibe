using Cannonball.Game.Camera;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game.Automation;

public sealed class CameraHandlingScenario
{
    private const int ProfileFramesPerStage = 12;
    private const int ReviewFramesPerStage = 60;
    private const int MaximumWaitFrames = 900;
    private static readonly string[] StageNames =
    [
        "grade-and-chassis-isolation",
        "spring-arm-collision",
        "spring-arm-recovery",
        "route-transition-and-origin-rebase",
        "vehicle-reset",
        "cockpit-chase-transition",
    ];

    private readonly Node _parent;
    private readonly CannonballVehicle _vehicle;
    private readonly WorldStreamer _streamer;
    private readonly Vector3 _initialRoadPoint;
    private readonly Vector3 _initialRoadForward;
    private readonly bool _review;
    private readonly Node _semanticNode;
    private readonly Godot.Collections.Dictionary _automationState = new();
    private readonly List<double> _collisionHitLengths = [];
    private StaticBody3D? _collisionWall;
    private int _stageIndex;
    private int _stageFrames;
    private int _rebaseCountBefore;
    private string _edgeBeforeRebase = string.Empty;
    private bool _cockpitObserved;
    private bool _chaseObserved;

    public CameraHandlingScenario(
        Node parent,
        CannonballVehicle vehicle,
        WorldStreamer streamer,
        Vector3 initialRoadPoint,
        Vector3 initialRoadForward,
        bool review)
    {
        _parent = parent;
        _vehicle = vehicle;
        _streamer = streamer;
        _initialRoadPoint = initialRoadPoint;
        _initialRoadForward = initialRoadForward.Normalized();
        _review = review;
        _semanticNode = new Node { Name = "CameraHandlingScenario" };
        _semanticNode.SetMeta("automation_id", "camera.handling.scenario");
        _semanticNode.SetMeta("automation_state", _automationState);
        _parent.AddChild(_semanticNode);
        _vehicle.AutopilotEnabled = false;
        _vehicle.SetCameraMode(cockpit: false);
        _vehicle.PlaceForReview(_initialRoadPoint, _initialRoadForward);
        _vehicle.ChaseCameraRig.SnapToTarget();
        UpdateAutomationState();
    }

    public bool Complete { get; private set; }

    public void Advance()
    {
        if (Complete)
        {
            return;
        }
        if (_stageFrames == 0)
        {
            ConfigureStage(_stageIndex);
        }
        _stageFrames++;
        ObserveStage(_stageIndex);
        UpdateAutomationState();
        if (!StageReady(_stageIndex))
        {
            if (_stageFrames >= MaximumWaitFrames)
            {
                throw new TimeoutException(
                    $"Camera handling stage '{StageNames[_stageIndex]}' did not settle.");
            }
            return;
        }

        ValidateStage(_stageIndex);
        GD.Print(
            $"CANNONBALL_CAMERA_HANDLING_STAGE_OK stage={StageNames[_stageIndex]} " +
            $"index={_stageIndex + 1} of={StageNames.Length}");
        _stageIndex++;
        _stageFrames = 0;
        if (_stageIndex < StageNames.Length)
        {
            return;
        }

        Complete = true;
        UpdateAutomationState();
        var snapshot = _vehicle.ChaseCameraRig.CaptureSnapshot();
        GD.Print(
            "CANNONBALL_CAMERA_HANDLING_OK " +
            $"stages={StageNames.Length} horizon_error_deg={snapshot.HorizonRollDegrees:0.000000} " +
            $"collision_compression_m={MaximumCollisionCompression():0.000} " +
            $"collision_oscillation_m={CollisionOscillationMeters():0.000} " +
            $"rebases={_streamer.RebaseCount} edge={_streamer.CurrentEdgeId} " +
            $"mode={_vehicle.CurrentCameraMode}");
    }

    private int FramesPerStage => _review ? ReviewFramesPerStage : ProfileFramesPerStage;

    private void ConfigureStage(int stage)
    {
        switch (stage)
        {
            case 0:
                _vehicle.PlaceForReview(_initialRoadPoint, _initialRoadForward);
                _vehicle.Rotation = new Vector3(
                    Mathf.DegToRad(9),
                    Mathf.DegToRad(24),
                    Mathf.DegToRad(7));
                _vehicle.ChaseCameraRig.SnapToTarget();
                break;
            case 1:
                _vehicle.PlaceForReview(_initialRoadPoint, _initialRoadForward);
                _vehicle.ChaseCameraRig.SnapToTarget();
                BuildCollisionWall();
                break;
            case 2:
                RemoveCollisionWall();
                break;
            case 3:
                _rebaseCountBefore = _streamer.RebaseCount;
                _edgeBeforeRebase = _streamer.CurrentEdgeId;
                var targetDistance = Math.Clamp(
                    _streamer.TotalRouteLengthMeters * 0.72,
                    Math.Min(2_500, _streamer.TotalRouteLengthMeters * 0.5),
                    Math.Max(0, _streamer.TotalRouteLengthMeters - 25));
                _streamer.SetReviewDistance(targetDistance);
                break;
            case 4:
                var resetRoadPoint = _vehicle.TargetRoadPoint;
                var resetRoadForward = _vehicle.TargetRoadForward;
                _vehicle.Freeze = true;
                _vehicle.Position = resetRoadPoint + new Vector3(18, 6, 12);
                _vehicle.Rotation = new Vector3(
                    Mathf.DegToRad(18),
                    Mathf.DegToRad(70),
                    Mathf.DegToRad(32));
                _vehicle.ChaseCameraRig.SnapToTarget();
                _vehicle.RequestResetToRoad(resetRoadPoint, resetRoadForward);
                break;
            case 5:
                _vehicle.Freeze = true;
                var cockpitProbeRotation = _vehicle.Rotation;
                cockpitProbeRotation.X = Mathf.DegToRad(5);
                cockpitProbeRotation.Z = Mathf.DegToRad(-4);
                _vehicle.Rotation = cockpitProbeRotation;
                _vehicle.ChaseCameraRig.SnapToTarget();
                _vehicle.SetCameraMode(cockpit: true);
                break;
        }
    }

    private void ObserveStage(int stage)
    {
        if (stage == 1 && _stageFrames > 2)
        {
            _collisionHitLengths.Add(
                _vehicle.ChaseCameraRig.CaptureSnapshot().SpringHitLengthMeters);
        }
        if (stage == 5)
        {
            if (_vehicle.CurrentCameraMode == "cockpit")
            {
                _cockpitObserved = true;
            }
            if (_stageFrames == Math.Max(2, FramesPerStage / 2))
            {
                _vehicle.SetCameraMode(cockpit: false);
            }
            if (_vehicle.CurrentCameraMode == "chase")
            {
                _chaseObserved = true;
            }
        }
    }

    private bool StageReady(int stage)
    {
        if (stage == 3)
        {
            return _stageFrames >= FramesPerStage &&
                _streamer.ReviewTargetReady &&
                _streamer.IsStreamingSettled;
        }
        return _stageFrames >= FramesPerStage;
    }

    private void ValidateStage(int stage)
    {
        var snapshot = _vehicle.ChaseCameraRig.CaptureSnapshot();
        ValidateAttachedAndLevel(snapshot, StageNames[stage]);
        switch (stage)
        {
            case 0 when snapshot.HeadingLagDegrees > 45:
                throw new InvalidOperationException(
                    "Chase heading failed to settle after the grade/chassis isolation probe.");
            case 1:
                if (MaximumCollisionCompression() < 1.0)
                {
                    throw new InvalidOperationException(
                        "The spring-arm collision probe did not move the camera clear of the obstacle.");
                }
                if (CollisionOscillationMeters() > 0.25)
                {
                    throw new InvalidOperationException(
                        "The spring-arm collision response oscillated by more than 0.25 meters.");
                }
                break;
            case 2 when snapshot.CollisionCompressionMeters > 0.10:
                throw new InvalidOperationException(
                    "The chase camera did not recover its follow distance after occlusion cleared.");
            case 3:
                if (_streamer.RebaseCount <= _rebaseCountBefore)
                {
                    throw new InvalidOperationException(
                        "The route-distance camera probe did not exercise a local-origin rebase.");
                }
                if (string.Equals(_streamer.CurrentEdgeId, _edgeBeforeRebase, StringComparison.Ordinal))
                {
                    throw new InvalidOperationException(
                        "The camera route probe did not cross an authoritative route edge transition.");
                }
                break;
            case 4:
                var expected = _vehicle.TargetRoadPoint + Vector3.Up * 0.78f;
                if (_vehicle.GlobalPosition.DistanceTo(expected) > 3.0f)
                {
                    throw new InvalidOperationException(
                        "Vehicle reset did not restore the camera target to the road pose: " +
                        $"actual={_vehicle.GlobalPosition} expected={expected} " +
                        $"distance_m={_vehicle.GlobalPosition.DistanceTo(expected):0.000} " +
                        $"target={_vehicle.TargetRoadPoint} velocity={_vehicle.LinearVelocity}.");
                }
                break;
            case 5 when !_cockpitObserved || !_chaseObserved ||
                _vehicle.CurrentCameraMode != "chase":
                throw new InvalidOperationException(
                    "Cockpit-to-chase transition did not preserve a valid active camera.");
            case 5:
                var cockpit = _vehicle.CockpitCameraRig.CaptureSnapshot();
                if (!cockpit.VehicleLocal || cockpit.HorizonRollDegrees > 0.2 ||
                    Math.Abs(cockpit.PitchStabilizationDegrees) > 6.01 ||
                    Math.Abs(cockpit.RollStabilizationDegrees) > 6.01)
                {
                    throw new InvalidOperationException(
                        $"Cockpit stabilization exceeded its bounded local contract: {cockpit}.");
                }
                break;
        }
    }

    private static void ValidateAttachedAndLevel(ChaseCameraSnapshot snapshot, string stage)
    {
        if (!snapshot.TopLevel || !snapshot.TargetValid ||
            !double.IsFinite(snapshot.TargetDistanceMeters) ||
            snapshot.TargetDistanceMeters > 15 ||
            snapshot.HorizonRollDegrees > 0.01)
        {
            throw new InvalidOperationException(
                $"Camera detached or lost its stable horizon during '{stage}': {snapshot}.");
        }
    }

    private void BuildCollisionWall()
    {
        var arm = _vehicle.ChaseCameraRig.Arm;
        var wall = new StaticBody3D
        {
            Name = "CameraCollisionProbeWall",
            CollisionLayer = 1,
            CollisionMask = 0,
        };
        wall.AddChild(new CollisionShape3D
        {
            Shape = new BoxShape3D { Size = new Vector3(8, 8, 0.5f) },
        });
        _parent.AddChild(wall);
        wall.GlobalTransform = new Transform3D(
            arm.GlobalBasis,
            arm.GlobalPosition + arm.GlobalBasis.Z.Normalized() * 3.25f);
        _collisionWall = wall;
    }

    private void RemoveCollisionWall()
    {
        _collisionWall?.QueueFree();
        _collisionWall = null;
    }

    private double MaximumCollisionCompression() => _collisionHitLengths.Count == 0
        ? 0
        : _vehicle.ChaseCameraRig.Arm.SpringLength - _collisionHitLengths.Min();

    private double CollisionOscillationMeters() => _collisionHitLengths.Count == 0
        ? 0
        : _collisionHitLengths.Max() - _collisionHitLengths.Min();

    private void UpdateAutomationState()
    {
        var snapshot = _vehicle.ChaseCameraRig.CaptureSnapshot();
        _automationState["complete"] = Complete;
        _automationState["stage"] = Complete ? "complete" : StageNames[_stageIndex];
        _automationState["stage_index"] = Complete ? StageNames.Length : _stageIndex;
        _automationState["stage_count"] = StageNames.Length;
        _automationState["horizon_roll_degrees"] = snapshot.HorizonRollDegrees;
        _automationState["heading_lag_degrees"] = snapshot.HeadingLagDegrees;
        _automationState["collision_compression_m"] = snapshot.CollisionCompressionMeters;
        _automationState["target_distance_m"] = snapshot.TargetDistanceMeters;
        _automationState["camera_mode"] = _vehicle.CurrentCameraMode;
        _automationState["route_edge_id"] = _streamer.CurrentEdgeId;
        _automationState["rebase_count"] = _streamer.RebaseCount;
    }
}
