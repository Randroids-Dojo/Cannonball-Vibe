using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Game.Vehicle;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class WorldStreamer : Node3D
{
    public const double VisualLookAheadMeters = 10_000;
    public const double ActivePhysicsAheadMeters = 2_000;
    public const double ActivePhysicsBehindMeters = 50;
    public const double RetainBehindMeters = 500;
    public const double PrefetchHorizonSeconds = 112;
    public const float RebaseThresholdMeters = 1_000;
    public const double ChunkBuildBudgetMilliseconds = 40;
    public const double InitialChunkBuildBudgetMilliseconds = 50;
    public const double CollisionBuildBudgetMilliseconds = 40;
    public const double InitialCollisionBuildBudgetMilliseconds = 50;
    public const int MaximumConcurrentChunkReads = 2;
    public const double ShortCorridorLoopResetLeadMeters = 25;

    private readonly Dictionary<string, RoadChunk> _loaded = new(StringComparer.Ordinal);
    private readonly Dictionary<string, JunctionSeam> _junctionSeams = new(StringComparer.Ordinal);
    private readonly Dictionary<string, RouteChunkContent> _content = new(StringComparer.Ordinal);
    private readonly Dictionary<string, PendingRead> _pending = new(StringComparer.Ordinal);
    private readonly Queue<string> _loadQueue = [];
    private readonly HashSet<string> _queued = new(StringComparer.Ordinal);
    private readonly HashSet<string> _failed = new(StringComparer.Ordinal);
    private HashSet<string> _desiredVisual = new(StringComparer.Ordinal);
    private HashSet<string> _desiredCollision = new(StringComparer.Ordinal);
    private RouteContentPackage _package = null!;
    private IRouteChunkContentSource _source = null!;
    private LinearRoutePlan _routePlan = null!;
    private HashSet<string> _routePlanEdgeIds = new(StringComparer.Ordinal);
    private IReadOnlyDictionary<(string FromEdgeId, string ToEdgeId), JunctionConnector>
        _routePlanConnectors =
            new Dictionary<(string FromEdgeId, string ToEdgeId), JunctionConnector>();
    private IReadOnlyList<RouteManifestSpan> _manifests = [];
    private RouteFrame _frame = null!;
    private CannonballVehicle? _vehicle;
    private RouteWorldPoint _localOriginWorld;
    private string _currentEdgeId = string.Empty;
    private double _routeDistanceMeters;
    private double _lateralOffsetMeters;
    private RouteWorldPoint _initialRoadWorldPoint;
    private double? _reviewTargetDistanceMeters;
    private bool _reviewTargetReady;
    private readonly HashSet<string> _reviewReadyChunksSeen = new(StringComparer.Ordinal);
    private readonly HashSet<string> _reviewEdgesVisited = new(StringComparer.Ordinal);
    private readonly HashSet<string> _topologyObservedChunks = new(StringComparer.Ordinal);
    private readonly HashSet<string> _topologyCollisionChunks = new(StringComparer.Ordinal);
    private readonly HashSet<JunctionMovement> _observedConnectorMovements = [];
    private readonly HashSet<string> _observedConnectorIds = new(StringComparer.Ordinal);
    private readonly HashSet<string> _desiredBranchPrewarm = new(StringComparer.Ordinal);
    private readonly HashSet<string> _branchPrewarmSeen = new(StringComparer.Ordinal);
    private readonly HashSet<string> _branchPrewarmEvicted = new(StringComparer.Ordinal);
    private readonly HashSet<string> _junctionSeamsBuilt = new(StringComparer.Ordinal);
    private readonly HashSet<string> _routeContextAutomationIds = new(StringComparer.Ordinal);
    private readonly List<double> _chunkBuildSamplesMilliseconds = [];
    private readonly List<double> _collisionBuildSamplesMilliseconds = [];
    private bool _preserveResumeStateThroughReady;

    public double RouteDistanceMeters => _routeDistanceMeters;
    public double LocalOriginMeters { get; private set; }
    public double CurrentLookAheadMeters { get; private set; } = ActivePhysicsAheadMeters;
    public int LoadedChunkCount => _loaded.Count;
    public int ExpectedChunkCount => _manifests.Count;
    public int ReviewReadyChunkCount => _loaded.Values.Count(chunk => chunk.HasReviewGeometry());
    public int RebaseCount { get; private set; }
    public int ChunkFailureCount { get; private set; }
    public double MaximumBuildMilliseconds { get; private set; }
    public double MaximumCollisionBuildMilliseconds { get; private set; }
    public int CollisionBuildCount { get; private set; }
    public int CollisionRemovalCount { get; private set; }
    public int MinimumObservedLaneCount { get; private set; } = int.MaxValue;
    public int MaximumObservedLaneCount { get; private set; }
    public int TopologyTransitionCount { get; private set; }
    public int TopologyCollisionTransitionChunkCount => _topologyCollisionChunks.Count;
    public bool ObservedGoreGeometry { get; private set; }
    public double MaximumPavedWidthMeters { get; private set; }
    public IReadOnlyCollection<JunctionMovement> ObservedConnectorMovements =>
        _observedConnectorMovements;
    public IReadOnlyCollection<string> ObservedConnectorIds => _observedConnectorIds;
    public IReadOnlyCollection<string> PrewarmedBranchChunkIds => _branchPrewarmSeen;
    public IReadOnlyCollection<string> DesiredBranchPrewarmChunkIds => _desiredBranchPrewarm;
    public IReadOnlyCollection<string> EvictedBranchChunkIds => _branchPrewarmEvicted;
    public int BranchPrewarmCount => _branchPrewarmSeen.Count;
    public int BranchPrewarmEvictionCount => _branchPrewarmEvicted.Count;
    public int MaximumVisualChunkCount { get; private set; }
    public int MaximumCollisionChunkCount { get; private set; }
    public int ObservedVisualOnlyChunkCount { get; private set; }
    public string CurrentEdgeId => _currentEdgeId;
    public double CurrentEdgeDistanceMeters =>
        _routeDistanceMeters - _routePlan.GetEdge(_currentEdgeId).StartMeters;
    public double CurrentLateralOffsetMeters => _lateralOffsetMeters;
    public int CurrentLaneIndex { get; private set; }
    public string CurrentStableLaneId { get; private set; } = string.Empty;
    public string ActiveConnectorId { get; private set; } = string.Empty;
    public string ContentVersion => _package.Graph.ContentVersion;
    public double TotalRouteLengthMeters => RouteLengthMeters;
    public IReadOnlyList<string> RoutePlan => _routePlan.EdgeIds;
    public Vector3 InitialRoadPoint { get; private set; }
    public Vector3 InitialRoadForward { get; private set; }
    public bool ShortCorridorLoopEnabled { get; set; }
    public int CompletedShortCorridorLoops { get; private set; }
    public int CrossedReviewDistanceThresholdCount { get; private set; }
    public double MaximumLocalCoordinateMeters { get; private set; }
    public double MaximumJunctionGapMeters { get; private set; }
    public int JunctionSeamBuildCount => _junctionSeamsBuilt.Count;
    public IReadOnlyCollection<string> JunctionSeamIdsBuilt => _junctionSeamsBuilt;
    public IReadOnlyCollection<string> RouteContextAutomationIds => _routeContextAutomationIds;
    public int MileMarkerCount { get; private set; }
    public int ExitSignCount { get; private set; }
    public int HighwayTransferSignCount { get; private set; }
    public IReadOnlyCollection<string> ReviewReadyChunkIdsSeen => _reviewReadyChunksSeen;
    public IReadOnlyCollection<string> ReviewEdgeIdsVisited => _reviewEdgesVisited;
    public IReadOnlyList<double> ChunkBuildSamplesMilliseconds => _chunkBuildSamplesMilliseconds;
    public IReadOnlyList<double> CollisionBuildSamplesMilliseconds =>
        _collisionBuildSamplesMilliseconds;

    public WorldStreamSnapshot CaptureStreamSnapshot() => new(
        _localOriginWorld.X,
        _localOriginWorld.Y,
        _localOriginWorld.Z,
        LocalOriginMeters,
        RebaseCount,
        _loaded.Keys.OrderBy(id => id, StringComparer.Ordinal).ToArray(),
        _loaded.Where(entry => entry.Value.HasCollision)
            .Select(entry => entry.Key)
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray());
    public bool ReviewTargetReady => _reviewTargetReady;
    public int ReviewReadyChunkCountSeen => _reviewReadyChunksSeen.Count;
    public int ReviewEdgeCountVisited => _reviewEdgesVisited.Count;
    public int CollisionChunkCount => _loaded.Values.Count(chunk => chunk.HasCollision);
    public int VisualOnlyChunkCount => _loaded.Count - CollisionChunkCount;
    public int DesiredVisualChunkCount => _desiredVisual.Count;
    public int DesiredCollisionChunkCount => _desiredCollision.Count;
    public bool IsStreamingSettled =>
        _desiredVisual.SetEquals(_loaded.Keys) &&
        !_pending.Keys.Any(_desiredVisual.Contains) &&
        _desiredCollision.SetEquals(_loaded
            .Where(entry => entry.Value.HasCollision)
            .Select(entry => entry.Key));
    public double LoadedVisualAheadMeters => _loaded.Count == 0
        ? 0
        : Math.Max(
            0,
            _manifests
                .Where(span => _loaded.ContainsKey(span.Manifest.Id))
                .Select(span => span.EndMeters)
                .DefaultIfEmpty(_routeDistanceMeters)
                .Max() - _routeDistanceMeters);

    public static ChunkManifest FindInitialManifest(
        RouteContentPackage package,
        IReadOnlyList<string>? routePlanEdgeIds = null)
    {
        ArgumentNullException.ThrowIfNull(package);
        var plan = LinearRoutePlan.Build(
            package.Graph,
            routePlanEdgeIds ?? package.Chunks.Values.Select(manifest => manifest.EdgeId));
        var firstEdgeId = plan.Edges[0].EdgeId;
        return package.Chunks.Values
            .Where(manifest => string.Equals(manifest.EdgeId, firstEdgeId, StringComparison.Ordinal))
            .OrderBy(manifest => manifest.StartMeters)
            .ThenBy(manifest => manifest.Id, StringComparer.Ordinal)
            .FirstOrDefault()
            ?? throw new InvalidDataException($"Route edge '{firstEdgeId}' has no chunk manifests.");
    }

    public static ChunkManifest FindManifest(
        RouteContentPackage package,
        string edgeId,
        double edgeDistanceMeters)
    {
        ArgumentNullException.ThrowIfNull(package);
        ArgumentException.ThrowIfNullOrWhiteSpace(edgeId);
        var edge = package.Graph.GetEdge(edgeId);
        if (!double.IsFinite(edgeDistanceMeters) || edgeDistanceMeters < 0 ||
            edgeDistanceMeters > edge.LengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(edgeDistanceMeters));
        }
        return package.Chunks.Values
            .Where(manifest =>
                string.Equals(manifest.EdgeId, edgeId, StringComparison.Ordinal) &&
                manifest.StartMeters <= edgeDistanceMeters &&
                manifest.EndMeters >= edgeDistanceMeters)
            .OrderBy(manifest => edgeDistanceMeters == manifest.EndMeters ? 1 : 0)
            .ThenBy(manifest => manifest.StartMeters)
            .ThenBy(manifest => manifest.Id, StringComparer.Ordinal)
            .FirstOrDefault()
            ?? throw new InvalidDataException(
                $"Route edge '{edgeId}' has no chunk at {edgeDistanceMeters:F3} meters.");
    }

    public void Configure(
        RouteContentPackage package,
        IRouteChunkContentSource source,
        RouteChunkContent initialChunk,
        IReadOnlyList<string>? routePlanEdgeIds = null,
        IReadOnlyList<string>? routePlanConnectorIds = null,
        RoutePosition? resumePosition = null,
        WorldStreamSnapshot? resumeStream = null,
        IReadOnlyList<RouteChunkContent>? resumeChunks = null,
        RouteNavigationState? resumeNavigation = null)
    {
        if (IsInsideTree())
        {
            throw new InvalidOperationException("WorldStreamer must be configured before entering the scene tree.");
        }
        _package = package;
        _source = source;
        _routePlan = LinearRoutePlan.Build(
            package.Graph,
            routePlanEdgeIds ?? package.Chunks.Values.Select(manifest => manifest.EdgeId));
        _routePlanEdgeIds = _routePlan.EdgeIds.ToHashSet(StringComparer.Ordinal);
        _routePlanConnectors = BuildRoutePlanConnectors(routePlanConnectorIds);
        if (!string.Equals(initialChunk.EdgeId, _routePlan.Edges[0].EdgeId, StringComparison.Ordinal) ||
            initialChunk.StartMeters != 0)
        {
            throw new InvalidDataException("The initial route chunk is not the first chunk in the corridor plan.");
        }
        if (resumePosition is { } position)
        {
            _preserveResumeStateThroughReady = true;
            var edge = package.Graph.GetEdge(position.EdgeId);
            position.Validate(edge);
            if (!_routePlanEdgeIds.Contains(position.EdgeId))
            {
                throw new InvalidDataException(
                    $"Resume edge '{position.EdgeId}' is outside the selected route plan.");
            }
            _currentEdgeId = position.EdgeId;
            _routeDistanceMeters = _routePlan.GetEdge(position.EdgeId).StartMeters +
                position.DistanceMeters;
            _lateralOffsetMeters = position.LateralOffsetMeters;
            CurrentLaneIndex = position.LaneIndex;
            CurrentStableLaneId = position.StableLaneId
                ?? edge.GetLaneSection(position.DistanceMeters).Lanes.Single(lane =>
                    lane.Index == position.LaneIndex).Id;
            if (resumeStream is { } stream)
            {
                _localOriginWorld = new RouteWorldPoint(
                    stream.OriginWorldX,
                    stream.OriginWorldY,
                    stream.OriginWorldZ);
                LocalOriginMeters = stream.LocalOriginRouteMeters;
                RebaseCount = stream.RebaseCount;
            }
            UpdateCurrentLane();
            ActiveConnectorId = resumeNavigation?.ActiveConnectorId ?? string.Empty;
        }
        else
        {
            _currentEdgeId = initialChunk.EdgeId;
            UpdateCurrentLane();
        }
        _manifests = package.Chunks.Values
            .Where(manifest => _routePlanEdgeIds.Contains(manifest.EdgeId))
            .Select(manifest =>
            {
                var edge = _routePlan.GetEdge(manifest.EdgeId);
                return new RouteManifestSpan(
                    manifest,
                    edge.StartMeters + manifest.StartMeters,
                    edge.StartMeters + manifest.EndMeters);
            })
            .OrderBy(span => span.StartMeters)
            .ThenBy(span => span.Manifest.Id, StringComparer.Ordinal)
            .ToArray();
        if (_manifests.Count == 0)
        {
            throw new InvalidDataException($"Route edge '{_currentEdgeId}' has no chunk manifests.");
        }
        _frame = new RouteFrame(initialChunk.Samples);
        _initialRoadWorldPoint = _frame.ToWorld(initialChunk.Samples[0]);
        InitialRoadPoint = _initialRoadWorldPoint.RelativeTo(_localOriginWorld);
        InitialRoadForward = _frame.InitialForward;
        if (resumePosition is null)
        {
            AttachChunk(initialChunk, InitialChunkBuildBudgetMilliseconds);
        }
        else
        {
            if (resumeChunks is null || resumeChunks.Count == 0)
            {
                throw new InvalidDataException(
                    "Resume state does not contain any loaded route chunks.");
            }
            foreach (var content in resumeChunks.OrderBy(content => content.Id, StringComparer.Ordinal))
            {
                AttachChunk(content, InitialChunkBuildBudgetMilliseconds);
            }
            if (!_content.Values.Any(content =>
                    string.Equals(content.EdgeId, _currentEdgeId, StringComparison.Ordinal) &&
                    CurrentEdgeDistanceMeters >= content.StartMeters &&
                    CurrentEdgeDistanceMeters <= content.EndMeters))
            {
                throw new InvalidDataException(
                    "Resume stream state does not contain the saved route position.");
            }
        }
        var resumedCollisionIds = resumeStream?.CollisionChunkIds.ToHashSet(StringComparer.Ordinal);
        foreach (var chunk in _loaded.Values)
        {
            UpdateCollisionState(
                chunk,
                active: resumedCollisionIds?.Contains(chunk.ChunkId) ??
                    string.Equals(chunk.EdgeId, _currentEdgeId, StringComparison.Ordinal),
                buildBudgetMilliseconds: InitialCollisionBuildBudgetMilliseconds);
        }
    }

    public override void _Ready()
    {
        if (_manifests.Count == 0)
        {
            throw new InvalidOperationException("WorldStreamer was not configured with a route package.");
        }
        if (!_preserveResumeStateThroughReady)
        {
            RefreshDesiredChunks();
        }
    }

    public override void _Process(double delta)
    {
        _ = delta;
        _preserveResumeStateThroughReady = false;
        CompletePendingLoads();
        RefreshDesiredChunks();
    }

    public override void _PhysicsProcess(double delta)
    {
        _ = delta;
        if (_vehicle is null)
        {
            return;
        }

        if (_reviewTargetDistanceMeters is { } reviewDistance)
        {
            _routeDistanceMeters = reviewDistance;
            UpdateCurrentEdge();
            TryPlaceVehicleForReview();
            return;
        }

        var previousEdgeId = _currentEdgeId;
        var previousLaneId = CurrentStableLaneId;
        UpdateRouteProjection();
        UpdateCurrentEdge();
        if (!string.Equals(previousEdgeId, _currentEdgeId, StringComparison.Ordinal))
        {
            UpdateLaneAcrossRouteEdges(previousEdgeId, previousLaneId);
        }
        else
        {
            UpdateCurrentLane();
        }
        var crossedSeams = _routeDistanceMeters >= 300 ? 3
            : _routeDistanceMeters >= 200 ? 2
            : _routeDistanceMeters >= 100 ? 1
            : 0;
        CrossedReviewDistanceThresholdCount = Math.Max(
            CrossedReviewDistanceThresholdCount,
            crossedSeams);
        if (ShortCorridorLoopEnabled &&
            _routeDistanceMeters >= Math.Max(0, RouteLengthMeters - ShortCorridorLoopResetLeadMeters))
        {
            _routeDistanceMeters = 0;
            UpdateCurrentEdge();
            _lateralOffsetMeters = 0;
            UpdateCurrentLane();
            var resetPoint = _initialRoadWorldPoint.RelativeTo(_localOriginWorld);
            _vehicle.RouteDistanceMeters = 0;
            _vehicle.TargetRoadPoint = resetPoint;
            _vehicle.TargetRoadForward = InitialRoadForward;
            _vehicle.RequestResetToRoad(resetPoint, InitialRoadForward);
            CompletedShortCorridorLoops++;
            GD.Print($"CANNONBALL_SHORT_CORRIDOR_LOOP count={CompletedShortCorridorLoops}");
            return;
        }
        var targetDistance = Math.Min(RouteLengthMeters, _routeDistanceMeters + 20);
        var target = GetRoadPose(targetDistance);
        var targetPoint = OffsetForActiveLane(target.Point, target.Forward, targetDistance);
        _vehicle.RouteDistanceMeters = _routeDistanceMeters;
        _vehicle.TargetRoadPoint = targetPoint.RelativeTo(_localOriginWorld);
        _vehicle.TargetRoadForward = target.Forward;

        var horizontal = new Vector3(_vehicle.Position.X, 0, _vehicle.Position.Z);
        if (horizontal.Length() < RebaseThresholdMeters)
        {
            return;
        }

        Rebase(horizontal);
    }

    public void Track(CannonballVehicle vehicle)
    {
        _vehicle = vehicle;
        vehicle.RouteDistanceMeters = _routeDistanceMeters;
        var pose = GetRoadPose(_routeDistanceMeters);
        vehicle.TargetRoadPoint = OffsetForActiveLane(
            pose.Point,
            pose.Forward,
            _routeDistanceMeters).RelativeTo(_localOriginWorld);
        vehicle.TargetRoadForward = pose.Forward;
    }

    public void SetReviewDistance(double distanceMeters)
    {
        _reviewTargetDistanceMeters = Math.Clamp(distanceMeters, 0, RouteLengthMeters);
        _routeDistanceMeters = _reviewTargetDistanceMeters.Value;
        _reviewTargetReady = false;
        ActiveConnectorId = string.Empty;
        UpdateCurrentEdge();
        UpdateCurrentLane();
        RefreshDesiredChunks();
    }

    public void SetReviewPosition(double distanceMeters, string stableLaneId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(stableLaneId);
        _reviewTargetDistanceMeters = Math.Clamp(distanceMeters, 0, RouteLengthMeters);
        _routeDistanceMeters = _reviewTargetDistanceMeters.Value;
        _reviewTargetReady = false;
        ActiveConnectorId = string.Empty;
        UpdateCurrentEdge();
        var edge = _package.Graph.GetEdge(_currentEdgeId);
        var layout = LaneGeometryProfile.Evaluate(edge, CurrentEdgeDistanceMeters);
        var lane = layout.Lanes.SingleOrDefault(candidate =>
                string.Equals(candidate.Id, stableLaneId, StringComparison.Ordinal) &&
                candidate.WidthMeters > 0.5)
            ?? throw new InvalidDataException(
                $"Route edge '{edge.Id}' has no active lane '{stableLaneId}' at " +
                $"{CurrentEdgeDistanceMeters:F3} meters.");
        _lateralOffsetMeters = lane.CenterMeters;
        CurrentLaneIndex = lane.Index;
        CurrentStableLaneId = lane.Id;
        UpdateCurrentLane();
        RefreshDesiredChunks();
    }

    public double GetRouteDistance(string edgeId, double edgeDistanceMeters)
    {
        var planEdge = _routePlan.GetEdge(edgeId);
        var edge = _package.Graph.GetEdge(edgeId);
        if (!double.IsFinite(edgeDistanceMeters) || edgeDistanceMeters < 0 ||
            edgeDistanceMeters > edge.LengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(edgeDistanceMeters));
        }
        return planEdge.StartMeters + edgeDistanceMeters;
    }

    public void BeginReviewTraversal()
    {
        if (_reviewTargetDistanceMeters is null || !_reviewTargetReady || _vehicle is null)
        {
            throw new InvalidOperationException(
                "Review traversal requires a settled review target and tracked vehicle.");
        }
        var pose = GetRoadPose(_routeDistanceMeters);
        var roadPoint = OffsetForActiveLane(pose.Point, pose.Forward, _routeDistanceMeters);
        var localPoint = roadPoint.RelativeTo(_localOriginWorld);
        _vehicle.TargetRoadPoint = localPoint;
        _vehicle.TargetRoadForward = pose.Forward;
        _vehicle.RequestResetToRoad(localPoint, pose.Forward);
        _reviewTargetDistanceMeters = null;
        _reviewTargetReady = false;
    }

    public bool HasObservedConnectorMovement(JunctionMovement movement) =>
        _observedConnectorMovements.Contains(movement);

    private double RouteLengthMeters => _routePlan.TotalLengthMeters;

    private void RefreshDesiredChunks()
    {
        var speed = _vehicle?.SpeedMetersPerSecond ?? 0;
        CurrentLookAheadMeters = _reviewTargetDistanceMeters.HasValue
            ? VisualLookAheadMeters
            : Math.Clamp(
                speed * PrefetchHorizonSeconds,
                ActivePhysicsAheadMeters,
                VisualLookAheadMeters);
        var first = Math.Max(0, _routeDistanceMeters - RetainBehindMeters);
        var last = Math.Min(RouteLengthMeters, _routeDistanceMeters + CurrentLookAheadMeters);

        var directVisual = _manifests
            .Where(span => span.EndMeters >= first && span.StartMeters <= last)
            .Select(span => span.Manifest.Id)
            .ToHashSet(StringComparer.Ordinal);
        _desiredBranchPrewarm.Clear();
        foreach (var branchId in directVisual
                     .Select(id => _package.Chunks[id])
                     .SelectMany(manifest => manifest.ProbableBranchChunkIds))
        {
            if (!directVisual.Contains(branchId))
            {
                _desiredBranchPrewarm.Add(branchId);
            }
        }
        _desiredVisual = directVisual
            .Concat(_desiredBranchPrewarm)
            .ToHashSet(StringComparer.Ordinal);
        _desiredCollision = _manifests
            .Where(span =>
                span.EndMeters >= _routeDistanceMeters - ActivePhysicsBehindMeters &&
                span.StartMeters <= _routeDistanceMeters + ActivePhysicsAheadMeters)
            .Select(span => span.Manifest.Id)
            .ToHashSet(StringComparer.Ordinal);
        foreach (var (id, pending) in _pending.ToArray())
        {
            if (!_desiredVisual.Contains(id))
            {
                pending.Cancellation.Cancel();
            }
        }
        foreach (var manifest in _desiredVisual.Select(id => _package.Chunks[id]))
        {
            if (!_loaded.ContainsKey(manifest.Id) &&
                !_pending.ContainsKey(manifest.Id) &&
                !_queued.Contains(manifest.Id) &&
                !_failed.Contains(manifest.Id))
            {
                _queued.Add(manifest.Id);
                _loadQueue.Enqueue(manifest.Id);
            }
        }
        StartPendingReads(_desiredVisual);

        var collisionBuiltThisRefresh = false;
        foreach (var (id, chunk) in _loaded.ToArray())
        {
            var needsCollision = _desiredCollision.Contains(id);
            if (!needsCollision || !collisionBuiltThisRefresh || chunk.HasCollision)
            {
                var changed = UpdateCollisionState(
                    chunk,
                    needsCollision,
                    CollisionBuildBudgetMilliseconds);
                collisionBuiltThisRefresh |= changed && needsCollision;
            }
            if (!_desiredVisual.Contains(id))
            {
                if (_branchPrewarmSeen.Contains(id))
                {
                    _branchPrewarmEvicted.Add(id);
                }
                UpdateCollisionState(
                    chunk,
                    active: false,
                    buildBudgetMilliseconds: CollisionBuildBudgetMilliseconds);
                _loaded.Remove(id);
                _content.Remove(id);
                RemoveJunctionSeamsForChunk(id);
                chunk.QueueFree();
            }
        }
        RefreshJunctionSeamCollisions();
        MaximumVisualChunkCount = Math.Max(MaximumVisualChunkCount, _loaded.Count);
        MaximumCollisionChunkCount = Math.Max(MaximumCollisionChunkCount, CollisionChunkCount);
        ObservedVisualOnlyChunkCount = Math.Max(ObservedVisualOnlyChunkCount, VisualOnlyChunkCount);
    }

    private void CompletePendingLoads()
    {
        var completed = _pending.FirstOrDefault(entry => entry.Value.Task.IsCompleted);
        if (completed.Key is null)
        {
            return;
        }
        var (id, pending) = completed;
        _pending.Remove(id);
        pending.Cancellation.Dispose();
        var task = pending.Task;
        if (task.IsCanceled)
        {
            return;
        }
        if (!task.IsCompletedSuccessfully)
        {
            RecordChunkFailure(id, task.Exception?.GetBaseException());
            return;
        }
        try
        {
            AttachChunk(task.Result);
        }
        catch (Exception exception)
        {
            RecordChunkFailure(id, exception);
        }
    }

    private void StartPendingReads(IReadOnlySet<string> desired)
    {
        while (_pending.Count < MaximumConcurrentChunkReads && _loadQueue.TryDequeue(out var id))
        {
            _queued.Remove(id);
            if (!desired.Contains(id) || _loaded.ContainsKey(id) || _failed.Contains(id))
            {
                continue;
            }
            var cancellation = new CancellationTokenSource();
            _pending.Add(
                id,
                new PendingRead(_source.LoadChunkAsync(id, cancellation.Token).AsTask(), cancellation));
        }
    }

    private void AttachChunk(
        RouteChunkContent content,
        double buildBudgetMilliseconds = ChunkBuildBudgetMilliseconds)
    {
        if (_loaded.ContainsKey(content.Id))
        {
            return;
        }
        var chunk = RoadChunk.Create(
            content,
            _package.Graph.GetEdge(content.EdgeId),
            _package.Graph,
            _package.Semantics,
            _frame,
            _localOriginWorld);
        if (chunk.BuildMilliseconds > buildBudgetMilliseconds)
        {
            chunk.Free();
            throw new InvalidOperationException(
                $"Route chunk '{content.Id}' took {chunk.BuildMilliseconds:0.000} ms to build; " +
                $"budget is {buildBudgetMilliseconds:0.000} ms.");
        }
        _content.Add(content.Id, content);
        _loaded.Add(content.Id, chunk);
        if (_desiredBranchPrewarm.Contains(content.Id))
        {
            _branchPrewarmSeen.Add(content.Id);
        }
        if (_topologyObservedChunks.Add(content.Id))
        {
            MinimumObservedLaneCount = Math.Min(
                MinimumObservedLaneCount,
                chunk.MinimumLaneCount);
            MaximumObservedLaneCount = Math.Max(
                MaximumObservedLaneCount,
                chunk.MaximumLaneCount);
            TopologyTransitionCount += chunk.TransitionCount;
            ObservedGoreGeometry |= chunk.HasGoreGeometry;
            MaximumPavedWidthMeters = Math.Max(
                MaximumPavedWidthMeters,
                chunk.MaximumPavedWidthMeters);
        }
        foreach (var automationId in chunk.RouteContextAutomationIds)
        {
            _routeContextAutomationIds.Add(automationId);
        }
        MileMarkerCount += chunk.MileMarkerCount;
        ExitSignCount += chunk.ExitSignCount;
        HighwayTransferSignCount += chunk.HighwayTransferSignCount;
        if (chunk.HasReviewGeometry())
        {
            _reviewReadyChunksSeen.Add(content.Id);
        }
        MaximumBuildMilliseconds = Math.Max(MaximumBuildMilliseconds, chunk.BuildMilliseconds);
        _chunkBuildSamplesMilliseconds.Add(chunk.BuildMilliseconds);
        AddChild(chunk);
        TryBuildJunctionSeams();
    }

    private void TryBuildJunctionSeams()
    {
        var planPairs = Enumerable.Range(0, Math.Max(0, _routePlan.Edges.Count - 1))
            .Select(index => (
                FromEdgeId: _routePlan.Edges[index].EdgeId,
                ToEdgeId: _routePlan.Edges[index + 1].EdgeId));
        var connectorPairs = _package.Semantics?.JunctionConnectors
            .Select(connector => (
                FromEdgeId: connector.FromEdgeId,
                ToEdgeId: connector.ToEdgeId)) ?? [];
        foreach (var pair in planPairs.Concat(connectorPairs).Distinct())
        {
            var key = $"{pair.FromEdgeId}->{pair.ToEdgeId}";
            if (_junctionSeams.ContainsKey(key))
            {
                continue;
            }
            var fromEdge = _package.Graph.GetEdge(pair.FromEdgeId);
            var toEdge = _package.Graph.GetEdge(pair.ToEdgeId);
            var fromContent = _content.Values.SingleOrDefault(content =>
                content.EdgeId == fromEdge.Id && content.EndMeters == fromEdge.LengthMeters);
            var toContent = _content.Values.SingleOrDefault(content =>
                content.EdgeId == toEdge.Id && content.StartMeters == 0);
            if (fromContent is null || toContent is null)
            {
                continue;
            }
            var seam = JunctionSeam.Create(
                fromContent,
                fromEdge,
                toContent,
                toEdge,
                _frame,
                _localOriginWorld);
            _junctionSeams.Add(key, seam);
            _junctionSeamsBuilt.Add(key);
            MaximumJunctionGapMeters = Math.Max(
                MaximumJunctionGapMeters,
                seam.ConnectionGapMeters);
            AddChild(seam);
        }
        RefreshJunctionSeamCollisions();
    }

    private void RemoveJunctionSeamsForChunk(string chunkId)
    {
        foreach (var (key, seam) in _junctionSeams.Where(entry =>
                     entry.Value.FromChunkId == chunkId ||
                     entry.Value.ToChunkId == chunkId).ToArray())
        {
            _junctionSeams.Remove(key);
            seam.SetCollisionActive(false);
            seam.QueueFree();
        }
    }

    private void RefreshJunctionSeamCollisions()
    {
        foreach (var seam in _junctionSeams.Values)
        {
            seam.SetCollisionActive(
                _loaded.TryGetValue(seam.FromChunkId, out var from) && from.HasCollision &&
                _loaded.TryGetValue(seam.ToChunkId, out var to) && to.HasCollision);
        }
    }

    public void ValidateCurrentStreamingWindows()
    {
        if (!IsStreamingSettled)
        {
            throw new InvalidOperationException("Streaming windows are not settled.");
        }
        var collisionIds = _loaded
            .Where(entry => entry.Value.HasCollision)
            .Select(entry => entry.Key)
            .ToHashSet(StringComparer.Ordinal);
        if (!collisionIds.SetEquals(_desiredCollision))
        {
            throw new InvalidOperationException(
                "Loaded collision chunks do not match the declared near-player window.");
        }
        var expectedAhead = Math.Min(CurrentLookAheadMeters, RouteLengthMeters - _routeDistanceMeters);
        if (LoadedVisualAheadMeters + 1e-6 < expectedAhead)
        {
            throw new InvalidOperationException(
                $"Visual lookahead is {LoadedVisualAheadMeters:F3} m; expected " +
                $"{expectedAhead:F3} m.");
        }
    }

    private bool UpdateCollisionState(
        RoadChunk chunk,
        bool active,
        double buildBudgetMilliseconds)
    {
        var hadCollision = chunk.HasCollision;
        var elapsed = chunk.SetCollisionActive(active);
        if (hadCollision == chunk.HasCollision)
        {
            return false;
        }
        if (!active)
        {
            CollisionRemovalCount++;
            return true;
        }
        CollisionBuildCount++;
        if (chunk.TransitionCount > 0)
        {
            _topologyCollisionChunks.Add(chunk.ChunkId);
        }
        MaximumCollisionBuildMilliseconds = Math.Max(
            MaximumCollisionBuildMilliseconds,
            elapsed);
        _collisionBuildSamplesMilliseconds.Add(elapsed);
        if (elapsed > buildBudgetMilliseconds)
        {
            throw new InvalidOperationException(
                $"Route chunk '{chunk.ChunkId}' took {elapsed:0.000} ms to build collision; " +
                $"budget is {buildBudgetMilliseconds:0.000} ms.");
        }
        return true;
    }

    private void RecordChunkFailure(string id, Exception? exception)
    {
        _failed.Add(id);
        ChunkFailureCount++;
        GD.PushError($"Route chunk '{id}' failed verification or construction: {exception}");
    }

    private void UpdateRouteProjection()
    {
        if (_vehicle is null || _content.Count == 0)
        {
            return;
        }
        IReadOnlySet<string> projectionEdgeIds = _routePlanEdgeIds;
        if (_routePlanConnectors.Count > 0)
        {
            var currentIndex = FindRoutePlanEdgeIndex(_currentEdgeId);
            var bounded = new HashSet<string>(StringComparer.Ordinal) { _currentEdgeId };
            var currentPlanEdge = _routePlan.Edges[currentIndex];
            if (currentIndex + 1 < _routePlan.Edges.Count &&
                currentPlanEdge.EndMeters - _routeDistanceMeters <= 30)
            {
                bounded.Add(_routePlan.Edges[currentIndex + 1].EdgeId);
            }
            projectionEdgeIds = bounded;
        }
        var vehicleX = _localOriginWorld.X + _vehicle.Position.X;
        var vehicleZ = _localOriginWorld.Z + _vehicle.Position.Z;
        var bestDistanceSquared = double.PositiveInfinity;
        var bestRouteDistance = _routeDistanceMeters;
        var bestLateral = _lateralOffsetMeters;
        foreach (var chunk in _content.Values.Where(chunk =>
                     projectionEdgeIds.Contains(chunk.EdgeId)))
        {
            for (var index = 0; index < chunk.Samples.Count - 1; index++)
            {
                var first = _frame.ToWorld(chunk.Samples[index]);
                var second = _frame.ToWorld(chunk.Samples[index + 1]);
                var segmentX = second.X - first.X;
                var segmentZ = second.Z - first.Z;
                var relativeX = vehicleX - first.X;
                var relativeZ = vehicleZ - first.Z;
                var lengthSquared = segmentX * segmentX + segmentZ * segmentZ;
                if (lengthSquared <= 0.0001)
                {
                    continue;
                }
                var factor = Math.Clamp(
                    (relativeX * segmentX + relativeZ * segmentZ) / lengthSquared,
                    0,
                    1);
                var closestX = first.X + segmentX * factor;
                var closestZ = first.Z + segmentZ * factor;
                var errorX = vehicleX - closestX;
                var errorZ = vehicleZ - closestZ;
                var distanceSquared = errorX * errorX + errorZ * errorZ;
                if (distanceSquared >= bestDistanceSquared)
                {
                    continue;
                }
                bestDistanceSquared = distanceSquared;
                var edgeOffset = _routePlan.GetEdge(chunk.EdgeId).StartMeters;
                bestRouteDistance = edgeOffset + chunk.Samples[index].DistanceMeters +
                    (chunk.Samples[index + 1].DistanceMeters - chunk.Samples[index].DistanceMeters) * factor;
                var segmentLength = Math.Sqrt(lengthSquared);
                var rightX = -segmentZ / segmentLength;
                var rightZ = segmentX / segmentLength;
                bestLateral = errorX * rightX + errorZ * rightZ;
            }
        }
        if (_routePlanConnectors.Count > 0 && bestDistanceSquared > 25 * 25)
        {
            return;
        }
        _routeDistanceMeters = Math.Clamp(bestRouteDistance, 0, RouteLengthMeters);
        _lateralOffsetMeters = bestLateral;
    }

    private void UpdateCurrentLane()
    {
        var edge = _package.Graph.GetEdge(_currentEdgeId);
        var activeLanes = LaneGeometryProfile.Evaluate(edge, CurrentEdgeDistanceMeters).Lanes
            .Where(candidate => candidate.WidthMeters > 0.5)
            .ToArray();
        var geometryLane = (_routePlanConnectors.Count > 0
                ? activeLanes.SingleOrDefault(candidate => string.Equals(
                    candidate.Id,
                    CurrentStableLaneId,
                    StringComparison.Ordinal))
                : null)
            ?? activeLanes.MinBy(candidate => Math.Abs(
                candidate.CenterMeters - _lateralOffsetMeters))
            ?? throw new InvalidDataException(
                $"Route edge '{edge.Id}' has no active lane at " +
                $"{CurrentEdgeDistanceMeters:F3} meters.");
        var lane = edge.GetLaneSection(CurrentEdgeDistanceMeters).Lanes.Single(candidate =>
            candidate.Id == geometryLane.Id);
        CurrentLaneIndex = lane.Index;
        CurrentStableLaneId = lane.Id;
    }

    private (RouteWorldPoint Point, Vector3 Forward) GetRoadPose(double distanceMeters)
    {
        if (TryGetRoadPose(distanceMeters, out var pose))
        {
            return pose;
        }

        var fallback = _content.Values
            .Where(value => _routePlanEdgeIds.Contains(value.EdgeId))
            .OrderBy(value => Math.Abs(
                _routePlan.GetEdge(value.EdgeId).StartMeters + value.EndMeters - distanceMeters))
            .First();
        var last = fallback.Samples[^1];
        var point = _frame.ToWorld(last);
        return (point, _frame.DirectionToWorld(last.ProjectedTangentX, last.ProjectedTangentY));
    }

    private bool TryGetRoadPose(
        double distanceMeters,
        out (RouteWorldPoint Point, Vector3 Forward) pose)
    {
        foreach (var chunk in _content.Values
                     .Where(value => _routePlanEdgeIds.Contains(value.EdgeId))
                     .OrderBy(value =>
                         _routePlan.GetEdge(value.EdgeId).StartMeters + value.StartMeters))
        {
            var edgeOffset = _routePlan.GetEdge(chunk.EdgeId).StartMeters;
            var localDistance = distanceMeters - edgeOffset;
            if (localDistance < chunk.StartMeters || localDistance > chunk.EndMeters)
            {
                continue;
            }
            for (var index = 0; index < chunk.Samples.Count - 1; index++)
            {
                var firstSample = chunk.Samples[index];
                var secondSample = chunk.Samples[index + 1];
                if (localDistance < firstSample.DistanceMeters ||
                    localDistance > secondSample.DistanceMeters)
                {
                    continue;
                }
                var span = secondSample.DistanceMeters - firstSample.DistanceMeters;
                var factor = span <= 0 ? 0 : (localDistance - firstSample.DistanceMeters) / span;
                var first = _frame.ToWorld(firstSample);
                var second = _frame.ToWorld(secondSample);
                var tangentX = firstSample.ProjectedTangentX +
                    (secondSample.ProjectedTangentX - firstSample.ProjectedTangentX) * factor;
                var tangentY = firstSample.ProjectedTangentY +
                    (secondSample.ProjectedTangentY - firstSample.ProjectedTangentY) * factor;
                pose = (first.Lerp(second, factor), _frame.DirectionToWorld(tangentX, tangentY));
                return true;
            }
        }

        pose = default;
        return false;
    }

    private void TryPlaceVehicleForReview()
    {
        if (_reviewTargetReady || _vehicle is null ||
            !TryGetRoadPose(_routeDistanceMeters, out var pose))
        {
            return;
        }
        var roadPoint = OffsetForActiveLane(pose.Point, pose.Forward, _routeDistanceMeters);
        var localPoint = roadPoint.RelativeTo(_localOriginWorld);
        var horizontal = new Vector3(localPoint.X, 0, localPoint.Z);
        if (horizontal.Length() >= RebaseThresholdMeters)
        {
            Rebase(horizontal);
            localPoint = roadPoint.RelativeTo(_localOriginWorld);
        }
        MaximumLocalCoordinateMeters = Math.Max(
            MaximumLocalCoordinateMeters,
            Math.Sqrt(localPoint.X * localPoint.X + localPoint.Z * localPoint.Z));
        _vehicle.PlaceForReview(localPoint, pose.Forward);
        _vehicle.RouteDistanceMeters = _routeDistanceMeters;
        _vehicle.TargetRoadPoint = localPoint;
        _vehicle.TargetRoadForward = pose.Forward;
        _reviewEdgesVisited.Add(_currentEdgeId);
        _reviewTargetReady = true;
    }

    private void Rebase(Vector3 horizontal)
    {
        _localOriginWorld = _localOriginWorld.Add(horizontal);
        LocalOriginMeters = _routeDistanceMeters;
        RebaseCount++;
        if (_vehicle is not null)
        {
            _vehicle.Position -= horizontal;
            _vehicle.TargetRoadPoint -= horizontal;
        }
        foreach (var chunk in _loaded.Values)
        {
            chunk.ShiftForOriginRebase(horizontal);
        }
        foreach (var seam in _junctionSeams.Values)
        {
            seam.ShiftForOriginRebase(horizontal);
        }
    }

    private RouteWorldPoint OffsetForActiveLane(
        RouteWorldPoint point,
        Vector3 forward,
        double routeDistanceMeters)
    {
        var planEdge = _routePlan.GetEdgeAtDistance(routeDistanceMeters);
        var edge = _package.Graph.GetEdge(planEdge.EdgeId);
        var edgeDistance = Math.Clamp(
            routeDistanceMeters - planEdge.StartMeters,
            0,
            edge.LengthMeters);
        var layout = LaneGeometryProfile.Evaluate(edge, edgeDistance);
        var lane = layout.Lanes.SingleOrDefault(candidate =>
                string.Equals(candidate.Id, CurrentStableLaneId, StringComparison.Ordinal) &&
                candidate.WidthMeters > 0.5)
            ?? layout.Lanes
                .Where(candidate => candidate.WidthMeters > 0.5)
                .MinBy(candidate => Math.Abs(candidate.CenterMeters - _lateralOffsetMeters))
            ?? throw new InvalidDataException(
                $"Route edge '{edge.Id}' has no active lane at {edgeDistance:F3} meters.");
        var right = forward.Cross(Vector3.Up).Normalized();
        return point.Add(right * (float)lane.CenterMeters);
    }

    private void UpdateCurrentEdge()
    {
        _currentEdgeId = _routePlan.GetEdgeAtDistance(_routeDistanceMeters).EdgeId;
    }

    private IReadOnlyDictionary<(string FromEdgeId, string ToEdgeId), JunctionConnector>
        BuildRoutePlanConnectors(IReadOnlyList<string>? connectorIds)
    {
        if (connectorIds is null)
        {
            return new Dictionary<(string FromEdgeId, string ToEdgeId), JunctionConnector>();
        }
        if (connectorIds.Count != _routePlan.Edges.Count - 1)
        {
            throw new InvalidDataException(
                "Explicit route plan needs exactly one connector per edge transition.");
        }
        var semantics = _package.Semantics
            ?? throw new InvalidDataException("Explicit route plan requires route semantics.");
        var connectorsById = semantics.JunctionConnectors.ToDictionary(
            connector => connector.Id,
            StringComparer.Ordinal);
        var result = new Dictionary<(string FromEdgeId, string ToEdgeId), JunctionConnector>();
        for (var index = 0; index < connectorIds.Count; index++)
        {
            if (!connectorsById.TryGetValue(connectorIds[index], out var connector))
            {
                throw new InvalidDataException(
                    $"Explicit route plan references unknown connector '{connectorIds[index]}'.");
            }
            var fromEdgeId = _routePlan.Edges[index].EdgeId;
            var toEdgeId = _routePlan.Edges[index + 1].EdgeId;
            if (connector.FromEdgeId != fromEdgeId || connector.ToEdgeId != toEdgeId)
            {
                throw new InvalidDataException(
                    $"Connector '{connector.Id}' does not match route transition " +
                    $"'{fromEdgeId}' to '{toEdgeId}'.");
            }
            result.Add((fromEdgeId, toEdgeId), connector);
        }
        return result;
    }

    private void UpdateLaneAcrossRouteEdges(string previousEdgeId, string previousLaneId)
    {
        var previousIndex = FindRoutePlanEdgeIndex(previousEdgeId);
        var currentIndex = FindRoutePlanEdgeIndex(_currentEdgeId);
        if (currentIndex <= previousIndex)
        {
            UpdateCurrentLane();
            return;
        }
        var laneId = previousLaneId;
        for (var index = previousIndex; index < currentIndex; index++)
        {
            var fromEdgeId = _routePlan.Edges[index].EdgeId;
            var toEdgeId = _routePlan.Edges[index + 1].EdgeId;
            JunctionConnector? connector = null;
            if (_routePlanConnectors.TryGetValue((fromEdgeId, toEdgeId), out var planned))
            {
                connector = planned;
            }
            else
            {
                var candidates = _package.Semantics?.JunctionConnectors.Where(candidate =>
                    candidate.FromEdgeId == fromEdgeId &&
                    candidate.FromLaneId == laneId &&
                    candidate.ToEdgeId == toEdgeId).ToArray() ?? [];
                connector = candidates.Length == 0 ? null : candidates[0];
            }
            if (connector is null)
            {
                UpdateCurrentLane();
                return;
            }
            if (!string.Equals(connector.FromLaneId, laneId, StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"Route connector '{connector.Id}' expected lane '{connector.FromLaneId}' " +
                    $"but traversal reached it on '{laneId}'.");
            }
            laneId = connector.ToLaneId;
            ActiveConnectorId = connector.Id;
            _observedConnectorIds.Add(connector.Id);
            _observedConnectorMovements.Add(connector.Movement);
            GD.Print(
                $"CANNONBALL_CONNECTOR_OK movement={connector.Movement} " +
                $"from_edge={fromEdgeId} to_edge={toEdgeId} " +
                $"from_lane={connector.FromLaneId} to_lane={connector.ToLaneId}");
        }
        var edge = _package.Graph.GetEdge(_currentEdgeId);
        var lane = edge.GetLaneSection(CurrentEdgeDistanceMeters).Lanes.Single(candidate =>
            candidate.Id == laneId);
        CurrentLaneIndex = lane.Index;
        CurrentStableLaneId = lane.Id;
    }

    private int FindRoutePlanEdgeIndex(string edgeId)
    {
        for (var index = 0; index < _routePlan.Edges.Count; index++)
        {
            if (string.Equals(_routePlan.Edges[index].EdgeId, edgeId, StringComparison.Ordinal))
            {
                return index;
            }
        }
        throw new InvalidDataException($"Route plan does not contain edge '{edgeId}'.");
    }

    private sealed record RouteManifestSpan(
        ChunkManifest Manifest,
        double StartMeters,
        double EndMeters);

    private sealed record PendingRead(
        Task<RouteChunkContent> Task,
        CancellationTokenSource Cancellation);
}
