using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Saves;
using Cannonball.Core.Simulation;
using Cannonball.Core.Telemetry;
using Cannonball.Game.Automation;
using Cannonball.Game.UI;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;
using System.Runtime.InteropServices;
using System.Text.Json;

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
    private TripMapHud _tripMap = null!;
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
    private bool _routeContextProfile;
    private bool _routeContextReview;
    private bool _vehicleVisualProfile;
    private bool _vehicleVisualReview;
    private bool _roadVisualProfile;
    private bool _roadVisualReview;
    private bool _tripMapReview;
    private bool _tripMapToggleHeld;
    private bool _roadVisualProfileComplete;
    private bool _longRouteProfile;
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
        RepresentativeInterchangeFixture.SemiDirectionalTransferPlanId,
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
    private bool _routeContextProfileComplete;
    private IReadOnlyList<RouteContextReviewPoint> _routeContextReviewPoints = [];
    private int _routeContextReviewPointIndex;
    private int _routeContextStableFrames;
    private int _routeContextReviewFrames;
    private Camera3D? _routeContextDiagnosticCamera;
    private IReadOnlyList<RouteContextOmission> _routeContextOmissions = [];
    private int _routeChoiceSaveResumeCount;
    private readonly HashSet<string> _routeChoiceConnectorsObserved = new(StringComparer.Ordinal);
    private readonly HashSet<string> _routeChoiceBranchPrewarms = new(StringComparer.Ordinal);
    private readonly HashSet<string> _routeChoiceBranchEvictions = new(StringComparer.Ordinal);
    private double _routeChoiceMaximumBuildMilliseconds;
    private double _routeChoiceMaximumCollisionBuildMilliseconds;
    private int _routeChoiceMaximumUnsupportedFrames;
    private int _routeChoiceChunkFailures;
    private VehicleVisualScenario? _vehicleVisualScenario;
    private bool _resumeRequested;
    private bool _resumeVerify;
    private double _elapsedSecondsBase;
    private ulong _sessionStartedTicks;
    private ulong _tripMapPauseStartedTicks;
    private double _tripMapPausedSeconds;
    private ulong _runSeed = 20_260_714;
    private double _cash = 25_000;
    private VehicleCondition _vehicleCondition = new(82, 1, 1, 1, 0);
    private EnforcementState _enforcement = new(0, 0, "clear", 0);
    private LongRouteScenarioFixtureData? _longRouteFixture;
    private string _longRouteSourcePath = string.Empty;
    private string _longRouteEvidencePath = string.Empty;
    private string _longRouteRequestedPlatform = "current";
    private double _longRouteTargetMiles;
    private IReadOnlyList<double> _longRouteSavePointMiles = [];
    private bool _longRouteExpectedCompletion;
    private IReadOnlyList<double> _longRouteCheckpointsMeters = [];
    private int _longRouteCheckpointIndex;
    private int _longRouteStableFrames;
    private int _longRouteProfileIndex;
    private bool _longRouteComplete;
    private readonly AssistProfile[] _longRouteAssistProfiles =
        [AssistProfile.Accessible, AssistProfile.Balanced, AssistProfile.Raw];
    private readonly HashSet<string> _longRouteVerifiedChunks = new(StringComparer.Ordinal);
    private readonly HashSet<string> _longRouteVisitedEdges = new(StringComparer.Ordinal);
    private readonly HashSet<string> _longRouteBuiltSeams = new(StringComparer.Ordinal);
    private readonly List<double> _longRouteFrameMilliseconds = [];
    private readonly List<double> _longRouteChunkBuildMilliseconds = [];
    private readonly List<double> _longRouteCollisionBuildMilliseconds = [];
    private readonly List<object> _longRouteProfileResults = [];
    private readonly HashSet<double> _longRouteSavePointsVerifiedMeters = [];
    private int _longRouteResumeComparisons;
    private int _longRouteCollisionMisses;
    private int _longRouteHashFailures;
    private int _longRouteRebaseCount;
    private int _longRouteSeamCount;
    private double _longRouteMaximumJunctionGapMeters;
    private double _longRouteMaximumLocalCoordinateMeters;
    private long _longRouteStartingWorkingSetBytes;
    private long _longRoutePeakWorkingSetBytes;
    private int _longRouteProfileCheckpointCount;
    private int _longRouteProfileResumeStart;
    private int _longRouteProfileFrameStart;
    private int _longRouteProfileChunkStart;
    private int _longRouteProfileCollisionStart;
    private int _longRouteProfileRebaseStart;
    private bool _longRouteHandlingActive;
    private bool _longRouteHandlingComplete;
    private double _longRouteHandlingStartMeters;
    private double _longRouteHandlingDistanceMeters;
    private int _longRouteHandlingPhysicsFrames;
    private int _longRouteHandlingUnsupportedFrames;

    public override void _Ready()
    {
        try
        {
            ProcessMode = ProcessModeEnum.Always;
            var arguments = OS.GetCmdlineUserArgs();
            var routePath = RequiredArgument(arguments, "--route-package");
            var requestedProbeMiles = OptionalPositiveDouble(arguments, "--distance-miles");
            _longRouteProfile = arguments.Contains("--long-route-profile", StringComparer.Ordinal);
            if (_longRouteProfile)
            {
                _longRouteTargetMiles = requestedProbeMiles > 0
                    ? requestedProbeMiles
                    : throw new ArgumentException(
                        "Long-route profile requires --distance-miles.");
                _runSeed = OptionalUnsignedInteger(arguments, "--seed", 20_260_718);
                _longRouteSavePointMiles = OptionalDoubleList(
                    arguments,
                    "--save-points",
                    [100, 250, 400],
                    _longRouteTargetMiles);
                _longRouteExpectedCompletion = OptionalBoolean(
                    arguments,
                    "--expected-completion",
                    true);
                _longRouteEvidencePath = Path.GetFullPath(
                    RequiredArgument(arguments, "--evidence"));
                _longRouteRequestedPlatform = OptionalArgument(
                    arguments,
                    "--platform") ?? "current";
                ValidateRequestedPlatform(_longRouteRequestedPlatform);
            }
            _resumeVerify = arguments.Contains("--resume-verify", StringComparer.Ordinal);
            _resumeRequested = arguments.Contains("--resume", StringComparer.Ordinal) ||
                _resumeVerify;
            _sessionStartedTicks = Time.GetTicksMsec();
            _smokeTest = arguments.Contains("--smoke-test", StringComparer.Ordinal) || requestedProbeMiles > 0;
            _stressTest = arguments.Contains("--stress-driver", StringComparer.Ordinal);
            _shortCorridorSoak = arguments.Contains("--short-corridor-soak", StringComparer.Ordinal);
            _renderIntegrity = arguments.Contains("--render-integrity", StringComparer.Ordinal);
            _geographicReview = arguments.Contains("--geographic-review", StringComparer.Ordinal);
            _streamingProfile = arguments.Contains("--streaming-profile", StringComparer.Ordinal);
            _topologyProfile = arguments.Contains("--topology-profile", StringComparer.Ordinal);
            _topologyReview = arguments.Contains("--topology-review", StringComparer.Ordinal);
            _routeChoiceProfile = arguments.Contains("--route-choice-profile", StringComparer.Ordinal);
            _routeContextProfile = arguments.Contains("--route-context-profile", StringComparer.Ordinal);
            _routeContextReview = arguments.Contains("--sign-review", StringComparer.Ordinal);
            _vehicleVisualProfile = arguments.Contains("--vehicle-visual-profile", StringComparer.Ordinal);
            _vehicleVisualReview = arguments.Contains("--vehicle-visual-review", StringComparer.Ordinal);
            _roadVisualProfile = arguments.Contains("--road-visual-profile", StringComparer.Ordinal);
            _roadVisualReview = arguments.Contains("--road-visual-review", StringComparer.Ordinal);
            _tripMapReview = arguments.Contains("--trip-map-review", StringComparer.Ordinal);
            _smokeTest = _smokeTest || _stressTest || _shortCorridorSoak || _renderIntegrity ||
                _geographicReview || _streamingProfile || _topologyProfile || _topologyReview ||
                _routeChoiceProfile || _routeContextProfile || _routeContextReview ||
                _vehicleVisualProfile || _vehicleVisualReview || _roadVisualProfile ||
                _roadVisualReview || _tripMapReview || _longRouteProfile || _resumeVerify;
            _smokeTargetFrames = _stressTest || _shortCorridorSoak ? 3_600 : 360;
            if (_renderIntegrity)
            {
                _smokeTargetFrames = 4_800;
            }
            if (_geographicReview)
            {
                _smokeTargetFrames = 7_200;
            }
            if (_streamingProfile || _topologyProfile || _routeContextProfile)
            {
                _smokeTargetFrames = 7_200;
            }
            if (_routeChoiceProfile)
            {
                _smokeTargetFrames = 14_400;
            }
            if (_longRouteProfile)
            {
                _smokeTargetFrames = 250_000;
            }
            if (_topologyReview)
            {
                _smokeTargetFrames = 480;
            }
            if (_routeContextReview)
            {
                _smokeTargetFrames = 1_200;
            }
            if (_vehicleVisualProfile || _vehicleVisualReview)
            {
                _smokeTargetFrames = 1_200;
            }
            if (_roadVisualProfile || _roadVisualReview)
            {
                _smokeTargetFrames = 1_200;
            }
            if (_tripMapReview)
            {
                _smokeTargetFrames = 1_200;
            }

            var absoluteRoutePath = Path.GetFullPath(routePath);
            var sourcePackage = FlatBufferRouteContent.Load(absoluteRoutePath);
            _package = sourcePackage;
            if (_longRouteProfile)
            {
                _longRouteSourcePath = absoluteRoutePath;
                _longRouteFixture = LongRouteScenarioFixture.Create(
                    sourcePackage,
                    _longRouteTargetMiles,
                    _runSeed);
                _package = _longRouteFixture.Package;
                _chunkSource = _longRouteFixture.Source;
            }
            else if (_routeChoiceProfile || _routeContextProfile || _routeContextReview ||
                _roadVisualProfile || _roadVisualReview || _tripMapReview)
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
            if (!_routeChoiceProfile && !_routeContextProfile && !_routeContextReview &&
                !_roadVisualProfile && !_roadVisualReview && !_tripMapReview && !_longRouteProfile)
            {
                _chunkSource = new VerifiedFileChunkSource(
                    _package,
                    Path.GetDirectoryName(absoluteRoutePath)
                        ?? throw new InvalidDataException("Route package has no parent directory."));
            }

            _saves = new JsonRunStateRepository(
                ProjectSettings.GlobalizePath("user://runs/suspended-run.json"),
                RunSave.ComputePackageIdentity(_package));
            RunSave? resumedSave = null;
            if (_resumeRequested)
            {
                resumedSave = Task.Run(async () => await _saves.LoadAsync())
                    .GetAwaiter().GetResult()
                    ?? throw new InvalidDataException("No suspended run is available to resume.");
                _elapsedSecondsBase = resumedSave.Run.ElapsedSeconds;
                _runSeed = resumedSave.Run.Seed;
                _cash = resumedSave.Run.Cash;
                _vehicleCondition = resumedSave.Run.Vehicle;
                _enforcement = resumedSave.Run.Enforcement;
            }

            ConfigureInputMap();
            BuildLighting();
            var initialRoutePlan = _interchangeFixture is null
                ? null
                : resumedSave is not null &&
                    _interchangeFixture.Plans.TryGetValue(
                        resumedSave.Run.Navigation.SelectedPlanId,
                        out var resumedPlan)
                    ? resumedPlan
                    : _interchangeFixture.Plans[
                        _routeContextProfile || _routeContextReview ||
                            _roadVisualProfile || _roadVisualReview || _tripMapReview
                            ? RepresentativeInterchangeFixture.TransferPlanId
                            : RouteChoicePlanOrder[0]];
            ConfigureRuntimeWorld(initialRoutePlan, resumedSave);
            if (_resumeVerify)
            {
                ValidateResumedRuntime(resumedSave
                    ?? throw new InvalidOperationException("Resume verification requires a save."));
            }
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
            if (_routeContextReview || _roadVisualReview)
            {
                _routeContextDiagnosticCamera = new Camera3D
                {
                    Name = "RouteContextDiagnosticCamera",
                    Current = false,
                    Fov = 42,
                };
                AddChild(_routeContextDiagnosticCamera);
            }
            _hud = new PrototypeHud { Name = "PrototypeHud" };
            AddChild(_hud);
            _hud.TripOverviewRequested += OpenTripMap;
            _tripMap = new TripMapHud { Name = "TripMapHud" };
            AddChild(_tripMap);
            _tripMap.Closed += OnTripMapClosed;
            if (_tripMapReview)
            {
                CallDeferred(MethodName.OpenTripMap);
            }

            _telemetry = new JsonlTelemetrySink(
                ProjectSettings.GlobalizePath("user://telemetry/prototype.jsonl"));

            _vehicle.AutopilotEnabled = _smokeTest && !_renderIntegrity && !_streamingProfile &&
                !_topologyProfile && !_topologyReview && !_routeChoiceProfile &&
                !_routeContextProfile && !_routeContextReview && !_vehicleVisualProfile &&
                !_vehicleVisualReview && !_roadVisualProfile && !_roadVisualReview &&
                !_tripMapReview && !_longRouteProfile;
            if (resumedSave is not null)
            {
                _vehicle.SetAssistProfile(resumedSave.Run.AssistProfile);
                GD.Print(
                    $"CANNONBALL_RESUME_OK edge={resumedSave.Run.Position.EdgeId} " +
                    $"distance_m={resumedSave.Run.Position.DistanceMeters:0.000} " +
                    $"rebases={resumedSave.Run.WorldStream.RebaseCount} " +
                    $"backup_recovery={_saves.LastLoadRecovery?.UsedBackup ?? false}");
            }
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
            if (_routeContextProfile || _routeContextReview || _roadVisualProfile ||
                _roadVisualReview)
            {
                ConfigureRouteContextReviewPoints();
                BeginNextRouteContextReviewPoint();
            }
            if (_longRouteProfile)
            {
                BeginLongRouteProfile();
            }
            if (_vehicleVisualProfile || _vehicleVisualReview)
            {
                _vehicleVisualScenario = new VehicleVisualScenario(
                    this,
                    _vehicle,
                    _streamer.InitialVehiclePoint,
                    _streamer.InitialRoadForward,
                    GetNode<DirectionalLight3D>("MoonLight"),
                    GetNode<WorldEnvironment>("NightEnvironment"),
                    _vehicleVisualReview);
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
            if (requestedProbeMiles > 0 && !_longRouteProfile)
            {
                _transportProbe = RunTransportProbeAsync(requestedProbeMiles);
            }

            GD.Print(
                $"CANNONBALL_READY engine={Engine.GetVersionInfo()["string"]} " +
                $"physics_hz={Engine.PhysicsTicksPerSecond} " +
                $"content_source=packaged content_version={_package.Graph.ContentVersion}");
            if (_resumeVerify)
            {
                GetTree().Quit();
            }
        }
        catch (Exception exception)
        {
            GD.PushError(exception.ToString());
            GetTree().Quit(1);
        }
    }

    public override void _Process(double delta)
    {
        if (_streamer is null || _vehicle is null || _hud is null || _tripMap is null)
        {
            return;
        }

        var tripMapTogglePressed = Godot.Input.IsActionPressed("toggle_trip_map");
        if (tripMapTogglePressed && !_tripMapToggleHeld)
        {
            if (_tripMap.IsOpen)
            {
                _tripMap.Close();
            }
            else
            {
                OpenTripMap();
            }
        }
        _tripMapToggleHeld = tripMapTogglePressed;
        if (_tripMap.IsOpen)
        {
            if (_tripMapReview && !_shutdownStarted && ++_smokeFrames >= _smokeTargetFrames)
            {
                _shutdownStarted = true;
                GetTree().Quit();
            }
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
        if ((_routeContextProfile || _routeContextReview || _roadVisualProfile ||
                _roadVisualReview) &&
            !_routeContextProfileComplete)
        {
            try
            {
                AdvanceRouteContextProfile();
            }
            catch (Exception exception)
            {
                GD.PushError(exception.ToString());
                _shutdownStarted = true;
                GetTree().Quit(1);
                return;
            }
        }
        if (_vehicleVisualScenario is { Complete: false })
        {
            try
            {
                _vehicleVisualScenario.Advance();
            }
            catch (Exception exception)
            {
                GD.PushError(exception.ToString());
                _shutdownStarted = true;
                GetTree().Quit(1);
                return;
            }
        }
        if ((_roadVisualProfile || _roadVisualReview) && !_roadVisualProfileComplete)
        {
            try
            {
                AdvanceRoadVisualProfile();
            }
            catch (Exception exception)
            {
                GD.PushError(exception.ToString());
                _shutdownStarted = true;
                GetTree().Quit(1);
                return;
            }
        }
        if (_longRouteProfile && !_longRouteComplete)
        {
            try
            {
                _longRouteFrameMilliseconds.Add(delta * 1_000);
                _longRoutePeakWorkingSetBytes = Math.Max(
                    _longRoutePeakWorkingSetBytes,
                    System.Diagnostics.Process.GetCurrentProcess().WorkingSet64);
                AdvanceLongRouteProfile();
            }
            catch (Exception exception)
            {
                GD.PushError(exception.ToString());
                _shutdownStarted = true;
                GetTree().Quit(1);
                return;
            }
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
            _routeChoiceProfileComplete ||
            (_routeContextProfileComplete && !_roadVisualProfile && !_roadVisualReview) ||
            _longRouteComplete ||
            _vehicleVisualScenario is { Complete: true } ||
            (_roadVisualProfileComplete && _routeContextProfileComplete))
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

    private void ConfigureRuntimeWorld(ValidatedRoutePlan? routePlan, RunSave? resumedSave = null)
    {
        var routePlanEdgeIds = resumedSave?.Run.RoutePlan ??
            routePlan?.LinearPlan.EdgeIds ??
            _longRouteFixture?.EdgeIds;
        var routePlanConnectorIds = routePlan?.Selection.ConnectorIds ??
            _longRouteFixture?.ConnectorIds;
        var initialManifest = WorldStreamer.FindInitialManifest(_package, routePlanEdgeIds);
        var initialChunk = _chunkSource.LoadChunk(initialManifest.Id);
        IReadOnlyList<RouteChunkContent>? resumeChunks = null;
        if (resumedSave is not null)
        {
            var resumeManifest = WorldStreamer.FindManifest(
                _package,
                resumedSave.Run.Position.EdgeId,
                resumedSave.Run.Position.DistanceMeters);
            var savedChunkIds = resumedSave.Run.WorldStream.LoadedChunkIds;
            var resumeChunkIds = (savedChunkIds.Count == 0
                    ? [resumeManifest.Id]
                    : savedChunkIds)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(id => id, StringComparer.Ordinal)
                .ToArray();
            resumeChunks = resumeChunkIds.Select(_chunkSource.LoadChunk).ToArray();
        }
        _streamer = new WorldStreamer { Name = "WorldStreamer" };
        _streamer.Configure(
            _package,
            _chunkSource,
            initialChunk,
            routePlanEdgeIds,
            routePlanConnectorIds,
            resumedSave?.Run.Position,
            resumedSave?.Run.WorldStream,
            resumeChunks,
            resumedSave?.Run.Navigation);
        _streamer.ShortCorridorLoopEnabled = _shortCorridorSoak;
        var vehicleTransform = resumedSave is null
            ? new Transform3D(
                Basis.LookingAt(_streamer.InitialRoadForward, Vector3.Up),
                _streamer.InitialVehiclePoint + Vector3.Up * 0.78f)
            : new Transform3D(
                new Basis(new Quaternion(
                    (float)resumedSave.LocalVehicle.RotationX,
                    (float)resumedSave.LocalVehicle.RotationY,
                    (float)resumedSave.LocalVehicle.RotationZ,
                    (float)resumedSave.LocalVehicle.RotationW)),
                new Vector3(
                    (float)resumedSave.LocalVehicle.PositionX,
                    (float)resumedSave.LocalVehicle.PositionY,
                    (float)resumedSave.LocalVehicle.PositionZ));
        _vehicle = new CannonballVehicle
        {
            Transform = vehicleTransform,
            LinearVelocity = resumedSave is null
                ? Vector3.Zero
                : new Vector3(
                    (float)resumedSave.LocalVehicle.VelocityX,
                    (float)resumedSave.LocalVehicle.VelocityY,
                    (float)resumedSave.LocalVehicle.VelocityZ),
            AngularVelocity = resumedSave is null
                ? Vector3.Zero
                : new Vector3(
                    (float)resumedSave.LocalVehicle.AngularVelocityX,
                    (float)resumedSave.LocalVehicle.AngularVelocityY,
                    (float)resumedSave.LocalVehicle.AngularVelocityZ),
        };
        if (resumedSave is not null)
        {
            _vehicle.SetAssistProfile(resumedSave.Run.AssistProfile);
        }
        _streamer.Track(_vehicle);
        AddChild(_streamer);
        AddChild(_vehicle);
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

    private void ValidateResumedRuntime(RunSave expected)
    {
        var position = expected.Run.Position;
        var actualStream = _streamer.CaptureStreamSnapshot();
        var actualRotation = _vehicle.Basis.GetRotationQuaternion();
        var expectedRotation = new Quaternion(
            (float)expected.LocalVehicle.RotationX,
            (float)expected.LocalVehicle.RotationY,
            (float)expected.LocalVehicle.RotationZ,
            (float)expected.LocalVehicle.RotationW).Normalized();
        var rotationDot = Math.Abs(actualRotation.Normalized().Dot(expectedRotation));
        if (!string.Equals(_streamer.CurrentEdgeId, position.EdgeId, StringComparison.Ordinal) ||
            Math.Abs(_streamer.CurrentEdgeDistanceMeters - position.DistanceMeters) > 0.001 ||
            _streamer.CurrentLaneIndex != position.LaneIndex ||
            !string.Equals(
                _streamer.CurrentStableLaneId,
                position.StableLaneId,
                StringComparison.Ordinal) ||
            !_streamer.RoutePlan.SequenceEqual(expected.Run.RoutePlan, StringComparer.Ordinal) ||
            !string.Equals(
                _streamer.ActiveConnectorId,
                expected.Run.Navigation.ActiveConnectorId,
                StringComparison.Ordinal) ||
            !StreamEquivalent(actualStream, expected.Run.WorldStream) ||
            _runSeed != expected.Run.Seed ||
            _cash != expected.Run.Cash ||
            _vehicleCondition != expected.Run.Vehicle ||
            _enforcement != expected.Run.Enforcement ||
            _vehicle.AssistProfile != expected.Run.AssistProfile ||
            _elapsedSecondsBase != expected.Run.ElapsedSeconds ||
            _vehicle.Position.DistanceTo(new Vector3(
                (float)expected.LocalVehicle.PositionX,
                (float)expected.LocalVehicle.PositionY,
                (float)expected.LocalVehicle.PositionZ)) > 0.001f ||
            _vehicle.LinearVelocity.DistanceTo(new Vector3(
                (float)expected.LocalVehicle.VelocityX,
                (float)expected.LocalVehicle.VelocityY,
                (float)expected.LocalVehicle.VelocityZ)) > 0.001f ||
            _vehicle.AngularVelocity.DistanceTo(new Vector3(
                (float)expected.LocalVehicle.AngularVelocityX,
                (float)expected.LocalVehicle.AngularVelocityY,
                (float)expected.LocalVehicle.AngularVelocityZ)) > 0.001f ||
            1 - rotationDot > 0.0001)
        {
            GD.PrintErr(
                $"CANNONBALL_RESUME_MISMATCH " +
                $"edge={_streamer.CurrentEdgeId == position.EdgeId} " +
                $"distance_delta={_streamer.CurrentEdgeDistanceMeters - position.DistanceMeters:0.000000} " +
                $"lane_index={_streamer.CurrentLaneIndex == position.LaneIndex} " +
                $"lane_id={_streamer.CurrentStableLaneId == position.StableLaneId} " +
                $"route_plan={_streamer.RoutePlan.SequenceEqual(expected.Run.RoutePlan, StringComparer.Ordinal)} " +
                $"connector={_streamer.ActiveConnectorId == expected.Run.Navigation.ActiveConnectorId} " +
                $"stream={StreamEquivalent(actualStream, expected.Run.WorldStream)} " +
                $"origin_delta=({actualStream.OriginWorldX - expected.Run.WorldStream.OriginWorldX:0.000000}," +
                $"{actualStream.OriginWorldY - expected.Run.WorldStream.OriginWorldY:0.000000}," +
                $"{actualStream.OriginWorldZ - expected.Run.WorldStream.OriginWorldZ:0.000000}) " +
                $"local_origin_delta={actualStream.LocalOriginRouteMeters - expected.Run.WorldStream.LocalOriginRouteMeters:0.000000} " +
                $"rebase_delta={actualStream.RebaseCount - expected.Run.WorldStream.RebaseCount} " +
                $"loaded_actual={string.Join(',', actualStream.LoadedChunkIds)} " +
                $"loaded_expected={string.Join(',', expected.Run.WorldStream.LoadedChunkIds)} " +
                $"collision_actual={string.Join(',', actualStream.CollisionChunkIds)} " +
                $"collision_expected={string.Join(',', expected.Run.WorldStream.CollisionChunkIds)} " +
                $"seed={_runSeed == expected.Run.Seed} cash={_cash == expected.Run.Cash} " +
                $"vehicle_condition={_vehicleCondition == expected.Run.Vehicle} " +
                $"enforcement={_enforcement == expected.Run.Enforcement} " +
                $"assist={_vehicle.AssistProfile == expected.Run.AssistProfile} " +
                $"elapsed={_elapsedSecondsBase == expected.Run.ElapsedSeconds} " +
                $"position_delta={_vehicle.Position.DistanceTo(new Vector3((float)expected.LocalVehicle.PositionX, (float)expected.LocalVehicle.PositionY, (float)expected.LocalVehicle.PositionZ)):0.000000} " +
                $"velocity_delta={_vehicle.LinearVelocity.DistanceTo(new Vector3((float)expected.LocalVehicle.VelocityX, (float)expected.LocalVehicle.VelocityY, (float)expected.LocalVehicle.VelocityZ)):0.000000} " +
                $"angular_delta={_vehicle.AngularVelocity.DistanceTo(new Vector3((float)expected.LocalVehicle.AngularVelocityX, (float)expected.LocalVehicle.AngularVelocityY, (float)expected.LocalVehicle.AngularVelocityZ)):0.000000} " +
                $"rotation_delta={1 - rotationDot:0.000000}");
            throw new InvalidDataException(
                "Resumed runtime does not match the authoritative suspended state.");
        }
        GD.Print(
            $"CANNONBALL_RESUME_EQUIVALENT_OK edge={position.EdgeId} " +
            $"distance_m={position.DistanceMeters:0.000} lane={position.StableLaneId} " +
            $"loaded_chunks={actualStream.LoadedChunkIds.Count} " +
            $"collision_chunks={actualStream.CollisionChunkIds.Count} " +
            $"rebases={actualStream.RebaseCount}");
    }

    private static bool StreamEquivalent(
        WorldStreamSnapshot actual,
        WorldStreamSnapshot expected) =>
        Math.Abs(actual.OriginWorldX - expected.OriginWorldX) <= 0.001 &&
        Math.Abs(actual.OriginWorldY - expected.OriginWorldY) <= 0.001 &&
        Math.Abs(actual.OriginWorldZ - expected.OriginWorldZ) <= 0.001 &&
        Math.Abs(actual.LocalOriginRouteMeters - expected.LocalOriginRouteMeters) <= 0.001 &&
        actual.RebaseCount == expected.RebaseCount &&
        actual.LoadedChunkIds.SequenceEqual(expected.LoadedChunkIds, StringComparer.Ordinal) &&
        actual.CollisionChunkIds.SequenceEqual(expected.CollisionChunkIds, StringComparer.Ordinal);

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

    private void BeginLongRouteProfile()
    {
        var fixture = _longRouteFixture
            ?? throw new InvalidOperationException("Long-route fixture is not configured.");
        if (_longRouteCheckpointsMeters.Count == 0)
        {
            var plan = LinearRoutePlan.Build(_package.Graph, fixture.EdgeIds);
            _longRouteCheckpointsMeters = _package.Chunks.Values
                .Select(manifest =>
                {
                    var edge = plan.GetEdge(manifest.EdgeId);
                    return edge.StartMeters + (manifest.StartMeters + manifest.EndMeters) / 2;
                })
                .Concat(_longRouteSavePointMiles.Select(miles =>
                    miles * LongRouteScenarioFixture.MetersPerMile))
                .Append(Math.Max(0, fixture.TargetDistanceMeters - 0.001))
                .Select(distance => Math.Round(distance, 6, MidpointRounding.AwayFromZero))
                .Distinct()
                .OrderBy(distance => distance)
                .ToArray();
            _longRouteStartingWorkingSetBytes =
                System.Diagnostics.Process.GetCurrentProcess().WorkingSet64;
            _longRoutePeakWorkingSetBytes = _longRouteStartingWorkingSetBytes;
        }
        _longRouteCheckpointIndex = 0;
        _longRouteStableFrames = 0;
        _longRouteProfileCheckpointCount = 0;
        _longRouteProfileResumeStart = _longRouteResumeComparisons;
        _longRouteProfileFrameStart = _longRouteFrameMilliseconds.Count;
        _longRouteProfileChunkStart = _longRouteChunkBuildMilliseconds.Count;
        _longRouteProfileCollisionStart = _longRouteCollisionBuildMilliseconds.Count;
        _longRouteProfileRebaseStart = _longRouteRebaseCount;
        _longRouteHandlingActive = false;
        _longRouteHandlingComplete = false;
        _longRouteHandlingStartMeters = 0;
        _longRouteHandlingDistanceMeters = 0;
        _longRouteHandlingPhysicsFrames = 0;
        _longRouteHandlingUnsupportedFrames = 0;
        _vehicle.AutopilotEnabled = false;
        _vehicle.SetAssistProfile(_longRouteAssistProfiles[_longRouteProfileIndex]);
        _streamer.SetReviewDistance(_longRouteCheckpointsMeters[0]);
        GD.Print(
            $"CANNONBALL_LONG_ROUTE_PROFILE_START assist=" +
            $"{_longRouteAssistProfiles[_longRouteProfileIndex]} " +
            $"target_miles={_longRouteTargetMiles:0.###} " +
            $"checkpoints={_longRouteCheckpointsMeters.Count}");
    }

    private void AdvanceLongRouteProfile()
    {
        if (_longRouteHandlingActive)
        {
            if (_vehicle.PostGroundingPhysicsFrames < 180)
            {
                return;
            }
            _longRouteHandlingActive = false;
            _vehicle.AutopilotEnabled = false;
            _longRouteHandlingDistanceMeters = Math.Max(
                0,
                _streamer.RouteDistanceMeters - _longRouteHandlingStartMeters);
            _longRouteHandlingUnsupportedFrames =
                _vehicle.MaximumConsecutiveUnsupportedPhysicsFrames;
            _longRouteHandlingPhysicsFrames = _vehicle.PostGroundingPhysicsFrames;
            if (!_vehicle.HasBeenGrounded ||
                _longRouteHandlingDistanceMeters < 2 ||
                _longRouteHandlingUnsupportedFrames >
                    MaximumRenderIntegrityUnsupportedPhysicsFrames)
            {
                throw new InvalidOperationException(
                    $"Long-route {_longRouteAssistProfiles[_longRouteProfileIndex]} handling " +
                    $"segment failed: distance={_longRouteHandlingDistanceMeters:F3} m, " +
                    $"grounded={_vehicle.HasBeenGrounded}, " +
                    $"unsupported_frames={_longRouteHandlingUnsupportedFrames}.");
            }
            _longRouteHandlingComplete = true;
            _streamer.SetReviewDistance(_longRouteCheckpointsMeters[0]);
            _longRouteStableFrames = 0;
            GD.Print(
                $"CANNONBALL_LONG_ROUTE_HANDLING_OK assist=" +
                $"{_longRouteAssistProfiles[_longRouteProfileIndex]} " +
                $"distance_m={_longRouteHandlingDistanceMeters:0.000} " +
                $"physics_frames={_longRouteHandlingPhysicsFrames} " +
                $"max_unsupported_frames={_longRouteHandlingUnsupportedFrames}");
            return;
        }
        if (!_streamer.ReviewTargetReady || !_streamer.IsStreamingSettled)
        {
            _longRouteStableFrames = 0;
            return;
        }
        _longRouteStableFrames++;
        if (_longRouteStableFrames < StreamingStableFramesPerCheckpoint)
        {
            return;
        }

        _streamer.ValidateCurrentStreamingWindows();
        if (!_longRouteHandlingComplete)
        {
            _vehicle.ResetGroundingTelemetry();
            _vehicle.AutopilotSpeedLimitMetersPerSecond = 30;
            _longRouteHandlingStartMeters = _streamer.RouteDistanceMeters;
            _streamer.BeginReviewTraversal();
            _vehicle.AutopilotEnabled = true;
            _longRouteHandlingActive = true;
            return;
        }
        if (_streamer.DesiredCollisionChunkCount != _streamer.CollisionChunkCount)
        {
            _longRouteCollisionMisses++;
            throw new InvalidOperationException(
                "Long-route collision residency does not match the declared window.");
        }
        var checkpoint = _longRouteCheckpointsMeters[_longRouteCheckpointIndex];
        _longRouteProfileCheckpointCount++;
        var isSavePoint = _longRouteSavePointMiles.Any(miles =>
            Math.Abs(checkpoint - miles * LongRouteScenarioFixture.MetersPerMile) <= 0.001);
        if (isSavePoint)
        {
            VerifyLongRouteSaveResume(checkpoint);
        }

        _longRouteCheckpointIndex++;
        _longRouteStableFrames = 0;
        if (_longRouteCheckpointIndex < _longRouteCheckpointsMeters.Count)
        {
            _streamer.SetReviewDistance(
                _longRouteCheckpointsMeters[_longRouteCheckpointIndex]);
            return;
        }

        CompleteLongRouteAssistProfile();
    }

    private void VerifyLongRouteSaveResume(double checkpointMeters)
    {
        var expected = CaptureSave();
        var actual = Task.Run(async () =>
        {
            await _saves.SaveAsync(expected);
            return await _saves.LoadAsync();
        }).GetAwaiter().GetResult()
            ?? throw new InvalidDataException("Long-route save disappeared during round trip.");
        if (!string.Equals(actual.ContentChecksum, expected.ContentChecksum, StringComparison.Ordinal) ||
            actual.Run.Position != expected.Run.Position ||
            !actual.Run.RoutePlan.SequenceEqual(expected.Run.RoutePlan, StringComparer.Ordinal) ||
            !StreamEquivalent(actual.Run.WorldStream, expected.Run.WorldStream) ||
            actual.Run.Vehicle != expected.Run.Vehicle ||
            actual.Run.Enforcement != expected.Run.Enforcement ||
            actual.LocalVehicle != expected.LocalVehicle)
        {
            throw new InvalidDataException(
                $"Long-route save diverged at {checkpointMeters:F3} meters.");
        }

        CollectLongRouteStreamerMetrics(includeRebases: false);
        RemoveRuntimeWorld();
        _elapsedSecondsBase = actual.Run.ElapsedSeconds;
        _sessionStartedTicks = Time.GetTicksMsec();
        ConfigureRuntimeWorld(routePlan: null, actual);
        ValidateResumedRuntime(actual);
        _vehicle.AutopilotEnabled = false;
        _vehicle.SetAssistProfile(_longRouteAssistProfiles[_longRouteProfileIndex]);
        _streamer.SetReviewDistance(checkpointMeters);
        _longRouteResumeComparisons++;
        _longRouteSavePointsVerifiedMeters.Add(checkpointMeters);
        GD.Print(
            $"CANNONBALL_LONG_ROUTE_RESUME_OK assist=" +
            $"{_longRouteAssistProfiles[_longRouteProfileIndex]} " +
            $"distance_m={checkpointMeters:0.000}");
    }

    private void CompleteLongRouteAssistProfile()
    {
        CollectLongRouteStreamerMetrics(includeRebases: true);
        var assist = _longRouteAssistProfiles[_longRouteProfileIndex];
        var completedDistance = _streamer.RouteDistanceMeters;
        _longRouteProfileResults.Add(new
        {
            assist_profile = assist.ToString(),
            completed_distance_miles = completedDistance /
                LongRouteScenarioFixture.MetersPerMile,
            checkpoints = _longRouteProfileCheckpointCount,
            resume_comparisons = _longRouteResumeComparisons - _longRouteProfileResumeStart,
            rebases = _longRouteRebaseCount - _longRouteProfileRebaseStart,
            frames = _longRouteFrameMilliseconds.Count - _longRouteProfileFrameStart,
            chunk_builds = _longRouteChunkBuildMilliseconds.Count - _longRouteProfileChunkStart,
            collision_builds = _longRouteCollisionBuildMilliseconds.Count -
                _longRouteProfileCollisionStart,
            handling_distance_meters = _longRouteHandlingDistanceMeters,
            handling_physics_frames = _longRouteHandlingPhysicsFrames,
            handling_maximum_unsupported_frames = _longRouteHandlingUnsupportedFrames,
            expected_completion = _longRouteExpectedCompletion,
            completed = completedDistance + 0.01 >=
                (_longRouteFixture?.TargetDistanceMeters ?? double.PositiveInfinity),
        });
        GD.Print(
            $"CANNONBALL_LONG_ROUTE_PROFILE_OK assist={assist} " +
            $"distance_miles={completedDistance / LongRouteScenarioFixture.MetersPerMile:0.000} " +
            $"checkpoints={_longRouteProfileCheckpointCount} " +
            $"resume_comparisons={_longRouteResumeComparisons - _longRouteProfileResumeStart}");

        _longRouteProfileIndex++;
        if (_longRouteProfileIndex >= _longRouteAssistProfiles.Length)
        {
            _longRouteComplete = true;
            return;
        }

        RemoveRuntimeWorld();
        _elapsedSecondsBase = 0;
        _sessionStartedTicks = Time.GetTicksMsec();
        ConfigureRuntimeWorld(routePlan: null);
        BeginLongRouteProfile();
    }

    private void CollectLongRouteStreamerMetrics(bool includeRebases)
    {
        foreach (var id in _streamer.ReviewReadyChunkIdsSeen)
        {
            _longRouteVerifiedChunks.Add(id);
        }
        foreach (var id in _streamer.ReviewEdgeIdsVisited)
        {
            _longRouteVisitedEdges.Add(id);
        }
        foreach (var id in _streamer.JunctionTransitionSeamIdsBuilt)
        {
            _longRouteBuiltSeams.Add(id);
        }
        _longRouteChunkBuildMilliseconds.AddRange(
            _streamer.ChunkBuildSamplesMilliseconds);
        _longRouteCollisionBuildMilliseconds.AddRange(
            _streamer.CollisionBuildSamplesMilliseconds);
        _longRouteHashFailures += _streamer.ChunkFailureCount;
        _longRouteMaximumJunctionGapMeters = Math.Max(
            _longRouteMaximumJunctionGapMeters,
            _streamer.MaximumJunctionGapMeters);
        _longRouteMaximumLocalCoordinateMeters = Math.Max(
            _longRouteMaximumLocalCoordinateMeters,
            _streamer.MaximumLocalCoordinateMeters);
        if (includeRebases)
        {
            _longRouteRebaseCount += _streamer.RebaseCount;
        }
        _longRouteSeamCount = _longRouteBuiltSeams.Count;
    }

    private void RemoveRuntimeWorld()
    {
        _streamer.ProcessMode = ProcessModeEnum.Disabled;
        _vehicle.ProcessMode = ProcessModeEnum.Disabled;
        RemoveChild(_vehicle);
        _vehicle.QueueFree();
        RemoveChild(_streamer);
        _streamer.QueueFree();
    }

    private void ValidateLongRouteProfile()
    {
        var fixture = _longRouteFixture
            ?? throw new InvalidOperationException("Long-route fixture is not configured.");
        var expectedResumeComparisons =
            _longRouteSavePointMiles.Count * _longRouteAssistProfiles.Length;
        var expectedSeams = fixture.EdgeIds.Count - 1;
        if (!_longRouteComplete ||
            _longRouteProfileResults.Count != _longRouteAssistProfiles.Length ||
            _longRouteVerifiedChunks.Count != fixture.Package.Chunks.Count ||
            _longRouteVisitedEdges.Count != fixture.EdgeIds.Count ||
            _longRouteSeamCount != expectedSeams ||
            fixture.MaximumGeometryGapMeters > 0.001 ||
            _longRouteMaximumJunctionGapMeters > 0.001 ||
            _longRouteCollisionMisses != 0 ||
            _longRouteHashFailures != 0 ||
            _longRouteResumeComparisons != expectedResumeComparisons ||
            _longRouteSavePointsVerifiedMeters.Count != _longRouteSavePointMiles.Count ||
            _longRouteRebaseCount < 1 ||
            _longRouteMaximumLocalCoordinateMeters >= WorldStreamer.RebaseThresholdMeters)
        {
            throw new InvalidOperationException(
                "Long-route acceptance metrics did not satisfy the deterministic scenario contract: " +
                $"complete={_longRouteComplete} " +
                $"profiles={_longRouteProfileResults.Count}/{_longRouteAssistProfiles.Length} " +
                $"chunks={_longRouteVerifiedChunks.Count}/{fixture.Package.Chunks.Count} " +
                $"edges={_longRouteVisitedEdges.Count}/{fixture.EdgeIds.Count} " +
                $"transitions={_longRouteSeamCount}/{expectedSeams} " +
                $"geometry_gap_m={fixture.MaximumGeometryGapMeters:F6} " +
                $"junction_gap_m={_longRouteMaximumJunctionGapMeters:F6} " +
                $"collision_misses={_longRouteCollisionMisses} " +
                $"hash_failures={_longRouteHashFailures} " +
                $"resume={_longRouteResumeComparisons}/{expectedResumeComparisons} " +
                $"save_points={_longRouteSavePointsVerifiedMeters.Count}/{_longRouteSavePointMiles.Count} " +
                $"rebases={_longRouteRebaseCount} " +
                $"max_local_m={_longRouteMaximumLocalCoordinateMeters:F3}.");
        }

        var packageIdentity = RunSave.ComputePackageIdentity(_package);
        var memoryGrowth = Math.Max(
            0,
            _longRoutePeakWorkingSetBytes - _longRouteStartingWorkingSetBytes);
        var evidence = new
        {
            schema_version = 1,
            task_id = "P0-006",
            milestone = "M1",
            status = "complete",
            git_revision = OptionalEnvironment("GITHUB_SHA") ??
                OptionalEnvironment("CANNONBALL_GIT_REVISION") ?? "working-tree",
            recorded_at_utc = DateTimeOffset.UtcNow,
            platform = new
            {
                requested = _longRouteRequestedPlatform,
                os = RuntimeInformation.OSDescription,
                architecture = RuntimeInformation.OSArchitecture.ToString().ToLowerInvariant(),
            },
            scenario_inputs = new
            {
                route_package = Path.GetRelativePath(
                    Directory.GetCurrentDirectory(),
                    _longRouteSourcePath).Replace('\\', '/'),
                route_package_checksum = packageIdentity.PackageChecksum,
                source_route_root_sha256 = fixture.SourceRootContentHash,
                source_artifact_sha256 = fixture.Package.Metadata?.SourceArtifactSha256,
                seed = _runSeed,
                assist_profiles = _longRouteAssistProfiles.Select(value => value.ToString()).ToArray(),
                target_distance_miles = _longRouteTargetMiles,
                save_points_miles = _longRouteSavePointMiles,
                expected_completion = _longRouteExpectedCompletion,
                authored_override_id = fixture.OverrideId,
            },
            metrics = new
            {
                traversed_distance_miles = fixture.TargetDistanceMeters /
                    LongRouteScenarioFixture.MetersPerMile,
                route_edges = fixture.EdgeIds.Count,
                route_transitions = _longRouteSeamCount,
                expected_route_transitions = expectedSeams,
                route_chunks = fixture.Package.Chunks.Count,
                verified_route_chunks = _longRouteVerifiedChunks.Count,
                missing_chunks = fixture.Package.Chunks.Count - _longRouteVerifiedChunks.Count,
                hash_failures = _longRouteHashFailures,
                geometry_gap_meters = fixture.MaximumGeometryGapMeters,
                maximum_junction_gap_meters = _longRouteMaximumJunctionGapMeters,
                road_gaps = 0,
                collision_misses = _longRouteCollisionMisses,
                rebases = _longRouteRebaseCount,
                maximum_local_coordinate_meters = _longRouteMaximumLocalCoordinateMeters,
                resume_comparisons = _longRouteResumeComparisons,
                save_divergence = 0,
                frame_time_ms = Percentiles(_longRouteFrameMilliseconds),
                chunk_build_ms = Percentiles(_longRouteChunkBuildMilliseconds),
                collision_build_ms = Percentiles(_longRouteCollisionBuildMilliseconds),
                starting_working_set_bytes = _longRouteStartingWorkingSetBytes,
                peak_working_set_bytes = _longRoutePeakWorkingSetBytes,
                memory_growth_bytes = memoryGrowth,
            },
            assist_profile_results = _longRouteProfileResults,
            acceptance = new
            {
                completed = true,
                zero_missing_chunks = true,
                zero_hash_failures = true,
                zero_road_gaps = true,
                zero_collision_misses = true,
                zero_save_divergence = true,
                all_assist_profiles = true,
            },
            human_gate = new
            {
                name = "30-minute keyboard and controller handling sessions",
                required_for = "M0",
                status = "not part of deterministic automation acceptance",
            },
        };
        Directory.CreateDirectory(Path.GetDirectoryName(_longRouteEvidencePath)
            ?? throw new InvalidDataException("Evidence path has no parent directory."));
        File.WriteAllText(
            _longRouteEvidencePath,
            JsonSerializer.Serialize(evidence, new JsonSerializerOptions
            {
                WriteIndented = true,
            }) + System.Environment.NewLine);
        GD.Print(
            $"CANNONBALL_LONG_ROUTE_OK distance_miles={_longRouteTargetMiles:0.000} " +
            $"profiles={_longRouteAssistProfiles.Length} chunks={_longRouteVerifiedChunks.Count} " +
            $"transitions={_longRouteSeamCount} rebases={_longRouteRebaseCount} " +
            $"resume_comparisons={_longRouteResumeComparisons} collision_misses=0 " +
            $"hash_failures=0 road_gaps=0 evidence={_longRouteEvidencePath}");
    }

    private static object Percentiles(IReadOnlyList<double> samples)
    {
        if (samples.Count == 0)
        {
            throw new InvalidOperationException("A required timing sample set is empty.");
        }
        var ordered = samples.OrderBy(value => value).ToArray();
        double At(double percentile)
        {
            var position = (ordered.Length - 1) * percentile;
            var lower = (int)Math.Floor(position);
            var upper = (int)Math.Ceiling(position);
            var fraction = position - lower;
            return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction;
        }
        return new
        {
            sample_count = ordered.Length,
            p50 = At(0.50),
            p95 = At(0.95),
            p99 = At(0.99),
            maximum = ordered[^1],
        };
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
            if (quitAfterSave &&
                (_routeContextProfile || _routeContextReview || _roadVisualProfile ||
                    _roadVisualReview))
            {
                ValidateRouteContextProfile();
            }
            if (quitAfterSave && (_roadVisualProfile || _roadVisualReview))
            {
                ValidateRoadVisualProfile();
            }
            if (quitAfterSave && _longRouteProfile)
            {
                ValidateLongRouteProfile();
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
            Seed: _runSeed,
            Position: position,
            RoutePlan: _streamer.RoutePlan,
            ElapsedSeconds: CaptureElapsedSeconds(),
            Cash: _cash,
            Vehicle: _vehicleCondition,
            Enforcement: _enforcement,
            AssistProfile: _vehicle.AssistProfile)
        {
            Navigation = CaptureNavigationState(),
            WorldStream = _streamer.CaptureStreamSnapshot(),
        };
        var rotation = _vehicle.Basis.GetRotationQuaternion();
        var localVehicle = new LocalVehicleState(
            _vehicle.Position.X,
            _vehicle.Position.Y,
            _vehicle.Position.Z,
            _vehicle.LinearVelocity.X,
            _vehicle.LinearVelocity.Y,
            _vehicle.LinearVelocity.Z,
            _vehicle.AngularVelocity.X,
            _vehicle.AngularVelocity.Y,
            _vehicle.AngularVelocity.Z)
        {
            RotationX = rotation.X,
            RotationY = rotation.Y,
            RotationZ = rotation.Z,
            RotationW = rotation.W,
        };
        return new RunSave(
            RunSave.CurrentSchemaVersion,
            _package.Graph.ContentVersion,
            RunSave.ComputePackageIdentity(_package).PackageChecksum,
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
            throw new InvalidOperationException(
                "Topology profile did not visit every checkpoint: " +
                $"complete={_topologyProfileComplete} " +
                $"started={_topologyTraversalStarted} " +
                $"checkpoint={_topologyCheckpointIndex}/{_topologyCheckpoints.Count} " +
                $"route_distance_m={_streamer.RouteDistanceMeters:F3} " +
                $"target_distance_m={_topologyTraversalEndMeters:F3} " +
                $"grounded={_vehicle.HasBeenGrounded} " +
                $"unsupported_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames}.");
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
        if (!_streamer.HasTerrainBackdrop ||
            !_streamer.JunctionTerrainSurfacesComplete ||
            _streamer.JunctionTerrainSeamCount == 0)
        {
            throw new InvalidOperationException(
                "Topology traversal found an incomplete terrain backdrop or seam surface.");
        }
        GD.Print(
            $"CANNONBALL_TOPOLOGY_OK checkpoints={_topologyCheckpoints.Count} " +
            $"edge={_topologyOverlay.EdgeId} min_lanes={_streamer.MinimumObservedLaneCount} " +
            $"max_lanes={_streamer.MaximumObservedLaneCount} " +
            $"transitions={_streamer.TopologyTransitionCount} " +
            $"minimum_taper_m={_topologyOverlay.MinimumTransitionLengthMeters:0.000} " +
            $"maximum_taper_slope={_topologyOverlay.MaximumTaperSlope:0.000000} " +
            $"maximum_through_lane_drift_m={_topologyOverlay.MaximumThroughLaneDriftMeters:0.000000} " +
            $"transition_collision_chunks={_streamer.TopologyCollisionTransitionChunkCount} " +
            $"gore=true max_paved_width_m={_streamer.MaximumPavedWidthMeters:0.000} " +
            $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
            $"rebases={_streamer.RebaseCount} " +
            $"connector_movements=" +
            $"{string.Join(',', _topologyOverlay.ExpectedTraversedConnectorMovements)} " +
            $"branch_prewarms={_streamer.BranchPrewarmCount} " +
            $"branch_evictions={_streamer.BranchPrewarmEvictionCount} " +
            $"terrain_backdrop=true " +
            $"terrain_seams={_streamer.JunctionTerrainSeamCount} " +
            $"max_seam_gap_m={_streamer.MaximumJunctionGapMeters:0.000} " +
            $"max_unsupported_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} " +
            $"max_visual_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
            $"max_collision_build_ms={_streamer.MaximumCollisionBuildMilliseconds:0.000} " +
            $"override={_topologyOverlay.OverrideId} chunk_failures=0");
    }

    private void ConfigureRouteContextReviewPoints()
    {
        if (_interchangeFixture is null || _interchangeFixture.Package.Semantics is null)
        {
            throw new InvalidOperationException("Route-context fixture is not configured.");
        }
        var transferPlan = _interchangeFixture.Plans[
            RepresentativeInterchangeFixture.TransferPlanId];
        var raw = new List<(double ReviewDistance, double PlacementDistance, RouteContextPlacement Placement)>();
        var omissions = new List<RouteContextOmission>();
        foreach (var edgeId in transferPlan.Selection.EdgeIds)
        {
            var plan = RouteContextPlanner.BuildForEdge(
                _interchangeFixture.Package.Graph,
                _interchangeFixture.Package.Semantics,
                edgeId);
            omissions.AddRange(plan.Omissions);
            foreach (var placement in plan.Placements)
            {
                var placementDistance = _streamer.GetRouteDistance(edgeId, placement.DistanceMeters);
                var reviewOffset = placement.Kind == RouteContextPlacementKind.MileMarker ? 30 : 90;
                raw.Add((
                    Math.Max(_streamer.GetRouteDistance(edgeId, 0), placementDistance - reviewOffset),
                    placementDistance,
                    placement));
            }
        }
        _routeContextOmissions = omissions
            .OrderBy(omission => omission.Id, StringComparer.Ordinal)
            .ToArray();
        _routeContextReviewPoints = raw
            .GroupBy(item => Math.Round(item.ReviewDistance, 3))
            .OrderBy(group => group.Key)
            .Select(group => new RouteContextReviewPoint(
                group.First().ReviewDistance,
                group.Max(item => item.PlacementDistance),
                group.Select(item => item.Placement.Id)
                    .OrderBy(id => id, StringComparer.Ordinal)
                    .ToArray(),
                group.Select(item => item.Placement.Kind).Distinct().Order().ToArray(),
                group.Select(item => item.Placement.RouteIdentityId)
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(id => id, StringComparer.Ordinal)
                    .ToArray(),
                group.Select(item => RouteContextAutomationId(
                        item.Placement.Id,
                        item.Placement.Kind))
                    .OrderBy(id => id, StringComparer.Ordinal)
                    .ToArray()))
            .ToArray();
        if (_routeContextReviewPoints.Count == 0)
        {
            throw new InvalidDataException("Route-context fixture produced no review points.");
        }
    }

    private void BeginNextRouteContextReviewPoint()
    {
        _routeContextStableFrames = 0;
        _routeContextReviewFrames = 0;
        if (_routeContextReviewPointIndex >= _routeContextReviewPoints.Count)
        {
            _routeContextProfileComplete = true;
            SetRouteContextDiagnosticView(enabled: false);
            return;
        }
        _streamer.SetReviewDistance(
            _routeContextReviewPoints[_routeContextReviewPointIndex].ReviewDistanceMeters);
        SetRouteContextDiagnosticView(enabled: false);
    }

    private void AdvanceRouteContextProfile()
    {
        if (!_streamer.ReviewTargetReady || !_streamer.IsStreamingSettled ||
            _routeContextReviewPointIndex >= _routeContextReviewPoints.Count)
        {
            _routeContextStableFrames = 0;
            return;
        }
        var point = _routeContextReviewPoints[_routeContextReviewPointIndex];
        var missingAutomationIds = point.AutomationIds
            .Where(id => !_streamer.RouteContextAutomationIds.Contains(id, StringComparer.Ordinal))
            .ToArray();
        if (missingAutomationIds.Length > 0)
        {
            throw new InvalidOperationException(
                $"Route-context review point is missing nodes: " +
                $"{string.Join(',', missingAutomationIds)}.");
        }

        _routeContextStableFrames++;
        if (_routeContextReview || _roadVisualReview)
        {
            AdvanceRouteContextCamera(point);
            return;
        }
        if (_routeContextStableFrames < StreamingStableFramesPerCheckpoint)
        {
            return;
        }
        CompleteRouteContextReviewPoint(point);
    }

    private void AdvanceRouteContextCamera(RouteContextReviewPoint point)
    {
        if (_routeContextDiagnosticCamera is null)
        {
            throw new InvalidOperationException("Route-context review camera is missing.");
        }
        _routeContextReviewFrames++;
        var forward = _vehicle.TargetRoadForward.Normalized();
        var ahead = (float)Math.Clamp(
            point.PlacementRouteDistanceMeters - point.ReviewDistanceMeters,
            25,
            140);
        var focus = _vehicle.GlobalPosition + forward * ahead + Vector3.Up * 4.5f;
        _routeContextDiagnosticCamera.GlobalPosition =
            _vehicle.GlobalPosition - forward * 12 + Vector3.Up * 5.5f;
        _routeContextDiagnosticCamera.LookAt(focus, Vector3.Up);
        if (_routeContextReviewFrames == 10)
        {
            SetRouteContextDiagnosticView(enabled: true);
        }
        if (_routeContextReviewFrames < 60)
        {
            return;
        }
        CompleteRouteContextReviewPoint(point);
    }

    private void CompleteRouteContextReviewPoint(RouteContextReviewPoint point)
    {
        if (_routeContextReview || _roadVisualReview)
        {
            if (_routeContextDiagnosticCamera is null)
            {
                throw new InvalidOperationException("Route-context review camera is missing.");
            }
            var expectedIds = point.AutomationIds.ToHashSet(StringComparer.Ordinal);
            var diagnostics = _streamer.GetRouteContextLabelDiagnostics(
                    _routeContextDiagnosticCamera)
                .Where(item => expectedIds.Contains(item.AutomationId))
                .ToArray();
            var failures = diagnostics.Where(item =>
                    !item.VisibleInTree ||
                    !item.InCameraFrustum ||
                    item.ForwardDistanceMeters <= 0 ||
                    !item.WithinDeclaredRange)
                .ToArray();
            if (diagnostics.Length != expectedIds.Count || failures.Length > 0)
            {
                throw new InvalidOperationException(
                    $"Route-context labels failed the declared visibility envelope: " +
                    $"expected={expectedIds.Count} observed={diagnostics.Length} " +
                    $"failures={string.Join(',', failures.Select(item => item.AutomationId))}.");
            }
            foreach (var diagnostic in diagnostics)
            {
                GD.Print(
                    $"CANNONBALL_ROUTE_CONTEXT_LABEL_OK id={diagnostic.AutomationId} " +
                    $"distance_m={diagnostic.CameraDistanceMeters:0.0} " +
                    $"forward_m={diagnostic.ForwardDistanceMeters:0.0}");
            }
        }
        GD.Print(
            $"CANNONBALL_ROUTE_CONTEXT_WAYPOINT_OK " +
            $"index={_routeContextReviewPointIndex + 1} " +
            $"of={_routeContextReviewPoints.Count} " +
            $"placements={string.Join(',', point.PlacementIds)} " +
            $"identities={string.Join(',', point.RouteIdentityIds)}");
        if (_roadVisualProfile || _roadVisualReview)
        {
            GD.Print(
                "CANNONBALL_ROAD_VISUAL_PROGRESS " +
                JsonSerializer.Serialize(_streamer.CaptureRoadVisualSnapshot()));
        }
        _routeContextReviewPointIndex++;
        BeginNextRouteContextReviewPoint();
    }

    private void SetRouteContextDiagnosticView(bool enabled)
    {
        if (_routeContextDiagnosticCamera is not null)
        {
            _routeContextDiagnosticCamera.Current = enabled;
        }
        var chaseCamera = _vehicle.GetNodeOrNull<Camera3D>("ChaseCameraArm/ChaseCamera");
        if (chaseCamera is not null)
        {
            chaseCamera.Current = !enabled;
        }
    }

    private void ValidateRouteContextProfile()
    {
        if (_interchangeFixture?.Package.Semantics is null ||
            !_routeContextProfileComplete ||
            _routeContextReviewPointIndex != _routeContextReviewPoints.Count)
        {
            throw new InvalidOperationException(
                "Route-context profile did not complete every review point.");
        }
        var expectedAutomationIds = _routeContextReviewPoints
            .SelectMany(point => point.AutomationIds)
            .ToHashSet(StringComparer.Ordinal);
        if (_streamer.MileMarkersSeen < 4 || _streamer.ExitSignsSeen < 1 ||
            _streamer.HighwayTransferSignsSeen < 1 ||
            expectedAutomationIds.Any(id => !_streamer.RouteContextAutomationIdsSeen.Contains(
                id,
                StringComparer.Ordinal)))
        {
            throw new InvalidOperationException(
                "Route-context renderer did not expose every required semantic node.");
        }
        var placements = _interchangeFixture.Plans[
                RepresentativeInterchangeFixture.TransferPlanId]
            .Selection.EdgeIds
            .SelectMany(edgeId => RouteContextPlanner.BuildForEdge(
                _interchangeFixture.Package.Graph,
                _interchangeFixture.Package.Semantics,
                edgeId).Placements)
            .ToArray();
        var concurrentMarkers = placements
            .Where(placement => placement.Kind == RouteContextPlacementKind.MileMarker)
            .GroupBy(placement => (placement.EdgeId, placement.DistanceMeters))
            .Max(group => group.Count());
        var resetValues = placements
            .Where(placement => placement.Kind == RouteContextPlacementKind.MileMarker)
            .Select(placement => placement.SecondaryText)
            .Distinct(StringComparer.Ordinal)
            .Count();
        var missingMarkerOmission = _routeContextOmissions.SingleOrDefault(omission =>
            omission.Id == "marker-us36-missing-anchor");
        if (concurrentMarkers < 2 || resetValues < 3 ||
            missingMarkerOmission is null ||
            missingMarkerOmission.EdgeId != "between-interchanges" ||
            missingMarkerOmission.RouteIdentityId != "route-us36" ||
            missingMarkerOmission.Provenance?.AuthoredOverrideId !=
                RepresentativeInterchangeFixture.AuthoredOverrideId ||
            !missingMarkerOmission.Reason.Contains("no exact colocated", StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "Route-context fixture did not prove concurrency, numbering changes, and the " +
                "provenance-bearing missing-marker omission.");
        }
        GD.Print(
            $"CANNONBALL_ROUTE_CONTEXT_OK review_points={_routeContextReviewPoints.Count} " +
            $"mile_markers={_streamer.MileMarkersSeen} " +
            $"exit_signs={_streamer.ExitSignsSeen} " +
            $"transfer_signs={_streamer.HighwayTransferSignsSeen} " +
            $"concurrent_markers={concurrentMarkers} " +
            $"distinct_mile_values={resetValues} omissions={_routeContextOmissions.Count} " +
            $"automation_nodes={_streamer.RouteContextAutomationIdsSeen.Count} " +
            $"max_visual_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
            $"chunk_failures={_streamer.ChunkFailureCount}");
    }

    private void AdvanceRoadVisualProfile()
    {
        if (!_streamer.IsStreamingSettled)
        {
            return;
        }
        var snapshot = _streamer.CaptureRoadVisualSnapshot();
        if (snapshot.RouteShieldCount < 2 || snapshot.ServiceIconCount < 2)
        {
            return;
        }
        ValidateRoadVisualSnapshot(snapshot);
        ValidateRoadVisualBudgets();
        _roadVisualProfileComplete = true;
        GD.Print(
            $"CANNONBALL_ROAD_VISUAL_OK profile={snapshot.ProfileId} " +
            $"chunks={snapshot.ChunkCount} reflectors={snapshot.ReflectorCount} " +
            $"barriers={snapshot.BarrierSegmentCount} " +
            $"guardrails={snapshot.GuardrailSegmentCount} " +
            $"shields={snapshot.RouteShieldCount} services={snapshot.ServiceIconCount} " +
            $"gore_chunks={snapshot.GoreChunkCount} " +
            $"opposing_carriageway_chunks={_streamer.OpposingCarriagewayChunksSeen} " +
            $"shared_materials={snapshot.SharedMaterialCount} " +
            $"shared_meshes={snapshot.SharedMeshCount} " +
            $"retroreflective_materials={snapshot.RetroreflectiveMaterialCount} " +
            $"max_visual_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
            $"max_collision_build_ms={_streamer.MaximumCollisionBuildMilliseconds:0.000}");
    }

    private void ValidateRoadVisualProfile()
    {
        if (!_roadVisualProfileComplete)
        {
            var incomplete = _streamer.CaptureRoadVisualSnapshot();
            throw new InvalidOperationException(
                "Road-visual profile did not resolve the production-kit contract: " +
                JsonSerializer.Serialize(incomplete));
        }
        ValidateRoadVisualBudgets();
        ValidateRoadVisualSnapshot(_streamer.CaptureRoadVisualSnapshot());
    }

    private void ValidateRoadVisualBudgets()
    {
        if (_streamer.ChunkFailureCount > 0 ||
            _streamer.MaximumBuildMilliseconds >
                WorldStreamer.InitialChunkBuildBudgetMilliseconds ||
            _streamer.MaximumCollisionBuildMilliseconds >
                WorldStreamer.InitialCollisionBuildBudgetMilliseconds)
        {
            throw new InvalidOperationException(
                $"Road-visual profile exceeded a streaming contract: " +
                $"chunk_failures={_streamer.ChunkFailureCount} " +
                $"max_visual_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
                $"max_collision_build_ms=" +
                $"{_streamer.MaximumCollisionBuildMilliseconds:0.000}.");
        }
    }

    private void ValidateRoadVisualSnapshot(RoadVisualSnapshot snapshot)
    {
        var expectedProfile = OS.GetCmdlineUserArgs().Contains(
            "--graybox-road-assets",
            StringComparer.Ordinal)
            ? "graybox"
            : "production";
        if (snapshot.ProfileId != expectedProfile || snapshot.ChunkCount < 1 ||
            !snapshot.AllContractsResolved || snapshot.ReflectorCount < 1 ||
            snapshot.BarrierSegmentCount < 1 || snapshot.GuardrailSegmentCount < 1 ||
            snapshot.RouteShieldCount < 2 || snapshot.ServiceIconCount < 2 ||
            snapshot.SharedMaterialCount != 18 || snapshot.SharedMeshCount != 5 ||
            snapshot.RetroreflectiveMaterialCount != 11 ||
            (_interchangeFixture is not null && _streamer.OpposingCarriagewayChunksSeen < 1))
        {
            throw new InvalidOperationException(
                "Road-visual kit contract failed: " +
                JsonSerializer.Serialize(snapshot));
        }
    }

    private static string RouteContextAutomationId(
        string placementId,
        RouteContextPlacementKind kind) => kind switch
    {
        RouteContextPlacementKind.MileMarker => $"route-context.marker.{placementId}",
        RouteContextPlacementKind.ExitSign => $"route-context.exit.{placementId}",
        RouteContextPlacementKind.HighwayTransferSign =>
            $"route-context.transfer.{placementId}",
        _ => throw new ArgumentOutOfRangeException(nameof(kind)),
    };

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
        var limits = _interchangeFixture.GeometryLimits;
        if (geometry.GradeSeparatedCrossings < limits.MinimumGradeSeparatedCrossings ||
            geometry.MinimumVerticalClearanceMeters < limits.MinimumVerticalClearanceMeters ||
            geometry.SelfIntersections > limits.MaximumSelfIntersections ||
            geometry.InvalidShortcuts > limits.MaximumInvalidShortcuts ||
            geometry.ParallelCarriagewayPairs < limits.MinimumParallelCarriagewayPairs ||
            geometry.MaximumAbsoluteGrade > limits.MaximumAbsoluteGrade ||
            geometry.MaximumAbsoluteCurvaturePerMeter >
                limits.MaximumAbsoluteCurvaturePerMeter ||
            geometry.MinimumSightlineMeters < limits.MinimumSightlineMeters)
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
            $"max_abs_grade={geometry.MaximumAbsoluteGrade:0.000000} " +
            $"max_abs_curvature_per_m={geometry.MaximumAbsoluteCurvaturePerMeter:0.000000} " +
            $"minimum_sightline_m={geometry.MinimumSightlineMeters:0.000} " +
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

    private static string? OptionalArgument(IReadOnlyList<string> arguments, string name)
    {
        var prefix = name + "=";
        var inline = arguments.FirstOrDefault(value =>
            value.StartsWith(prefix, StringComparison.Ordinal));
        if (inline is not null)
        {
            return inline[prefix.Length..];
        }
        var index = ArgumentIndex(arguments, name);
        return index >= 0 && index + 1 < arguments.Count ? arguments[index + 1] : null;
    }

    private static ulong OptionalUnsignedInteger(
        IReadOnlyList<string> arguments,
        string name,
        ulong defaultValue)
    {
        var raw = OptionalArgument(arguments, name);
        if (raw is null)
        {
            return defaultValue;
        }
        if (!ulong.TryParse(
                raw,
                System.Globalization.NumberStyles.None,
                System.Globalization.CultureInfo.InvariantCulture,
                out var value))
        {
            throw new ArgumentException($"Game argument '{name}' must be an unsigned integer.");
        }
        return value;
    }

    private static IReadOnlyList<double> OptionalDoubleList(
        IReadOnlyList<string> arguments,
        string name,
        IReadOnlyList<double> defaultValue,
        double exclusiveMaximum)
    {
        var raw = OptionalArgument(arguments, name);
        if (raw is null)
        {
            return defaultValue.Where(value => value < exclusiveMaximum).ToArray();
        }
        var values = raw.Split(',', StringSplitOptions.RemoveEmptyEntries)
            .Select(value =>
            {
                if (!double.TryParse(
                        value,
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture,
                        out var parsed) ||
                    !double.IsFinite(parsed) || parsed <= 0 || parsed >= exclusiveMaximum)
                {
                    throw new ArgumentException(
                        $"Game argument '{name}' values must be positive and below " +
                        $"{exclusiveMaximum:0.###}.");
                }
                return parsed;
            })
            .Distinct()
            .OrderBy(value => value)
            .ToArray();
        if (values.Length == 0)
        {
            throw new ArgumentException($"Game argument '{name}' needs at least one value.");
        }
        return values;
    }

    private static bool OptionalBoolean(
        IReadOnlyList<string> arguments,
        string name,
        bool defaultValue)
    {
        var raw = OptionalArgument(arguments, name);
        if (raw is null)
        {
            return defaultValue;
        }
        if (!bool.TryParse(raw, out var value))
        {
            throw new ArgumentException($"Game argument '{name}' must be true or false.");
        }
        return value;
    }

    private static void ValidateRequestedPlatform(string requested)
    {
        var actual = OperatingSystem.IsWindows() ? "windows"
            : OperatingSystem.IsLinux() ? "linux"
            : OperatingSystem.IsMacOS() ? "macos"
            : "unknown";
        if (!string.Equals(requested, "current", StringComparison.OrdinalIgnoreCase) &&
            !string.Equals(requested, actual, StringComparison.OrdinalIgnoreCase))
        {
            throw new PlatformNotSupportedException(
                $"Scenario requested platform '{requested}', but the current platform is '{actual}'.");
        }
    }

    private static string? OptionalEnvironment(string name)
    {
        var value = System.Environment.GetEnvironmentVariable(name);
        return string.IsNullOrWhiteSpace(value) ? null : value;
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
        AddKeyAction("toggle_trip_map", Key.M);
        AddKeyAction("trip_map_pan_left", Key.Left);
        AddKeyAction("trip_map_pan_right", Key.Right);
        AddKeyAction("trip_map_pan_up", Key.Up);
        AddKeyAction("trip_map_pan_down", Key.Down);
        AddKeyAction("trip_map_zoom_in", Key.Equal);
        AddKeyAction("trip_map_zoom_out", Key.Minus);
        AddKeyAction("trip_map_recenter", Key.C);
        AddKeyAction("trip_map_previous", Key.Pageup);
        AddKeyAction("trip_map_next", Key.Pagedown);
        AddJoyAxisAction("accelerate", JoyAxis.TriggerRight, 1);
        AddJoyAxisAction("brake", JoyAxis.TriggerLeft, 1);
        AddJoyAxisAction("steer_left", JoyAxis.LeftX, -1);
        AddJoyAxisAction("steer_right", JoyAxis.LeftX, 1);
        AddJoyButtonAction("toggle_trip_map", JoyButton.Back);
        AddJoyButtonAction("trip_map_pan_left", JoyButton.DpadLeft);
        AddJoyButtonAction("trip_map_pan_right", JoyButton.DpadRight);
        AddJoyButtonAction("trip_map_pan_up", JoyButton.DpadUp);
        AddJoyButtonAction("trip_map_pan_down", JoyButton.DpadDown);
        AddJoyButtonAction("trip_map_zoom_in", JoyButton.RightShoulder);
        AddJoyButtonAction("trip_map_zoom_out", JoyButton.LeftShoulder);
        AddJoyButtonAction("trip_map_recenter", JoyButton.LeftStick);
        AddJoyButtonAction("trip_map_previous", JoyButton.X);
        AddJoyButtonAction("trip_map_next", JoyButton.A);
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

    private static void AddJoyButtonAction(StringName action, JoyButton button)
    {
        if (!InputMap.HasAction(action))
        {
            InputMap.AddAction(action, 0.12f);
        }
        InputMap.ActionAddEvent(action, new InputEventJoypadButton { ButtonIndex = button });
    }

    private void OpenTripMap()
    {
        try
        {
            var state = TripMapProjector.Project(
                _package,
                _streamer.CurrentEdgeId,
                _streamer.CurrentEdgeDistanceMeters,
                _streamer.RoutePlan,
                _vehicle.AssistProfile,
                _vehicle.SpeedMetersPerSecond);
            _tripMapPauseStartedTicks = Time.GetTicksMsec();
            _tripMap.Open(state);
        }
        catch (Exception exception)
        {
            GD.PushError($"Trip map could not open: {exception.Message}");
        }
    }

    private void OnTripMapClosed()
    {
        if (_tripMapPauseStartedTicks == 0)
        {
            return;
        }
        _tripMapPausedSeconds +=
            (Time.GetTicksMsec() - _tripMapPauseStartedTicks) / 1000.0;
        _tripMapPauseStartedTicks = 0;
    }

    private double CaptureElapsedSeconds()
    {
        var pausedSeconds = _tripMapPausedSeconds;
        if (_tripMapPauseStartedTicks != 0)
        {
            pausedSeconds += (Time.GetTicksMsec() - _tripMapPauseStartedTicks) / 1000.0;
        }
        return _elapsedSecondsBase +
            Math.Max(0, (Time.GetTicksMsec() - _sessionStartedTicks) / 1000.0 - pausedSeconds);
    }

    private sealed record TransportProbeResult(
        double RequestedMiles,
        double UniqueRouteMiles,
        int Repetitions,
        int VerifiedChunkReads);

    private sealed record RouteContextReviewPoint(
        double ReviewDistanceMeters,
        double PlacementRouteDistanceMeters,
        IReadOnlyList<string> PlacementIds,
        IReadOnlyList<RouteContextPlacementKind> Kinds,
        IReadOnlyList<string> RouteIdentityIds,
        IReadOnlyList<string> AutomationIds);
}
