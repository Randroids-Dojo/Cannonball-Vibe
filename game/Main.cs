using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Saves;
using Cannonball.Core.Telemetry;
using Cannonball.Game.Automation;
using Cannonball.Game.UI;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game;

public sealed partial class Main : Node3D
{
    private const int MaximumTransportProbeReads = 10_000;
    private const int MaximumRenderIntegrityUnsupportedPhysicsFrames = 30;
    private const double MinimumRenderIntegrityWellGroundedRatio = 0.90;
    private const int GeographicReviewFramesPerWaypoint = 90;
    private const int StreamingStableFramesPerCheckpoint = 5;
    private const float TopologyHighSpeedTargetMetersPerSecond = 60;
    private const float RouteChoiceTraversalSpeedMetersPerSecond = 20;
    private static readonly double[] GeographicReviewFractions =
        [0.005, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.995];
    private static readonly double[] StreamingCheckpointFractions =
        [0.0, 0.2, 0.4, 0.6, 0.8, 0.995];
    private WorldStreamer _streamer = null!;
    private CannonballVehicle _vehicle = null!;
    private PrototypeHud _hud = null!;
    private JsonRunStateRepository _saves = null!;
    private JsonlTelemetrySink _telemetry = null!;
    private RouteContentPackage _package = null!;
    private IRouteChunkContentSource _chunkSource = null!;
    private Task<TransportProbeResult>? _transportProbe;
    private bool _transportProbeReported;
    private bool _smokeTest;
    private bool _stressTest;
    private bool _shortCorridorSoak;
    private bool _renderIntegrity;
    private bool _geographicReview;
    private bool _streamingProfile;
    private bool _topologyProfile;
    private bool _topologyReview;
    private bool _routeChoiceProfile;
    private bool _shutdownStarted;
    private int _smokeFrames;
    private double _telemetryElapsed;
    private double _previousDistance;
    private float _peakSpeedMetersPerSecond;
    private int _smokeTargetFrames = 360;
    private bool _renderTraversalStarted;
    private int _minimumLoadedChunksDuringRenderTraversal = int.MaxValue;
    private int _geographicReviewWaypointIndex = -1;
    private int _geographicReviewStableFrames;
    private bool _geographicReviewComplete;
    private int _streamingCheckpointIndex = -1;
    private int _streamingStableFrames;
    private bool _streamingProfileComplete;
    private VariableLaneTopologyOverlay? _topologyOverlay;
    private IReadOnlyList<double> _topologyCheckpoints = [];
    private int _topologyCheckpointIndex = -1;
    private int _topologyStableFrames;
    private bool _topologyProfileComplete;
    private bool _topologyTraversalPreparing;
    private bool _topologyTraversalStarted;
    private double _topologyTraversalStartMeters;
    private double _topologyTraversalEndMeters;
    private Camera3D? _topologyDiagnosticCamera;
    private int _topologyReviewWaypointIndex;
    private int _topologyReviewFrames;
    private RepresentativeInterchangeFixtureData? _interchangeFixture;
    private static readonly string[] RouteChoicePlanOrder =
    [
        RepresentativeInterchangeFixture.StayPlanId,
        RepresentativeInterchangeFixture.ExitPlanId,
        RepresentativeInterchangeFixture.TransferPlanId,
    ];
    private int _routeChoicePlanIndex;
    private int _routeChoiceTransitionIndex;
    private int _routeChoiceStableFrames;
    private bool _routeChoiceTraversing;
    private bool _routeChoiceFinishingPlan;
    private bool _routeChoiceUnsupportedReported;
    private bool _routeChoiceBeforeSaved;
    private bool _routeChoiceInsideSaved;
    private bool _routeChoiceProfileComplete;
    private int _routeChoiceSaveResumeCount;
    private readonly HashSet<string> _routeChoiceConnectorsObserved = new(StringComparer.Ordinal);
    private readonly HashSet<string> _routeChoiceBranchPrewarms = new(StringComparer.Ordinal);
    private readonly HashSet<string> _routeChoiceBranchEvictions = new(StringComparer.Ordinal);
    private double _routeChoiceMaximumBuildMilliseconds;
    private double _routeChoiceMaximumCollisionBuildMilliseconds;
    private int _routeChoiceMaximumUnsupportedFrames;
    private int _routeChoiceChunkFailures;

    public override void _Ready()
    {
        try
        {
            var arguments = OS.GetCmdlineUserArgs();
            var routePath = RequiredArgument(arguments, "--route-package");
            var requestedProbeMiles = OptionalPositiveDouble(arguments, "--distance-miles");
            _smokeTest = arguments.Contains("--smoke-test", StringComparer.Ordinal) || requestedProbeMiles > 0;
            _stressTest = arguments.Contains("--stress-driver", StringComparer.Ordinal);
            _shortCorridorSoak = arguments.Contains("--short-corridor-soak", StringComparer.Ordinal);
            _renderIntegrity = arguments.Contains("--render-integrity", StringComparer.Ordinal);
            _geographicReview = arguments.Contains("--geographic-review", StringComparer.Ordinal);
            _streamingProfile = arguments.Contains("--streaming-profile", StringComparer.Ordinal);
            _topologyProfile = arguments.Contains("--topology-profile", StringComparer.Ordinal);
            _topologyReview = arguments.Contains("--topology-review", StringComparer.Ordinal);
            _routeChoiceProfile = arguments.Contains("--route-choice-profile", StringComparer.Ordinal);
            _smokeTest = _smokeTest || _stressTest || _shortCorridorSoak || _renderIntegrity ||
                _geographicReview || _streamingProfile || _topologyProfile || _topologyReview ||
                _routeChoiceProfile;
            _smokeTargetFrames = _stressTest || _shortCorridorSoak ? 3_600 : 360;
            if (_renderIntegrity)
            {
                _smokeTargetFrames = 4_800;
            }
            if (_geographicReview)
            {
                _smokeTargetFrames = 7_200;
            }
            if (_streamingProfile || _topologyProfile)
            {
                _smokeTargetFrames = 7_200;
            }
            if (_routeChoiceProfile)
            {
                _smokeTargetFrames = 14_400;
            }
            if (_topologyReview)
            {
                _smokeTargetFrames = 480;
            }

            var absoluteRoutePath = Path.GetFullPath(routePath);
            var sourcePackage = FlatBufferRouteContent.Load(absoluteRoutePath);
            _package = sourcePackage;
            if (_routeChoiceProfile)
            {
                _interchangeFixture = RepresentativeInterchangeFixture.Create(sourcePackage);
                _package = _interchangeFixture.Package;
                _chunkSource = _interchangeFixture.Source;
            }
            else if (_topologyProfile || _topologyReview)
            {
                _topologyOverlay = VariableLaneTopologyFixture.Apply(_package);
                _package = _topologyOverlay.Package;
            }
            if (!_routeChoiceProfile)
            {
                _chunkSource = new VerifiedFileChunkSource(
                    _package,
                    Path.GetDirectoryName(absoluteRoutePath)
                        ?? throw new InvalidDataException("Route package has no parent directory."));
            }

            ConfigureInputMap();
            BuildLighting();
            ConfigureRuntimeWorld(_interchangeFixture is null
                ? null
                : _interchangeFixture.Plans[RouteChoicePlanOrder[0]]);
            if (_topologyReview)
            {
                _topologyDiagnosticCamera = new Camera3D
                {
                    Name = "TopologyDiagnosticCamera",
                    Current = false,
                    Fov = 68,
                };
                AddChild(_topologyDiagnosticCamera);
            }
            _hud = new PrototypeHud { Name = "PrototypeHud" };
            AddChild(_hud);

            _saves = new JsonRunStateRepository(
                ProjectSettings.GlobalizePath("user://runs/suspended-run.json"),
                _package.Graph.ContentVersion);
            _telemetry = new JsonlTelemetrySink(
                ProjectSettings.GlobalizePath("user://telemetry/prototype.jsonl"));

            _vehicle.AutopilotEnabled = _smokeTest && !_renderIntegrity && !_streamingProfile &&
                !_topologyProfile && !_topologyReview && !_routeChoiceProfile;
            if (_geographicReview)
            {
                _vehicle.AutopilotEnabled = false;
                BeginNextGeographicReviewWaypoint();
            }
            if (_streamingProfile)
            {
                BeginNextStreamingCheckpoint();
            }
            if (_topologyOverlay is not null)
            {
                ConfigureTopologyCheckpoints();
                if (_topologyProfile)
                {
                    BeginNextTopologyCheckpoint();
                }
                else if (_topologyReview)
                {
                    BeginTopologyReviewWaypoint();
                }
            }
            if (_routeChoiceProfile)
            {
                BeginNextRouteChoiceTransition();
            }
            if (_renderIntegrity)
            {
                _vehicle.AutopilotSpeedLimitMetersPerSecond = 12;
            }
            var assistArgument = arguments.FirstOrDefault(value => value.StartsWith("--assist=", StringComparison.Ordinal));
            if (assistArgument is not null &&
                Enum.TryParse<AssistProfile>(assistArgument["--assist=".Length..], ignoreCase: true, out var assist))
            {
                _vehicle.SetAssistProfile(assist);
            }
            if (requestedProbeMiles > 0)
            {
                _transportProbe = RunTransportProbeAsync(requestedProbeMiles);
            }

            GD.Print(
                $"CANNONBALL_READY engine={Engine.GetVersionInfo()["string"]} " +
                $"physics_hz={Engine.PhysicsTicksPerSecond} " +
                $"content_source=packaged content_version={_package.Graph.ContentVersion}");
        }
        catch (Exception exception)
        {
            GD.PushError(exception.ToString());
            GetTree().Quit(1);
        }
    }

