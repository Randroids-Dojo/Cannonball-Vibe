using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Cannonball.Game.World.Environments;
using Godot;

namespace Cannonball.Game.Automation;

/// <summary>
/// Drops the car onto the ground either side of the paved edge, on the flat
/// margin and in the ribbon's rising middle band, and requires it to come to
/// rest on the ground rather than fall to the recovery depth. Before the drops it checks the ground contract that every collision
/// chunk and junction seam carries a terrain collider.
/// </summary>
public sealed class OffRoadGroundScenario
{
    private const int SettleMinimumFrames = 120;
    private const int MaximumWaitFrames = 900;
    private const float DropHeightMeters = 1.0f;
    private const float RestingToleranceMeters = 0.45f;
    private const float RestingSpeedMetersPerSecond = 0.25f;
    private const double ProbeAheadMeters = 45;

    /// <summary>Signed metres beyond the paved edge on that side of the road.</summary>
    private static readonly (string Name, double BeyondPavedEdgeMeters)[] Probes =
    [
        ("right-verge", 8),
        ("right-margin-outer", 100),
        ("right-middle-band", 300),
        ("left-verge", -8),
        ("left-margin-outer", -100),
        ("left-middle-band", -300),
    ];

    private readonly Node _parent;
    private readonly CannonballVehicle _vehicle;
    private readonly WorldStreamer _streamer;
    private readonly Node _semanticNode;
    private readonly Godot.Collections.Dictionary _automationState = new();
    private readonly List<double> _restingErrors = [];
    private int _stageIndex;
    private int _stageFrames;
    private int _resetCountAtStart;
    private float _expectedRestingY;
    private GroundContractReport? _contract;

    public OffRoadGroundScenario(Node parent, CannonballVehicle vehicle, WorldStreamer streamer)
    {
        _parent = parent;
        _vehicle = vehicle;
        _streamer = streamer;
        _semanticNode = new Node { Name = "OffRoadGroundScenario" };
        _semanticNode.SetMeta("automation_id", "ground.off-road.scenario");
        _semanticNode.SetMeta("automation_state", _automationState);
        _parent.AddChild(_semanticNode);
        _vehicle.AutopilotEnabled = false;
        _vehicle.SetCameraMode(cockpit: false);
        UpdateAutomationState();
    }

    public bool Complete { get; private set; }

    /// <summary>Stage 0 is the static contract; the drops follow.</summary>
    private int StageCount => Probes.Length + 1;

    public void Advance()
    {
        if (Complete)
        {
            return;
        }
        if (_stageIndex == 0)
        {
            if (!_streamer.IsStreamingSettled)
            {
                if (++_stageFrames >= MaximumWaitFrames)
                {
                    throw new TimeoutException("Streaming did not settle before the ground contract.");
                }
                return;
            }
            _contract = ValidateGroundContract(_streamer);
            if (_contract.CollisionChunkCount == 0)
            {
                throw new InvalidOperationException("No road chunk carried collision at the route start.");
            }
            GD.Print(_contract.Marker());
            _stageIndex++;
            _stageFrames = 0;
            UpdateAutomationState();
            return;
        }

        var probe = Probes[_stageIndex - 1];
        if (_stageFrames == 0)
        {
            ConfigureDrop(probe.BeyondPavedEdgeMeters);
        }
        _stageFrames++;
        UpdateAutomationState();
        if (!DropSettled())
        {
            if (_stageFrames >= MaximumWaitFrames)
            {
                throw new TimeoutException(
                    $"Off-road probe '{probe.Name}' did not come to rest: {Describe()}.");
            }
            return;
        }

        ValidateDrop(probe.Name);
        GD.Print(
            $"CANNONBALL_OFF_ROAD_GROUND_STAGE_OK probe={probe.Name} " +
            $"beyond_paved_edge_m={probe.BeyondPavedEdgeMeters:0.0} " +
            $"resting_error_m={_restingErrors[^1]:0.000} " +
            $"grounded_wheels={_vehicle.GroundedWheelCount} " +
            $"index={_stageIndex} of={StageCount - 1}");
        _stageIndex++;
        _stageFrames = 0;
        if (_stageIndex < StageCount)
        {
            return;
        }

        Complete = true;
        UpdateAutomationState();
        GD.Print(
            "CANNONBALL_OFF_ROAD_GROUND_OK " +
            $"probes={Probes.Length} " +
            $"max_resting_error_m={_restingErrors.Max():0.000} " +
            $"resets={_vehicle.ResetToRoadCount - _resetCountAtStart} " +
            $"collision_chunks={_contract!.CollisionChunkCount} " +
            $"terrain_collision_chunks={_contract.TerrainCollisionChunkCount} " +
            $"collision_seams={_contract.CollisionSeamCount} " +
            $"recovery_depth_m={CannonballVehicle.FallRecoveryDepthMeters:0.0}");
    }

