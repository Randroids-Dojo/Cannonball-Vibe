using Cannonball.Game.World;
using Cannonball.Game.World.Environments;
using Godot;

namespace Cannonball.Game.Automation;

public sealed class RoadVisualScenario
{
    private const int ReviewFramesPerStage = 90;
    private static readonly string[] StageNames = ["daylight", "night-retroreflective"];
    private readonly WorldStreamer _streamer;
    private readonly DirectionalLight3D _light;
    private readonly Godot.Environment _environment;
    private readonly bool _review;
    private readonly Camera3D? _reviewCamera;
    private int _stageIndex;
    private int _stageFrames;
    private bool _reviewTargetSet;

    public RoadVisualScenario(
        WorldStreamer streamer,
        DirectionalLight3D light,
        WorldEnvironment environment,
        Camera3D? reviewCamera,
        bool review)
    {
        _streamer = streamer;
        _light = light;
        _environment = environment.Environment ??
            throw new InvalidOperationException("Road visual scenario requires an environment.");
        _review = review;
        _reviewCamera = reviewCamera;
        SetLighting(daylight: true);
    }

    public bool Complete { get; private set; }
    public int CompletedStageCount { get; private set; }

    public void Advance()
    {
        if (Complete)
        {
            return;
        }
        var daylight = _stageIndex == 0;
        SetLighting(daylight);
        if (_review && !_reviewTargetSet)
        {
            if (!_streamer.SetRoadStructureReviewTarget())
            {
                throw new InvalidOperationException(
                    "Road visual review could not resolve a structure on the selected route.");
            }
            _reviewTargetSet = true;
        }
        if (_review && (!_streamer.ReviewTargetReady || !_streamer.IsStreamingSettled))
        {
            return;
        }
        if (_review && (_reviewCamera is null ||
            !_streamer.ConfigureRoadStructureReviewCamera(_reviewCamera)))
        {
            throw new InvalidOperationException(
                "Road visual review could not frame the generated grade-separated structure.");
        }
        _stageFrames++;
        if (_stageFrames < (_review ? ReviewFramesPerStage : 3))
        {
            return;
        }
        ValidateStage(daylight);
        GD.Print(
            $"CANNONBALL_ROAD_VISUAL_LIGHTING_STAGE_OK stage={StageNames[_stageIndex]} " +
            $"index={_stageIndex + 1} of={StageNames.Length}");
        CompletedStageCount++;
        _stageIndex++;
        _stageFrames = 0;
        if (_stageIndex < StageNames.Length)
        {
            return;
        }
        Complete = true;
        GD.Print(
            $"CANNONBALL_ROAD_VISUAL_LIGHTING_OK stages={CompletedStageCount} " +
            "daylight=1 night=1");
    }

    private void ValidateStage(bool daylight)
    {
        var snapshot = _streamer.CaptureRoadVisualSnapshot();
        if (!snapshot.StructureContractResolved || snapshot.StructureCount < 1 ||
            snapshot.BridgeDeckCount < 1 || snapshot.OverpassOpeningCount < 1 ||
            snapshot.RetroreflectiveMaterialCount < 1 ||
            !snapshot.SignageContractResolved || snapshot.GuideSignCount < 1 ||
            snapshot.StandardRouteShieldCount != snapshot.RouteShieldCount ||
            snapshot.GeometricLaneArrowCount != snapshot.GuideSignCount)
        {
            throw new InvalidOperationException(
                "Road visual lighting stage did not resolve structures and reflective materials: " +
                $"structures={snapshot.StructureCount}, bridge_decks={snapshot.BridgeDeckCount}, " +
                $"overpass_openings={snapshot.OverpassOpeningCount}, " +
                $"contract={snapshot.StructureContractResolved}, " +
                $"retroreflective={snapshot.RetroreflectiveMaterialCount}, " +
                $"signage_contract={snapshot.SignageContractResolved}, " +
                $"guide_signs={snapshot.GuideSignCount}, " +
                $"standard_shields={snapshot.StandardRouteShieldCount}, " +
                $"geometric_lane_arrows={snapshot.GeometricLaneArrowCount}.");
        }
        var expectedPreset = daylight ? LightingPreset.Day : LightingPreset.Night;
        if (!SkyLighting.Matches(_light, _environment, expectedPreset))
        {
            throw new InvalidOperationException(
                $"Road visual {StageNames[_stageIndex]} lighting contract drifted.");
        }
    }

    private void SetLighting(bool daylight) =>
        SkyLighting.Apply(_light, _environment, daylight ? LightingPreset.Day : LightingPreset.Night);
}