    public override void _Process(double delta)
    {
        if (_streamer is null || _vehicle is null || _hud is null)
        {
            return;
        }

        if (!ReportTransportProbeWhenComplete())
        {
            return;
        }

        _hud.UpdateTelemetry(
            _vehicle.SpeedMetersPerSecond,
            _streamer.RouteDistanceMeters,
            _streamer.LoadedChunkCount,
            _streamer.LocalOriginMeters,
            _vehicle.AssistProfile);
        _peakSpeedMetersPerSecond = Math.Max(_peakSpeedMetersPerSecond, _vehicle.SpeedMetersPerSecond);
        if (_renderIntegrity)
        {
            if (!_renderTraversalStarted &&
                _streamer.LoadedChunkCount == _streamer.ExpectedChunkCount &&
                _streamer.ReviewReadyChunkCount == _streamer.ExpectedChunkCount)
            {
                _renderTraversalStarted = true;
                _vehicle.ResetGroundingTelemetry();
                _vehicle.AutopilotEnabled = true;
            }
            if (_renderTraversalStarted)
            {
                _minimumLoadedChunksDuringRenderTraversal = Math.Min(
                    _minimumLoadedChunksDuringRenderTraversal,
                    _streamer.LoadedChunkCount);
            }
        }
        if (_geographicReview && !_geographicReviewComplete)
        {
            AdvanceGeographicReview();
        }
        if (_streamingProfile && !_streamingProfileComplete)
        {
            AdvanceStreamingProfile();
        }
        if (_topologyProfile && !_topologyProfileComplete)
        {
            AdvanceTopologyProfile();
        }
        if (_topologyReview)
        {
            AdvanceTopologyReview();
        }
        if (_routeChoiceProfile && !_routeChoiceProfileComplete)
        {
            AdvanceRouteChoiceProfile();
        }
        _telemetryElapsed += delta;
        if (_telemetryElapsed >= 5)
        {
            _telemetryElapsed = 0;
            _ = RecordTelemetryAsync("pace_sample");
        }

        if (Godot.Input.IsActionJustPressed("suspend_run"))
        {
            _ = PersistAsync(quitAfterSave: false);
        }

        if (Godot.Input.IsActionJustPressed("cycle_assist"))
        {
            _vehicle.CycleAssistProfile();
        }

        if (!_smokeTest || _shutdownStarted)
        {
            return;
        }

        _smokeFrames++;
        var renderTraversalComplete = _renderIntegrity &&
            _streamer.RouteDistanceMeters >= Math.Min(300, _streamer.TotalRouteLengthMeters - 35);
        if (_smokeFrames >= _smokeTargetFrames || renderTraversalComplete ||
            _geographicReviewComplete || _streamingProfileComplete || _topologyProfileComplete ||
            _routeChoiceProfileComplete)
        {
            _shutdownStarted = true;
            _ = PersistAsync(quitAfterSave: true);
        }
    }

    public override void _ExitTree()
    {
        if (_telemetry is not null)
        {
            _telemetry.DisposeAsync().AsTask().GetAwaiter().GetResult();
        }
    }

    private void ConfigureRuntimeWorld(ValidatedRoutePlan? routePlan)
    {
        var routePlanEdgeIds = routePlan?.LinearPlan.EdgeIds;
        var initialManifest = WorldStreamer.FindInitialManifest(_package, routePlanEdgeIds);
        var initialChunk = _chunkSource.LoadChunk(initialManifest.Id);
        _streamer = new WorldStreamer { Name = "WorldStreamer" };
        _streamer.Configure(
            _package,
            _chunkSource,
            initialChunk,
            routePlanEdgeIds,
            routePlan?.Selection.ConnectorIds);
        _streamer.ShortCorridorLoopEnabled = _shortCorridorSoak;
        AddChild(_streamer);
        _vehicle = new CannonballVehicle
        {
            Transform = new Transform3D(
                Basis.LookingAt(_streamer.InitialRoadForward, Vector3.Up),
                _streamer.InitialRoadPoint + Vector3.Up * 0.78f),
        };
        AddChild(_vehicle);
        _streamer.Track(_vehicle);
    }

    private void ReplaceRuntimeWorld(ValidatedRoutePlan plan)
    {
        _streamer.ProcessMode = ProcessModeEnum.Disabled;
        _vehicle.ProcessMode = ProcessModeEnum.Disabled;
        RemoveChild(_vehicle);
        _vehicle.QueueFree();
        RemoveChild(_streamer);
        _streamer.QueueFree();
        ConfigureRuntimeWorld(plan);
        _vehicle.AutopilotEnabled = false;
    }

    private ValidatedRoutePlan ActiveRouteChoicePlan =>
        _interchangeFixture?.Plans[RouteChoicePlanOrder[Math.Min(
            _routeChoicePlanIndex,
            RouteChoicePlanOrder.Length - 1)]]
        ?? throw new InvalidOperationException("Representative interchange fixture is not configured.");

    private void BeginNextRouteChoiceTransition()
    {
        var plan = ActiveRouteChoicePlan;
        if (_routeChoiceTransitionIndex >= plan.Transitions.Count)
        {
            BeginRouteChoicePlanCompletion();
            return;
        }
        var transition = plan.Transitions[_routeChoiceTransitionIndex];
        var fromEdge = _package.Graph.GetEdge(transition.FromEdgeId);
        var crossingDistance = _streamer.GetRouteDistance(fromEdge.Id, fromEdge.LengthMeters);
        var approachLength = transition.ConnectorId is
            "connector-exit-crossroad" or "connector-transfer-merge"
            ? 15
            : Math.Min(70, fromEdge.LengthMeters * 0.35);
        var approachDistance = Math.Max(
            _streamer.GetRouteDistance(fromEdge.Id, 0),
            crossingDistance - approachLength);
        _routeChoiceStableFrames = 0;
        _routeChoiceTraversing = false;
        _routeChoiceUnsupportedReported = false;
        _vehicle.AutopilotEnabled = false;
        _streamer.SetReviewPosition(approachDistance, transition.FromLaneId);
    }

