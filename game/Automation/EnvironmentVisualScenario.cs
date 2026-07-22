using Cannonball.Game.World;
using Cannonball.Game.World.Environments;
using Godot;

namespace Cannonball.Game.Automation;

public sealed class EnvironmentVisualScenario
{
    private const int ReviewFramesPerStage = 90;
    private static readonly Stage[] Stages =
    [
        new("mountain-dawn", 0.08, EnvironmentRegion.Mountain, Lighting.Dawn),
        new("foothill-day", 0.36, EnvironmentRegion.Foothill, Lighting.Day),
        new("plains-weather", 0.62, EnvironmentRegion.Plains, Lighting.Overcast),
        new("urban-edge-night", 0.88, EnvironmentRegion.UrbanEdge, Lighting.Night),
        new("stream-boundary-day", 0.50, EnvironmentRegion.Plains, Lighting.Day),
    ];

    private readonly WorldStreamer _streamer;
    private readonly DirectionalLight3D _light;
    private readonly Godot.Environment _environment;
    private readonly bool _review;
    private int _stageIndex;
    private int _stageFrames;
    private bool _stageTargetSet;

    public EnvironmentVisualScenario(
        WorldStreamer streamer,
        DirectionalLight3D light,
        WorldEnvironment environment,
        bool review)
    {
        _streamer = streamer;
        _light = light;
        _environment = environment.Environment ??
            throw new InvalidOperationException(
                "Environment visual scenario requires a world environment.");
        _review = review;
    }

    public bool Complete { get; private set; }
    public int CompletedStageCount { get; private set; }

    public void Advance()
    {
        if (Complete)
        {
            return;
        }
        var stage = Stages[_stageIndex];
        if (!_stageTargetSet)
        {
            _streamer.SetReviewDistance(
                _streamer.TotalRouteLengthMeters * stage.RouteFraction);
            SetLighting(stage.Lighting);
            _stageTargetSet = true;
        }
        if (!_streamer.ReviewTargetReady || !_streamer.IsStreamingSettled ||
            !_streamer.IsEnvironmentStreamingSettled)
        {
            return;
        }
        _stageFrames++;
        if (_stageFrames < (_review ? ReviewFramesPerStage : 3))
        {
            return;
        }

        ValidateStage(stage);
        GD.Print(
            $"CANNONBALL_ENVIRONMENT_STAGE_OK stage={stage.Name} " +
            $"region={stage.Region.ToString().ToLowerInvariant()} " +
            $"lighting={stage.Lighting.ToString().ToLowerInvariant()} " +
            $"index={_stageIndex + 1} of={Stages.Length}");
        CompletedStageCount++;
        _stageIndex++;
        _stageFrames = 0;
        _stageTargetSet = false;
        if (_stageIndex < Stages.Length)
        {
            return;
        }

        var snapshot = _streamer.CaptureEnvironmentSnapshot();
        var missingRegions = Enum.GetValues<EnvironmentRegion>()
            .Where(region => !snapshot.RegionsSeen.Contains(region))
            .ToArray();
        if (missingRegions.Length > 0)
        {
            throw new InvalidOperationException(
                $"Environment scenario did not stream regions: {string.Join(",", missingRegions)}.");
        }
        Complete = true;
        GD.Print(
            $"CANNONBALL_ENVIRONMENT_OK profile={snapshot.ProfileId} " +
            $"stages={CompletedStageCount} regions={snapshot.RegionsSeen.Count} " +
            $"observed_chunks={snapshot.ObservedChunkCount} " +
            $"near_instances={snapshot.NearInstanceCount} " +
            $"mid_instances={snapshot.MidInstanceCount} " +
            $"distant_instances={snapshot.DistantInstanceCount} " +
            $"semantic_nodes={snapshot.SemanticNodeCount} " +
            $"shared_materials={snapshot.SharedMaterialCount} " +
            $"shared_meshes={snapshot.SharedMeshCount} " +
            $"collision_free={snapshot.CollisionFree} " +
            $"collision_budget={snapshot.CollisionBudget} " +
            $"rebases={_streamer.RebaseCount} " +
            $"max_build_ms={snapshot.MaximumBuildMilliseconds:0.000}");
    }

    private void ValidateStage(Stage stage)
    {
        var snapshot = _streamer.CaptureEnvironmentSnapshot();
        if (!snapshot.CollisionFree || snapshot.CollisionBudget != 0 ||
            snapshot.LoadedChunks.Count == 0 ||
            snapshot.NearInstanceCount == 0 || snapshot.MidInstanceCount == 0 ||
            snapshot.DistantInstanceCount == 0 || snapshot.SemanticNodeCount == 0 ||
            snapshot.SharedMaterialCount < 7 || snapshot.SharedMeshCount < 6 ||
            snapshot.LoadedChunks.All(chunk => chunk.Region != stage.Region))
        {
            throw new InvalidOperationException(
                $"Environment stage '{stage.Name}' did not satisfy its streaming contract: " +
                $"loaded={snapshot.LoadedChunks.Count}, region={stage.Region}, " +
                $"near={snapshot.NearInstanceCount}, mid={snapshot.MidInstanceCount}, " +
                $"distant={snapshot.DistantInstanceCount}, semantic={snapshot.SemanticNodeCount}, " +
                $"collision_free={snapshot.CollisionFree}.");
        }
        var expected = LightingValues(stage.Lighting);
        if (!_environment.BackgroundColor.IsEqualApprox(expected.Background) ||
            !Mathf.IsEqualApprox(_light.LightEnergy, expected.Energy))
        {
            throw new InvalidOperationException(
                $"Environment stage '{stage.Name}' lighting contract drifted.");
        }
    }

    private void SetLighting(Lighting lighting)
    {
        var values = LightingValues(lighting);
        _light.LightColor = values.Light;
        _light.LightEnergy = values.Energy;
        _light.RotationDegrees = new Vector3(values.PitchDegrees, -28, 0);
        _environment.BackgroundColor = values.Background;
        _environment.AmbientLightColor = values.Ambient;
        _environment.AmbientLightEnergy = values.AmbientEnergy;
    }

    private static LightingState LightingValues(Lighting lighting) => lighting switch
    {
        Lighting.Dawn => new(
            new Color("f6b982"), 1.15f, -9, new Color("8b6d78"), new Color("b58a8b"), 0.62f),
        Lighting.Day => new(
            new Color("fff2d6"), 1.8f, -48, new Color("78a7d8"), new Color("dbe8f6"), 0.8f),
        Lighting.Overcast => new(
            new Color("d8e0e5"), 0.72f, -54, new Color("687683"), new Color("a7b2b9"), 0.92f),
        Lighting.Night => new(
            new Color("a9c4ff"), 1.3f, -24, new Color("060912"), new Color("425072"), 0.45f),
        _ => throw new ArgumentOutOfRangeException(nameof(lighting)),
    };

    private enum Lighting
    {
        Dawn,
        Day,
        Overcast,
        Night,
    }

    private sealed record Stage(
        string Name,
        double RouteFraction,
        EnvironmentRegion Region,
        Lighting Lighting);

    private sealed record LightingState(
        Color Light,
        float Energy,
        float PitchDegrees,
        Color Background,
        Color Ambient,
        float AmbientEnergy);
}