    private void ConfigureDrop(double beyondPavedEdgeMeters)
    {
        var routeDistance = _streamer.RouteDistanceMeters + ProbeAheadMeters;
        var road = _streamer.ProbeRoad(routeDistance);
        var lateral = beyondPavedEdgeMeters >= 0
            ? road.PavedRightMeters + beyondPavedEdgeMeters
            : road.PavedLeftMeters + beyondPavedEdgeMeters;
        var right = road.Forward.Cross(Vector3.Up).Normalized();
        // The collider follows the ribbon's analytic surface, so the expected
        // resting height does too: flat near the road, rising in the middle band.
        var groundY = road.Point.Y + RegionalTerrainRibbon.SurfaceHeight(
            routeDistance,
            _streamer.TotalRouteLengthMeters,
            (float)lateral);
        var point = road.Point + right * (float)lateral + Vector3.Up * DropHeightMeters;
        // PlaceForReview freezes the chassis at the static ride height; releasing
        // it lets the car fall the drop height onto whatever collider is there.
        _vehicle.PlaceForReview(point, road.Forward);
        _vehicle.ResetGroundingTelemetry();
        _vehicle.Freeze = false;
        _resetCountAtStart = _stageIndex == 1 ? _vehicle.ResetToRoadCount : _resetCountAtStart;
        _expectedRestingY = groundY + CannonballVehicle.VisualRigMountHeightMeters;
        _vehicle.ChaseCameraRig.SnapToTarget();
    }

    private bool DropSettled() =>
        _stageFrames >= SettleMinimumFrames &&
        _vehicle.LinearVelocity.Length() < RestingSpeedMetersPerSecond;

    private void ValidateDrop(string probeName)
    {
        if (_vehicle.ResetToRoadCount != _resetCountAtStart)
        {
            throw new InvalidOperationException(
                $"The car fell through the ground on probe '{probeName}' and was reset: {Describe()}.");
        }
        var restingError = Math.Abs(_vehicle.Position.Y - _expectedRestingY);
        _restingErrors.Add(restingError);
        if (restingError > RestingToleranceMeters)
        {
            throw new InvalidOperationException(
                $"The car did not rest on the terrain margin on probe '{probeName}': " +
                $"resting_error_m={restingError:0.000} {Describe()}.");
        }
        if (_vehicle.GroundedWheelCount != 4)
        {
            throw new InvalidOperationException(
                $"Only {_vehicle.GroundedWheelCount} wheels found ground on probe '{probeName}': {Describe()}.");
        }
    }

    private string Describe() =>
        $"position={_vehicle.Position} expected_y={_expectedRestingY:0.000} " +
        $"velocity={_vehicle.LinearVelocity} grounded_wheels={_vehicle.GroundedWheelCount} " +
        $"resets={_vehicle.ResetToRoadCount - _resetCountAtStart} frames={_stageFrames}";

    private void UpdateAutomationState()
    {
        _automationState["stage_index"] = _stageIndex;
        _automationState["stage_count"] = StageCount;
        _automationState["complete"] = Complete;
        _automationState["resets"] = _vehicle.ResetToRoadCount - _resetCountAtStart;
        _automationState["grounded_wheels"] = _vehicle.GroundedWheelCount;
        if (_contract is { } contract)
        {
            _automationState["collision_chunks"] = contract.CollisionChunkCount;
            _automationState["terrain_collision_chunks"] = contract.TerrainCollisionChunkCount;
            _automationState["collision_seams"] = contract.CollisionSeamCount;
        }
    }

    /// <summary>
    /// The ground contract for the loaded world: every road chunk and junction
    /// seam with collision also carries its terrain collider, so a car that
    /// leaves the paved edge lands on the margin wherever the road collides.
    /// </summary>
    public static GroundContractReport ValidateGroundContract(WorldStreamer streamer)
    {
        ArgumentNullException.ThrowIfNull(streamer);
        var chunks = streamer.LoadedRoadChunks;
        var collisionChunks = chunks.Count(chunk => chunk.HasCollision);
        var terrainCollisionChunks = chunks.Count(chunk => chunk.HasCollision && chunk.HasTerrainCollision);
        if (terrainCollisionChunks != collisionChunks)
        {
            throw new InvalidOperationException(
                $"{collisionChunks - terrainCollisionChunks} of {collisionChunks} collision chunks " +
                "have no terrain collider.");
        }
        var seams = streamer.LoadedJunctionSeams;
        var collisionSeams = seams.Count(seam => seam.HasCollision);
        var terrainCollisionSeams = seams.Count(seam => seam.HasCollision && seam.HasTerrainCollision);
        if (terrainCollisionSeams != collisionSeams)
        {
            throw new InvalidOperationException(
                $"{collisionSeams - terrainCollisionSeams} of {collisionSeams} collision junction seams " +
                "have no terrain collider.");
        }
        return new GroundContractReport(collisionChunks, terrainCollisionChunks, collisionSeams);
    }
}

public sealed record GroundContractReport(
    int CollisionChunkCount,
    int TerrainCollisionChunkCount,
    int CollisionSeamCount)
{
    public string Marker() =>
        "CANNONBALL_GROUND_CONTRACT_OK " +
        $"collision_chunks={CollisionChunkCount} " +
        $"terrain_collision_chunks={TerrainCollisionChunkCount} " +
        $"collision_seams={CollisionSeamCount}";
}