    private void AdvanceRouteChoiceProfile()
    {
        if (_routeChoiceFinishingPlan)
        {
            if (!_streamer.ReviewTargetReady || !_streamer.IsStreamingSettled)
            {
                _routeChoiceStableFrames = 0;
                return;
            }
            _routeChoiceStableFrames++;
            if (_routeChoiceStableFrames >= StreamingStableFramesPerCheckpoint)
            {
                CompleteRouteChoicePlan();
            }
            return;
        }
        var plan = ActiveRouteChoicePlan;
        var transition = plan.Transitions[_routeChoiceTransitionIndex];
        if (!_routeChoiceTraversing)
        {
            if (!_streamer.ReviewTargetReady || !_streamer.IsStreamingSettled)
            {
                _routeChoiceStableFrames = 0;
                return;
            }
            _routeChoiceStableFrames++;
            if (_routeChoiceStableFrames < StreamingStableFramesPerCheckpoint)
            {
                return;
            }
            _streamer.ValidateCurrentStreamingWindows();
            if (!_routeChoiceBeforeSaved)
            {
                VerifyRouteChoiceSaveResume("before");
                _routeChoiceBeforeSaved = true;
            }
            _vehicle.ResetGroundingTelemetry();
            _vehicle.AutopilotSpeedLimitMetersPerSecond = transition.ConnectorId is
                "connector-exit-crossroad" or "connector-transfer-merge"
                ? 8
                : RouteChoiceTraversalSpeedMetersPerSecond;
            _vehicle.AutopilotEnabled = true;
            _streamer.BeginReviewTraversal();
            _routeChoiceTraversing = true;
            return;
        }

        if (!_routeChoiceUnsupportedReported &&
            _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames >
                MaximumRenderIntegrityUnsupportedPhysicsFrames)
        {
            _routeChoiceUnsupportedReported = true;
            GD.Print(
                $"CANNONBALL_ROUTE_SUPPORT_DIAGNOSTIC plan={plan.Selection.Id} " +
                $"connector={transition.ConnectorId} edge={_streamer.CurrentEdgeId} " +
                $"edge_distance_m={_streamer.CurrentEdgeDistanceMeters:0.000} " +
                $"lateral_m={_streamer.CurrentLateralOffsetMeters:0.000} " +
                $"vehicle=({_vehicle.Position.X:0.000},{_vehicle.Position.Y:0.000}," +
                $"{_vehicle.Position.Z:0.000}) target=({_vehicle.TargetRoadPoint.X:0.000}," +
                $"{_vehicle.TargetRoadPoint.Y:0.000},{_vehicle.TargetRoadPoint.Z:0.000})");
        }

        if (!_streamer.ObservedConnectorIds.Contains(transition.ConnectorId, StringComparer.Ordinal))
        {
            return;
        }
        var targetEdge = _package.Graph.GetEdge(transition.ToEdgeId);
        var targetDistance = _streamer.GetRouteDistance(transition.ToEdgeId, 0) +
            Math.Min(5, targetEdge.LengthMeters * 0.05);
        if (_streamer.RouteDistanceMeters < targetDistance)
        {
            return;
        }
        if (_vehicle.GroundedWheelCount == 0)
        {
            return;
        }
        _vehicle.AutopilotEnabled = false;
        if (!_vehicle.HasBeenGrounded)
        {
            throw new InvalidOperationException(
                $"Route-choice traversal crossed '{transition.ConnectorId}' without road contact.");
        }
        _routeChoiceMaximumUnsupportedFrames = Math.Max(
            _routeChoiceMaximumUnsupportedFrames,
            _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames);
        _routeChoiceConnectorsObserved.Add(transition.ConnectorId);
        if (!_routeChoiceInsideSaved &&
            (transition.Movement is JunctionMovement.Exit or JunctionMovement.HighwayTransfer ||
                _routeChoiceTransitionIndex == 0))
        {
            VerifyRouteChoiceSaveResume("inside");
            _routeChoiceInsideSaved = true;
        }
        GD.Print(
            $"CANNONBALL_ROUTE_CHOICE_OK plan={plan.Selection.Id} " +
            $"connector={transition.ConnectorId} movement={transition.Movement} " +
            $"to_edge={transition.ToEdgeId} " +
            $"max_unsupported_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames}");
        _routeChoiceTransitionIndex++;
        BeginNextRouteChoiceTransition();
    }

    private void BeginRouteChoicePlanCompletion()
    {
        _vehicle.AutopilotEnabled = false;
        _routeChoiceTraversing = false;
        _routeChoiceFinishingPlan = true;
        _routeChoiceStableFrames = 0;
        _streamer.SetReviewDistance(Math.Max(0, _streamer.TotalRouteLengthMeters - 1));
    }

    private void CompleteRouteChoicePlan()
    {
        var plan = ActiveRouteChoicePlan;
        VerifyRouteChoiceSaveResume("after");
        AccumulateRouteChoiceRuntimeMetrics();
        GD.Print(
            $"CANNONBALL_ROUTE_PLAN_OK plan={plan.Selection.Id} " +
            $"edges={plan.Selection.EdgeIds.Count} connectors={plan.Transitions.Count} " +
            $"branch_prewarms={_streamer.BranchPrewarmCount} " +
            $"branch_evictions={_streamer.BranchPrewarmEvictionCount}");
        _routeChoicePlanIndex++;
        _routeChoiceTransitionIndex = 0;
        _routeChoiceBeforeSaved = false;
        _routeChoiceInsideSaved = false;
        _routeChoiceFinishingPlan = false;
        if (_routeChoicePlanIndex >= RouteChoicePlanOrder.Length)
        {
            _routeChoiceProfileComplete = true;
            _vehicle.AutopilotEnabled = false;
            return;
        }
        ReplaceRuntimeWorld(ActiveRouteChoicePlan);
        BeginNextRouteChoiceTransition();
    }

    private void AccumulateRouteChoiceRuntimeMetrics()
    {
        foreach (var chunkId in _streamer.PrewarmedBranchChunkIds)
        {
            _routeChoiceBranchPrewarms.Add(chunkId);
        }
        foreach (var chunkId in _streamer.EvictedBranchChunkIds)
        {
            _routeChoiceBranchEvictions.Add(chunkId);
        }
        _routeChoiceMaximumBuildMilliseconds = Math.Max(
            _routeChoiceMaximumBuildMilliseconds,
            _streamer.MaximumBuildMilliseconds);
        _routeChoiceMaximumCollisionBuildMilliseconds = Math.Max(
            _routeChoiceMaximumCollisionBuildMilliseconds,
            _streamer.MaximumCollisionBuildMilliseconds);
        _routeChoiceMaximumUnsupportedFrames = Math.Max(
            _routeChoiceMaximumUnsupportedFrames,
            _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames);
        _routeChoiceChunkFailures += _streamer.ChunkFailureCount;
    }

