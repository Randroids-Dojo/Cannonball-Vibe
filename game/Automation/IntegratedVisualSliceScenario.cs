using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game.Automation;

public sealed class IntegratedVisualSliceScenario
{
    private const double MinimumMovingReviewDistanceMeters = 60;
    private const int ReviewStableFrames = 120;
    private readonly CannonballVehicle _vehicle;
    private readonly WorldStreamer _streamer;
    private readonly bool _review;
    private int _stableFrames;

    public IntegratedVisualSliceScenario(
        CannonballVehicle vehicle,
        WorldStreamer streamer,
        bool review)
    {
        _vehicle = vehicle;
        _streamer = streamer;
        _review = review;
    }

    public bool Complete { get; private set; }

    public void Advance()
    {
        if (Complete ||
            _streamer.RouteDistanceMeters < MinimumMovingReviewDistanceMeters ||
            !_streamer.IsStreamingSettled ||
            !_streamer.IsEnvironmentStreamingSettled)
        {
            return;
        }

        var vehicle = _vehicle.VisualRig?.CaptureSnapshot() ??
            throw new InvalidOperationException(
                "Integrated visual slice requires the project-owned Hero GT wrapper.");
        var road = _streamer.CaptureRoadVisualSnapshot();
        var environment = _streamer.CaptureEnvironmentSnapshot();
        Validate(vehicle, road, environment);

        _stableFrames++;
        if (_stableFrames < (_review ? ReviewStableFrames : 3))
        {
            return;
        }

        Complete = true;
        GD.Print(
            "CANNONBALL_INTEGRATED_VISUAL_SLICE_OK " +
            $"vehicle=hero-gt vehicle_semantic_nodes={vehicle.SemanticNodeCount} " +
            $"road={road.ProfileId} road_chunks={road.ChunkCount} " +
            $"road_materials={road.SharedMaterialCount} road_meshes={road.SharedMeshCount} " +
            $"environment={environment.ProfileId} " +
            $"environment_regions={environment.RegionsSeen.Count} " +
            $"environment_chunks={environment.ObservedChunkCount} " +
            $"terrain_ribbons={environment.TerrainRibbonCount} " +
            $"route_distance_m={_streamer.RouteDistanceMeters:0.000} " +
            $"stable_frames={_stableFrames}");
    }

    public void ValidateComplete()
    {
        if (!Complete)
        {
            throw new InvalidOperationException(
                "Integrated visual slice did not resolve all three presentation contracts.");
        }
    }

    private void Validate(
        VehicleVisualSnapshot vehicle,
        RoadVisualSnapshot road,
        EnvironmentStreamSnapshot environment)
    {
        if (_vehicle.UsesGrayboxVisual ||
            !vehicle.ContractResolved ||
            vehicle.SemanticNodeCount != VehicleVisualRig.RequiredSemanticNodes.Length ||
            vehicle.DamageZoneCount != 5)
        {
            throw new InvalidOperationException(
                "Integrated visual slice did not resolve the production Hero GT contract.");
        }
        if (road.ProfileId != "production" ||
            road.ChunkCount < 1 ||
            !road.AllContractsResolved ||
            road.ReflectorCount < 1 ||
            road.BarrierSegmentCount < 1 ||
            road.GuardrailSegmentCount < 1 ||
            road.SharedMaterialCount != 18 ||
            road.SharedMeshCount != 9 ||
            road.RetroreflectiveMaterialCount != 11)
        {
            throw new InvalidOperationException(
                "Integrated visual slice did not resolve the production highway contract.");
        }
        if (environment.ProfileId != "balanced" ||
            environment.LoadedChunks.Count < 1 ||
            environment.ObservedChunkCount < 1 ||
            environment.RegionsSeen.Count < 1 ||
            environment.NearInstanceCount < 1 ||
            environment.MidInstanceCount < 1 ||
            environment.DistantInstanceCount < 1 ||
            environment.TerrainRibbonCount != environment.LoadedChunks.Count ||
            environment.TerrainTriangleCount < 1 ||
            !environment.CollisionFree ||
            environment.CollisionBudget != 0 ||
            environment.NearVisibilityMeters >= environment.MidVisibilityMeters ||
            environment.MidVisibilityMeters >= environment.DistantVisibilityMeters)
        {
            throw new InvalidOperationException(
                "Integrated visual slice did not resolve the balanced regional environment contract.");
        }
    }
}