    private void VerifyRouteChoiceSaveResume(string phase)
    {
        var expected = CaptureSave();
        var actual = Task.Run(async () =>
        {
            await _saves.SaveAsync(expected);
            return await _saves.LoadAsync();
        }).GetAwaiter().GetResult()
            ?? throw new InvalidDataException("Route-choice save disappeared during round trip.");
        if (actual.Run.Position != expected.Run.Position ||
            !actual.Run.RoutePlan.SequenceEqual(expected.Run.RoutePlan, StringComparer.Ordinal) ||
            actual.Run.Navigation.SelectedPlanId != expected.Run.Navigation.SelectedPlanId ||
            actual.Run.Navigation.ActiveConnectorId != expected.Run.Navigation.ActiveConnectorId ||
            actual.Run.Navigation.BranchStream.DecisionEdgeId !=
                expected.Run.Navigation.BranchStream.DecisionEdgeId ||
            !actual.Run.Navigation.BranchStream.PrewarmedChunkIds.SequenceEqual(
                expected.Run.Navigation.BranchStream.PrewarmedChunkIds,
                StringComparer.Ordinal) ||
            !actual.Run.Navigation.BranchStream.SelectedChunkIds.SequenceEqual(
                expected.Run.Navigation.BranchStream.SelectedChunkIds,
                StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                $"Route-choice save/resume mismatch in phase '{phase}'.");
        }
        _routeChoiceSaveResumeCount++;
        GD.Print(
            $"CANNONBALL_ROUTE_RESUME_OK plan={expected.Run.Navigation.SelectedPlanId} " +
            $"phase={phase} edge={expected.Run.Position.EdgeId} " +
            $"connector={expected.Run.Navigation.ActiveConnectorId}");
    }

    private bool ReportTransportProbeWhenComplete()
    {
        if (_transportProbe is null || _transportProbeReported)
        {
            return true;
        }
        if (!_transportProbe.IsCompleted)
        {
            return false;
        }
        _transportProbeReported = true;
        if (!_transportProbe.IsCompletedSuccessfully)
        {
            GD.PushError($"Packaged route transport probe failed: {_transportProbe.Exception?.GetBaseException()}");
            GetTree().Quit(1);
            return false;
        }
        var result = _transportProbe.Result;
        GD.Print(
            $"CANNONBALL_OFFICIAL_CORRIDOR_OK content_source=packaged " +
            $"unique_route_miles={result.UniqueRouteMiles:0.000000} " +
            $"requested_probe_miles={result.RequestedMiles:0.######} " +
            $"route_repetitions={result.Repetitions} " +
            $"verified_chunk_reads={result.VerifiedChunkReads} chunk_failures=0");
        return true;
    }

    private async Task<TransportProbeResult> RunTransportProbeAsync(double requestedMiles)
    {
        var uniqueMeters = _package.Chunks.Values
            .GroupBy(manifest => manifest.EdgeId, StringComparer.Ordinal)
            .Sum(group => group.Max(manifest => manifest.EndMeters));
        var uniqueMiles = uniqueMeters / 1_609.344;
        if (!double.IsFinite(uniqueMeters) || !double.IsFinite(uniqueMiles) || uniqueMiles <= 0)
        {
            throw new InvalidDataException("Route package has no positive traversal distance.");
        }
        var manifests = _package.Chunks.Values.OrderBy(manifest => manifest.Id, StringComparer.Ordinal).ToArray();
        var repetitionValue = Math.Ceiling(requestedMiles / uniqueMiles);
        if (!double.IsFinite(repetitionValue) || repetitionValue < 1 || repetitionValue > int.MaxValue)
        {
            throw new ArgumentOutOfRangeException(
                nameof(requestedMiles),
                "Requested transport probe requires too many route repetitions.");
        }
        var repetitions = checked((int)repetitionValue);
        var expectedReads = checked((long)repetitions * manifests.Length);
        if (expectedReads > MaximumTransportProbeReads)
        {
            throw new ArgumentOutOfRangeException(
                nameof(requestedMiles),
                $"Requested transport probe exceeds the {MaximumTransportProbeReads} read budget.");
        }
        var reads = 0;
        for (var repetition = 0; repetition < repetitions; repetition++)
        {
            foreach (var manifest in manifests)
            {
                _ = await _chunkSource.LoadChunkAsync(manifest.Id);
                reads++;
            }
        }
        return new TransportProbeResult(requestedMiles, uniqueMiles, repetitions, reads);
    }

    private async Task PersistAsync(bool quitAfterSave)
    {
        try
        {
            if (quitAfterSave && _stressTest)
            {
                ValidateStressRun();
            }
            if (quitAfterSave && _shortCorridorSoak)
            {
                ValidateShortCorridorSoak();
            }
            if (quitAfterSave && _renderIntegrity)
            {
                ValidateRenderIntegrity();
            }
            if (quitAfterSave && _geographicReview)
            {
                ValidateGeographicReview();
            }
            if (quitAfterSave && _streamingProfile)
            {
                ValidateStreamingProfile();
            }
            if (quitAfterSave && _topologyProfile)
            {
                ValidateTopologyProfile();
            }
            if (quitAfterSave && _routeChoiceProfile)
            {
                ValidateRouteChoiceProfile();
            }
            var save = CaptureSave();
            await _saves.SaveAsync(save);
            await RecordTelemetryAsync("run_suspended");
            GD.Print($"CANNONBALL_SAVE_OK distance_m={save.Run.Position.DistanceMeters:0.0}");
            if (quitAfterSave)
            {
                if (_streamer.ChunkFailureCount > 0)
                {
                    throw new InvalidOperationException(
                        $"Streaming encountered {_streamer.ChunkFailureCount} verified chunk failures.");
                }
                GD.Print(
                    $"CANNONBALL_SMOKE_OK chunks={_streamer.LoadedChunkCount} " +
                    $"distance_m={_streamer.RouteDistanceMeters:0.0} " +
                    $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
                    $"rebases={_streamer.RebaseCount} " +
                    $"max_chunk_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
                    $"max_collision_build_ms={_streamer.MaximumCollisionBuildMilliseconds:0.000} " +
                    $"visual_chunks={_streamer.LoadedChunkCount} " +
                    $"collision_chunks={_streamer.CollisionChunkCount} " +
                    $"content_source=packaged");
                GetTree().Quit();
            }
        }
        catch (Exception exception)
        {
            GD.PushError(exception.ToString());
            if (quitAfterSave)
            {
                GetTree().Quit(1);
            }
        }
    }

    private RunSave CaptureSave()
    {
        var routeDistance = _streamer.CurrentEdgeDistanceMeters;
        var edge = _package.Graph.GetEdge(_streamer.CurrentEdgeId);
        var currentSection = edge.GetLaneSection(routeDistance);
        var activeLane = currentSection.Lanes.SingleOrDefault(candidate =>
            candidate.Index == _streamer.CurrentLaneIndex &&
            string.Equals(candidate.Id, _streamer.CurrentStableLaneId, StringComparison.Ordinal));
        if (activeLane is null)
        {
            throw new InvalidDataException(
                $"Active lane '{_streamer.CurrentStableLaneId}' at index " +
                $"{_streamer.CurrentLaneIndex} is not valid for section '{currentSection.Id}'.");
        }
        var position = RoutePositionMigration.Migrate(
            new RoutePosition(
                edge.Id,
                routeDistance,
                activeLane.Index,
                _streamer.CurrentLateralOffsetMeters,
                0)
            {
                StableLaneId = activeLane.Id,
            },
            edge);
        var runState = new RunState(
            Seed: 20_260_714,
            Position: position,
            RoutePlan: _streamer.RoutePlan,
            ElapsedSeconds: Time.GetTicksMsec() / 1000.0,
            Cash: 25_000,
            Vehicle: new VehicleCondition(82, 1, 1, 1, 0),
            Enforcement: new EnforcementState(0, 0, "clear", 0),
            AssistProfile: _vehicle.AssistProfile)
        {
            Navigation = CaptureNavigationState(),
        };
        var localVehicle = new LocalVehicleState(
            _vehicle.Position.X,
            _vehicle.Position.Y,
            _vehicle.Position.Z,
            _vehicle.LinearVelocity.X,
            _vehicle.LinearVelocity.Y,
            _vehicle.LinearVelocity.Z,
            _vehicle.AngularVelocity.X,
            _vehicle.AngularVelocity.Y,
            _vehicle.AngularVelocity.Z);
        return new RunSave(
            RunSave.CurrentSchemaVersion,
            _package.Graph.ContentVersion,
            RunSave.ComputeContentChecksum(_package.Graph.ContentVersion),
            DateTimeOffset.UtcNow,
            runState,
            localVehicle,
            [new ReplayMarker(runState.ElapsedSeconds, position, "suspend")]);
    }

    private RouteNavigationState CaptureNavigationState()
    {
        if (!_routeChoiceProfile || _interchangeFixture is null)
        {
            return RouteNavigationState.Empty;
        }
        var plan = ActiveRouteChoicePlan;
        var selectedChunks = _package.Chunks.Values
            .Where(manifest => plan.Selection.EdgeIds.Contains(
                manifest.EdgeId,
                StringComparer.Ordinal))
            .Select(manifest => manifest.Id)
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray();
        return new RouteNavigationState(
            plan.Selection.Id,
            _streamer.ActiveConnectorId,
            new BranchStreamSnapshot(
                _streamer.CurrentEdgeId,
                _streamer.DesiredBranchPrewarmChunkIds.OrderBy(id => id, StringComparer.Ordinal).ToArray(),
                selectedChunks));
    }

    private async Task RecordTelemetryAsync(string name)
    {
        var globalDistance = _streamer.RouteDistanceMeters;
        var edgeDistance = _streamer.CurrentEdgeDistanceMeters;
        var properties = new Dictionary<string, object?>
        {
            ["speedMetersPerSecond"] = _vehicle.SpeedMetersPerSecond,
            ["loadedChunks"] = _streamer.LoadedChunkCount,
            ["lookAheadMeters"] = _streamer.CurrentLookAheadMeters,
            ["distanceDeltaMeters"] = globalDistance - _previousDistance,
            ["globalRouteDistanceMeters"] = globalDistance,
            ["contentSource"] = "packaged",
            ["chunkFailures"] = _streamer.ChunkFailureCount,
            ["maximumChunkBuildMilliseconds"] = _streamer.MaximumBuildMilliseconds,
            ["maximumCollisionBuildMilliseconds"] =
                _streamer.MaximumCollisionBuildMilliseconds,
            ["collisionChunks"] = _streamer.CollisionChunkCount,
            ["visualOnlyChunks"] = _streamer.VisualOnlyChunkCount,
            ["shortCorridorLoops"] = _streamer.CompletedShortCorridorLoops,
        };
        _previousDistance = globalDistance;
        await _telemetry.WriteAsync(new TelemetryEvent(
            name,
            DateTimeOffset.UtcNow,
            20_260_714,
            _streamer.CurrentEdgeId,
            edgeDistance,
            properties));
    }

    private void AdvanceStreamingProfile()
    {
        if (!_streamer.IsStreamingSettled)
        {
            _streamingStableFrames = 0;
            return;
        }
        _streamingStableFrames++;
        if (_streamingStableFrames < StreamingStableFramesPerCheckpoint)
        {
            return;
        }
        _streamer.ValidateCurrentStreamingWindows();
        BeginNextStreamingCheckpoint();
    }

    private void BeginNextStreamingCheckpoint()
    {
        _streamingCheckpointIndex++;
        _streamingStableFrames = 0;
        if (_streamingCheckpointIndex >= StreamingCheckpointFractions.Length)
        {
            _streamingProfileComplete = true;
            return;
        }
        _streamer.SetReviewDistance(
            _streamer.TotalRouteLengthMeters *
            StreamingCheckpointFractions[_streamingCheckpointIndex]);
    }

    private void ValidateStreamingProfile()
    {
        if (!_streamingProfileComplete ||
            _streamingCheckpointIndex != StreamingCheckpointFractions.Length)
        {
            throw new InvalidOperationException("Streaming profile did not visit every checkpoint.");
        }
        if (_streamer.ObservedVisualOnlyChunkCount == 0 ||
            _streamer.MaximumVisualChunkCount <= _streamer.MaximumCollisionChunkCount)
        {
            throw new InvalidOperationException(
                "Streaming profile did not separate the visual and collision windows.");
        }
        if (_streamer.MaximumBuildMilliseconds >
                WorldStreamer.InitialChunkBuildBudgetMilliseconds ||
            _streamer.MaximumCollisionBuildMilliseconds >
                WorldStreamer.InitialCollisionBuildBudgetMilliseconds)
        {
            throw new InvalidOperationException("Streaming profile exceeded a declared build budget.");
        }
        GD.Print(
            $"CANNONBALL_STREAMING_SEPARATION_OK checkpoints={StreamingCheckpointFractions.Length} " +
            $"visual_horizon_m={WorldStreamer.VisualLookAheadMeters:0} " +
            $"collision_horizon_m={WorldStreamer.ActivePhysicsAheadMeters:0} " +
            $"max_visual_chunks={_streamer.MaximumVisualChunkCount} " +
            $"max_collision_chunks={_streamer.MaximumCollisionChunkCount} " +
            $"max_visual_only_chunks={_streamer.ObservedVisualOnlyChunkCount} " +
            $"collision_builds={_streamer.CollisionBuildCount} " +
            $"collision_removals={_streamer.CollisionRemovalCount} " +
            $"max_visual_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
            $"max_collision_build_ms={_streamer.MaximumCollisionBuildMilliseconds:0.000}");
    }

    private void ConfigureTopologyCheckpoints()
    {
        if (_topologyOverlay is null)
        {
            throw new InvalidOperationException("Topology overlay was not configured.");
        }
        const double reviewOffsetMeters = 65;
        _topologyCheckpoints = _topologyOverlay.TransitionDistancesMeters
            .SelectMany(distance => new[]
            {
                Math.Max(0, distance - reviewOffsetMeters),
                distance,
                Math.Min(_topologyOverlay.EdgeLengthMeters, distance + reviewOffsetMeters),
            })
            .Select(distance => _streamer.GetRouteDistance(_topologyOverlay.EdgeId, distance))
            .Distinct()
            .ToArray();
        _topologyTraversalStartMeters = Math.Max(
            0,
            _streamer.GetRouteDistance(_topologyOverlay.EdgeId, 0) - 150);
        _topologyTraversalEndMeters = Math.Min(
            _streamer.TotalRouteLengthMeters,
            _streamer.GetRouteDistance(
                _topologyOverlay.EdgeId,
                _topologyOverlay.EdgeLengthMeters) + 150);
    }

    private void BeginTopologyReviewWaypoint()
    {
        if (_topologyOverlay is null ||
            _topologyReviewWaypointIndex >= _topologyOverlay.ReviewDistancesMeters.Count)
        {
            return;
        }
        _topologyReviewFrames = 0;
        _streamer.SetReviewDistance(_streamer.GetRouteDistance(
            _topologyOverlay.EdgeId,
            _topologyOverlay.ReviewDistancesMeters[_topologyReviewWaypointIndex]));
        SetTopologyDiagnosticView(enabled: false);
    }

    private void AdvanceTopologyReview()
    {
        if (_topologyOverlay is null || _topologyDiagnosticCamera is null ||
            !_streamer.ReviewTargetReady || !_streamer.IsStreamingSettled ||
            _topologyReviewWaypointIndex >= _topologyOverlay.ReviewDistancesMeters.Count)
        {
            return;
        }
        _topologyReviewFrames++;
        var forward = -_vehicle.GlobalBasis.Z.Normalized();
        var focus = _vehicle.GlobalPosition + forward * 45;
        _topologyDiagnosticCamera.GlobalPosition =
            _vehicle.GlobalPosition - forward * 32 + Vector3.Up * 28;
        _topologyDiagnosticCamera.LookAt(focus, Vector3.Up);
        if (_topologyReviewFrames == 30)
        {
            SetTopologyDiagnosticView(enabled: true);
        }
        if (_topologyReviewFrames < 60)
        {
            return;
        }
        GD.Print(
            $"CANNONBALL_TOPOLOGY_REVIEW_WAYPOINT_OK " +
            $"index={_topologyReviewWaypointIndex + 1} " +
            $"of={_topologyOverlay.ReviewDistancesMeters.Count}");
        _topologyReviewWaypointIndex++;
        BeginTopologyReviewWaypoint();
    }

    private void SetTopologyDiagnosticView(bool enabled)
    {
        if (_topologyDiagnosticCamera is null)
        {
            return;
        }
        _topologyDiagnosticCamera.Current = enabled;
        var chaseCamera = _vehicle.GetNodeOrNull<Camera3D>("ChaseCameraArm/ChaseCamera");
        if (chaseCamera is not null)
        {
            chaseCamera.Current = !enabled;
        }
    }

    private void AdvanceTopologyProfile()
    {
        if (_topologyTraversalStarted)
        {
            if (_streamer.RouteDistanceMeters >= _topologyTraversalEndMeters)
            {
                _vehicle.AutopilotEnabled = false;
                _topologyProfileComplete = true;
            }
            return;
        }
        if (!_streamer.IsStreamingSettled)
        {
            _topologyStableFrames = 0;
            return;
        }
        _topologyStableFrames++;
        if (_topologyStableFrames < StreamingStableFramesPerCheckpoint)
        {
            return;
        }
        _streamer.ValidateCurrentStreamingWindows();
        if (_topologyTraversalPreparing)
        {
            if (!_streamer.ReviewTargetReady)
            {
                return;
            }
            _vehicle.ResetGroundingTelemetry();
            _vehicle.AutopilotSpeedLimitMetersPerSecond = 75;
            _vehicle.AutopilotEnabled = true;
            _streamer.BeginReviewTraversal();
            _topologyTraversalPreparing = false;
            _topologyTraversalStarted = true;
            return;
        }
        BeginNextTopologyCheckpoint();
    }

    private void BeginNextTopologyCheckpoint()
    {
        _topologyCheckpointIndex++;
        _topologyStableFrames = 0;
        if (_topologyCheckpointIndex >= _topologyCheckpoints.Count)
        {
            _topologyTraversalPreparing = true;
            _streamer.SetReviewDistance(_topologyTraversalStartMeters);
            return;
        }
        _streamer.SetReviewDistance(_topologyCheckpoints[_topologyCheckpointIndex]);
    }

    private void ValidateTopologyProfile()
    {
        if (_topologyOverlay is null || !_topologyProfileComplete ||
            !_topologyTraversalStarted ||
            _topologyCheckpointIndex != _topologyCheckpoints.Count)
        {
            throw new InvalidOperationException("Topology profile did not visit every checkpoint.");
        }
        if (_streamer.MinimumObservedLaneCount > 2 ||
            _streamer.MaximumObservedLaneCount < 4 ||
            _streamer.TopologyTransitionCount <
                _topologyOverlay.TransitionDistancesMeters.Count)
        {
            throw new InvalidOperationException(
                "Topology profile did not build the expected two-to-four-lane transitions.");
        }
        if (!_streamer.ObservedGoreGeometry ||
            _streamer.TopologyCollisionTransitionChunkCount == 0)
        {
            throw new InvalidOperationException(
                "Topology profile did not observe both gore and transition collision geometry.");
        }
        if (_streamer.MaximumPavedWidthMeters <= 15)
        {
            throw new InvalidOperationException(
                "Topology profile did not expand the generated paved road width.");
        }
        if (_streamer.ChunkFailureCount > 0 ||
            _streamer.MaximumBuildMilliseconds > WorldStreamer.InitialChunkBuildBudgetMilliseconds ||
            _streamer.MaximumCollisionBuildMilliseconds >
                WorldStreamer.InitialCollisionBuildBudgetMilliseconds)
        {
            throw new InvalidOperationException(
                "Topology profile encountered a chunk failure or exceeded a build budget.");
        }
        if (_peakSpeedMetersPerSecond < TopologyHighSpeedTargetMetersPerSecond ||
            _streamer.RebaseCount < 1 || !_vehicle.HasBeenGrounded ||
            _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames >
                MaximumRenderIntegrityUnsupportedPhysicsFrames)
        {
            throw new InvalidOperationException(
                "Topology traversal did not remain grounded through a high-speed rebased pass.");
        }
        var missingConnectorMovements = _topologyOverlay.ExpectedTraversedConnectorMovements
            .Where(movement => !_streamer.HasObservedConnectorMovement(movement))
            .ToArray();
        if (missingConnectorMovements.Length > 0)
        {
            throw new InvalidOperationException(
                $"Topology traversal missed connector movements: " +
                $"{string.Join(',', missingConnectorMovements)}.");
        }
        if (_streamer.BranchPrewarmCount == 0 ||
            _streamer.BranchPrewarmEvictionCount == 0)
        {
            throw new InvalidOperationException(
                "Topology traversal did not prewarm and evict its probable branch chunk.");
        }
        GD.Print(
            $"CANNONBALL_TOPOLOGY_OK checkpoints={_topologyCheckpoints.Count} " +
            $"edge={_topologyOverlay.EdgeId} min_lanes={_streamer.MinimumObservedLaneCount} " +
            $"max_lanes={_streamer.MaximumObservedLaneCount} " +
            $"transitions={_streamer.TopologyTransitionCount} " +
            $"transition_collision_chunks={_streamer.TopologyCollisionTransitionChunkCount} " +
            $"gore=true max_paved_width_m={_streamer.MaximumPavedWidthMeters:0.000} " +
            $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
            $"rebases={_streamer.RebaseCount} " +
            $"connector_movements=" +
            $"{string.Join(',', _topologyOverlay.ExpectedTraversedConnectorMovements)} " +
            $"branch_prewarms={_streamer.BranchPrewarmCount} " +
            $"branch_evictions={_streamer.BranchPrewarmEvictionCount} " +
            $"max_unsupported_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} " +
            $"max_visual_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
            $"max_collision_build_ms={_streamer.MaximumCollisionBuildMilliseconds:0.000} " +
            $"override={_topologyOverlay.OverrideId} chunk_failures=0");
    }

    private void ValidateRouteChoiceProfile()
    {
        if (_interchangeFixture is null || !_routeChoiceProfileComplete ||
            _routeChoicePlanIndex != RouteChoicePlanOrder.Length)
        {
            throw new InvalidOperationException(
                "Route-choice profile did not complete every representative route plan.");
        }
        var expectedConnectors = _interchangeFixture.Plans.Values
            .SelectMany(plan => plan.Transitions)
            .Select(transition => transition.ConnectorId)
            .ToHashSet(StringComparer.Ordinal);
        if (!expectedConnectors.SetEquals(_routeChoiceConnectorsObserved))
        {
            throw new InvalidOperationException(
                "Route-choice profile did not physically traverse every selected connector.");
        }
        var catalog = new RouteChoiceCatalog(
            _interchangeFixture.Package.Graph,
            _interchangeFixture.Package.Semantics!);
        var choices = _interchangeFixture.DecisionEdgeIds
            .SelectMany(edgeId => catalog.GetChoices(edgeId))
            .ToArray();
        if (!choices.Any(choice => choice.Movement == JunctionMovement.Continuation) ||
            !choices.Any(choice => choice.Movement == JunctionMovement.Exit &&
                choice.ExitNumber.Length > 0 && choice.Destinations.Count > 0) ||
            !choices.Any(choice => choice.Movement == JunctionMovement.HighwayTransfer &&
                choice.RouteIdentityIds.Count > 0 && choice.Destinations.Count > 0))
        {
            throw new InvalidOperationException(
                "Route-choice queries did not expose stable maneuver and destination metadata.");
        }
        if (!_interchangeFixture.Package.Semantics!.JunctionConnectors.Any(connector =>
                connector.Movement == JunctionMovement.Entrance))
        {
            throw new InvalidOperationException(
                "Representative interchange fixture has no entrance connector.");
        }
        if (_routeChoiceBranchPrewarms.Count < 4 || _routeChoiceBranchEvictions.Count < 4)
        {
            throw new InvalidOperationException(
                "Route-choice profile did not prewarm and evict every probable outgoing branch.");
        }
        if (_routeChoiceSaveResumeCount != RouteChoicePlanOrder.Length * 3)
        {
            throw new InvalidOperationException(
                $"Route-choice profile completed {_routeChoiceSaveResumeCount} of " +
                $"{RouteChoicePlanOrder.Length * 3} save/resume comparisons.");
        }
        if (_routeChoiceChunkFailures != 0 ||
            _routeChoiceMaximumBuildMilliseconds > WorldStreamer.InitialChunkBuildBudgetMilliseconds ||
            _routeChoiceMaximumCollisionBuildMilliseconds >
                WorldStreamer.InitialCollisionBuildBudgetMilliseconds ||
            _routeChoiceMaximumUnsupportedFrames >
                MaximumRenderIntegrityUnsupportedPhysicsFrames)
        {
            throw new InvalidOperationException(
                "Route-choice traversal failed a hash, build-budget, or collision-support gate: " +
                $"chunk_failures={_routeChoiceChunkFailures}, " +
                $"max_visual_build_ms={_routeChoiceMaximumBuildMilliseconds:0.000}, " +
                $"max_collision_build_ms={_routeChoiceMaximumCollisionBuildMilliseconds:0.000}, " +
                $"max_unsupported_frames={_routeChoiceMaximumUnsupportedFrames}.");
        }
        var geometry = _interchangeFixture.GeometryValidation;
        if (geometry.GradeSeparatedCrossings < 1 ||
            geometry.MinimumVerticalClearanceMeters < 5 ||
            geometry.SelfIntersections != 0 ||
            geometry.InvalidShortcuts != 0 ||
            geometry.ParallelCarriagewayPairs < 1)
        {
            throw new InvalidOperationException(
                "Representative interchange geometry failed its grade-separation or topology gates.");
        }
        GD.Print(
            $"CANNONBALL_INTERCHANGES_OK plans={RouteChoicePlanOrder.Length} " +
            $"connectors={_routeChoiceConnectorsObserved.Count} " +
            $"choice_movements=Continuation,Exit,Entrance,HighwayTransfer " +
            $"branch_prewarms={_routeChoiceBranchPrewarms.Count} " +
            $"branch_evictions={_routeChoiceBranchEvictions.Count} " +
            $"save_resumes={_routeChoiceSaveResumeCount} " +
            $"grade_separated_crossings={geometry.GradeSeparatedCrossings} " +
            $"minimum_clearance_m={geometry.MinimumVerticalClearanceMeters:0.000} " +
            $"parallel_carriageways={geometry.ParallelCarriagewayPairs} " +
            $"self_intersections=0 invalid_shortcuts=0 " +
            $"max_unsupported_frames={_routeChoiceMaximumUnsupportedFrames} " +
            $"max_visual_build_ms={_routeChoiceMaximumBuildMilliseconds:0.000} " +
            $"max_collision_build_ms={_routeChoiceMaximumCollisionBuildMilliseconds:0.000} " +
            $"override={_interchangeFixture.OverrideId} chunk_failures=0");
    }

    private void BeginNextGeographicReviewWaypoint()
    {
        _geographicReviewWaypointIndex++;
        _geographicReviewStableFrames = 0;
        if (_geographicReviewWaypointIndex >= GeographicReviewFractions.Length)
        {
            _geographicReviewComplete = true;
            return;
        }
        var fraction = GeographicReviewFractions[_geographicReviewWaypointIndex];
        _streamer.SetReviewDistance(_streamer.TotalRouteLengthMeters * fraction);
    }

    private void AdvanceGeographicReview()
    {
        if (!_streamer.ReviewTargetReady)
        {
            return;
        }
        _geographicReviewStableFrames++;
        if (_geographicReviewStableFrames < GeographicReviewFramesPerWaypoint)
        {
            return;
        }
        GD.Print(
            $"CANNONBALL_GEOGRAPHIC_WAYPOINT_OK index={_geographicReviewWaypointIndex + 1} " +
            $"of={GeographicReviewFractions.Length} edge={_streamer.CurrentEdgeId} " +
            $"distance_m={_streamer.RouteDistanceMeters:0.0}");
        BeginNextGeographicReviewWaypoint();
    }

    private void ValidateStressRun()
    {
        if (_peakSpeedMetersPerSecond < 80)
        {
            throw new InvalidOperationException(
                $"Stress driver only reached {_peakSpeedMetersPerSecond * 2.236936f:0.0} mph.");
        }
        if (_streamer.RebaseCount < 1)
        {
            throw new InvalidOperationException("Stress driver did not cross a local-origin rebase.");
        }
        if (_streamer.ChunkFailureCount > 0)
        {
            throw new InvalidOperationException("Stress driver encountered a route chunk failure.");
        }
    }

    private void ValidateShortCorridorSoak()
    {
        if (_peakSpeedMetersPerSecond < 70)
        {
            throw new InvalidOperationException(
                $"Short-corridor soak only reached {_peakSpeedMetersPerSecond * 2.236936f:0.0} mph.");
        }
        if (_streamer.ChunkFailureCount > 0)
        {
            throw new InvalidOperationException("Short-corridor soak encountered a route chunk failure.");
        }
        if (_streamer.CompletedShortCorridorLoops < 1)
        {
            throw new InvalidOperationException("Short-corridor soak did not complete a route loop.");
        }
        GD.Print(
            $"CANNONBALL_SHORT_CORRIDOR_SOAK_OK chunks={_streamer.LoadedChunkCount} " +
            $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
            $"route_loops={_streamer.CompletedShortCorridorLoops} chunk_failures=0");
    }

    private void ValidateRenderIntegrity()
    {
        const double requiredDistance = 300;
        if (_streamer.TotalRouteLengthMeters < requiredDistance + 35)
        {
            throw new InvalidOperationException(
                $"Render-integrity route is only {_streamer.TotalRouteLengthMeters:0.0} m; " +
                $"required at least {requiredDistance + 35:0.0} m.");
        }
        if (_streamer.RouteDistanceMeters < requiredDistance)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal only reached {_streamer.RouteDistanceMeters:0.0} m; " +
                $"required {requiredDistance:0.0} m.");
        }
        if (_streamer.LoadedChunkCount != _streamer.ExpectedChunkCount)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal loaded {_streamer.LoadedChunkCount} of " +
                $"{_streamer.ExpectedChunkCount} route chunks.");
        }
        if (!_renderTraversalStarted ||
            _minimumLoadedChunksDuringRenderTraversal != _streamer.ExpectedChunkCount)
        {
            throw new InvalidOperationException(
                "Render-integrity traversal did not retain every expected chunk after visual readiness.");
        }
        if (_streamer.ReviewReadyChunkCount != _streamer.ExpectedChunkCount)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal has review geometry for " +
                $"{_streamer.ReviewReadyChunkCount} of {_streamer.ExpectedChunkCount} chunks.");
        }
        if (_streamer.CrossedReviewDistanceThresholdCount != 3)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal crossed " +
                $"{_streamer.CrossedReviewDistanceThresholdCount} of 3 distance thresholds.");
        }
        if (_streamer.ChunkFailureCount > 0)
        {
            throw new InvalidOperationException("Render-integrity traversal encountered a route chunk failure.");
        }
        if (_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames >
            MaximumRenderIntegrityUnsupportedPhysicsFrames)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal was unsupported for " +
                $"{_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} consecutive physics frames.");
        }
        if (!_vehicle.HasBeenGrounded || _vehicle.PostGroundingPhysicsFrames == 0)
        {
            throw new InvalidOperationException("Render-integrity traversal never established road contact.");
        }
        var wellGroundedRatio =
            (double)_vehicle.WellGroundedPhysicsFrames / _vehicle.PostGroundingPhysicsFrames;
        if (wellGroundedRatio < MinimumRenderIntegrityWellGroundedRatio)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal had at least three grounded wheels for only " +
                $"{wellGroundedRatio:P2} of post-contact physics frames.");
        }
        GD.Print(
            $"CANNONBALL_RENDER_INTEGRITY_OK chunks={_streamer.LoadedChunkCount} " +
            $"distance_m={_streamer.RouteDistanceMeters:0.0} " +
            $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
            $"distance_thresholds={_streamer.CrossedReviewDistanceThresholdCount} " +
            $"review_chunks={_streamer.ReviewReadyChunkCount} " +
            $"well_grounded_ratio={wellGroundedRatio:0.0000} " +
            $"max_unsupported_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} " +
            $"chunk_failures=0");
    }

    private void ValidateGeographicReview()
    {
        const double minimumRouteMiles = 10;
        var routeMiles = _streamer.TotalRouteLengthMeters / 1_609.344;
        if (!_geographicReviewComplete || _geographicReviewWaypointIndex < GeographicReviewFractions.Length)
        {
            throw new InvalidOperationException("Geographic review did not render every planned waypoint.");
        }
        if (routeMiles < minimumRouteMiles)
        {
            throw new InvalidOperationException(
                $"Geographic review corridor is only {routeMiles:0.000} mi; required {minimumRouteMiles:0} mi.");
        }
        if (_streamer.RoutePlan.Count < 2)
        {
            throw new InvalidOperationException("Geographic review did not exercise a multi-edge route.");
        }
        if (_streamer.ReviewReadyChunkCountSeen != _streamer.ExpectedChunkCount)
        {
            throw new InvalidOperationException(
                $"Geographic review rendered {_streamer.ReviewReadyChunkCountSeen} of " +
                $"{_streamer.ExpectedChunkCount} route chunks.");
        }
        if (_streamer.ChunkFailureCount > 0)
        {
            throw new InvalidOperationException("Geographic review encountered a route chunk failure.");
        }
        GD.Print(
            $"CANNONBALL_GEOGRAPHIC_REVIEW_OK route_miles={routeMiles:0.000000} " +
            $"edges={_streamer.RoutePlan.Count} visited_edges={_streamer.ReviewEdgeCountVisited} " +
            $"review_chunks={_streamer.ReviewReadyChunkCountSeen} waypoints={GeographicReviewFractions.Length} " +
            $"chunk_failures=0");
    }

    private static string RequiredArgument(IReadOnlyList<string> arguments, string name)
    {
        var prefix = name + "=";
        var inline = arguments.FirstOrDefault(value => value.StartsWith(prefix, StringComparison.Ordinal));
        if (inline is not null && inline.Length > prefix.Length)
        {
            return inline[prefix.Length..];
        }
        var index = ArgumentIndex(arguments, name);
        if (index >= 0 && index + 1 < arguments.Count)
        {
            return arguments[index + 1];
        }
        throw new ArgumentException($"Missing required game argument '{name}=<path>'.");
    }

    private static double OptionalPositiveDouble(IReadOnlyList<string> arguments, string name)
    {
        var prefix = name + "=";
        var raw = arguments.FirstOrDefault(value => value.StartsWith(prefix, StringComparison.Ordinal));
        raw = raw is null ? null : raw[prefix.Length..];
        if (raw is null)
        {
            var index = ArgumentIndex(arguments, name);
            raw = index >= 0 && index + 1 < arguments.Count ? arguments[index + 1] : null;
        }
        if (raw is null)
        {
            return 0;
        }
        if (!double.TryParse(raw, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out var value) ||
            !double.IsFinite(value) || value <= 0)
        {
            throw new ArgumentException($"Game argument '{name}' must be a positive finite number.");
        }
        return value;
    }

    private static int ArgumentIndex(IReadOnlyList<string> arguments, string value)
    {
        for (var index = 0; index < arguments.Count; index++)
        {
            if (string.Equals(arguments[index], value, StringComparison.Ordinal))
            {
                return index;
            }
        }
        return -1;
    }

    private void BuildLighting()
    {
        AddChild(new DirectionalLight3D
        {
            Name = "MoonLight",
            RotationDegrees = new Vector3(-48, -28, 0),
            LightColor = new Color("a9c4ff"),
            LightEnergy = 1.3f,
            ShadowEnabled = true,
        });
        AddChild(new WorldEnvironment
        {
            Name = "NightEnvironment",
            Environment = new Godot.Environment
            {
                BackgroundMode = Godot.Environment.BGMode.Color,
                BackgroundColor = new Color("060912"),
                AmbientLightSource = Godot.Environment.AmbientSource.Color,
                AmbientLightColor = new Color("425072"),
                AmbientLightEnergy = 0.45f,
            },
        });
    }

    private static void ConfigureInputMap()
    {
        AddKeyAction("accelerate", Key.W);
        AddKeyAction("brake", Key.S);
        AddKeyAction("steer_left", Key.A);
        AddKeyAction("steer_right", Key.D);
        AddKeyAction("reset_vehicle", Key.R);
        AddKeyAction("suspend_run", Key.F5);
        AddKeyAction("cycle_assist", Key.Tab);
        AddJoyAxisAction("accelerate", JoyAxis.TriggerRight, 1);
        AddJoyAxisAction("brake", JoyAxis.TriggerLeft, 1);
        AddJoyAxisAction("steer_left", JoyAxis.LeftX, -1);
        AddJoyAxisAction("steer_right", JoyAxis.LeftX, 1);
    }

    private static void AddKeyAction(StringName action, Key key)
    {
        if (!InputMap.HasAction(action))
        {
            InputMap.AddAction(action, 0.12f);
        }
        InputMap.ActionAddEvent(action, new InputEventKey { PhysicalKeycode = key });
    }

    private static void AddJoyAxisAction(StringName action, JoyAxis axis, float axisValue)
    {
        if (!InputMap.HasAction(action))
        {
            InputMap.AddAction(action, 0.12f);
        }
        InputMap.ActionAddEvent(action, new InputEventJoypadMotion { Axis = axis, AxisValue = axisValue });
    }

    private sealed record TransportProbeResult(
        double RequestedMiles,
        double UniqueRouteMiles,
        int Repetitions,
        int VerifiedChunkReads);
}
