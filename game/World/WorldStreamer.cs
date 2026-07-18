using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Game.Vehicle;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class WorldStreamer : Node3D
{
    public const double VisualLookAheadMeters = 10_000;
    public const double ActivePhysicsAheadMeters = 2_000;
    public const double RetainBehindMeters = 500;
    public const double PrefetchHorizonSeconds = 112;
    public const float RebaseThresholdMeters = 1_000;
    public const double ChunkBuildBudgetMilliseconds = 40;
    public const double InitialChunkBuildBudgetMilliseconds = 50;
    public const int MaximumConcurrentChunkReads = 2;
    public const double ShortCorridorLoopResetLeadMeters = 25;

    private readonly Dictionary<string, RoadChunk> _loaded = new(StringComparer.Ordinal);
    private readonly Dictionary<string, RouteChunkContent> _content = new(StringComparer.Ordinal);
    private readonly Dictionary<string, PendingRead> _pending = new(StringComparer.Ordinal);
    private readonly Queue<string> _loadQueue = [];
    private readonly HashSet<string> _queued = new(StringComparer.Ordinal);
    private readonly HashSet<string> _failed = new(StringComparer.Ordinal);
    private RouteContentPackage _package = null!;
    private VerifiedFileChunkSource _source = null!;
    private LinearRoutePlan _routePlan = null!;
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

    public double RouteDistanceMeters => _routeDistanceMeters;
    public double LocalOriginMeters { get; private set; }
    public double CurrentLookAheadMeters { get; private set; } = ActivePhysicsAheadMeters;
    public int LoadedChunkCount => _loaded.Count;
    public int ExpectedChunkCount => _manifests.Count;
    public int ReviewReadyChunkCount => _loaded.Values.Count(chunk => chunk.HasReviewGeometry());
    public int RebaseCount { get; private set; }
    public int ChunkFailureCount { get; private set; }
    public double MaximumBuildMilliseconds { get; private set; }
    public string CurrentEdgeId => _currentEdgeId;
    public double CurrentEdgeDistanceMeters =>
        _routeDistanceMeters - _routePlan.GetEdge(_currentEdgeId).StartMeters;
    public double CurrentLateralOffsetMeters => _lateralOffsetMeters;
    public int CurrentLaneIndex { get; private set; }
    public string CurrentStableLaneId { get; private set; } = string.Empty;
    public string ContentVersion => _package.Graph.ContentVersion;
    public double TotalRouteLengthMeters => RouteLengthMeters;
    public IReadOnlyList<string> RoutePlan => _routePlan.EdgeIds;
    public Vector3 InitialRoadPoint { get; private set; }
    public Vector3 InitialRoadForward { get; private set; }
    public bool ShortCorridorLoopEnabled { get; set; }
    public int CompletedShortCorridorLoops { get; private set; }
    public int CrossedReviewDistanceThresholdCount { get; private set; }
    public bool ReviewTargetReady => _reviewTargetReady;
    public int ReviewReadyChunkCountSeen => _reviewReadyChunksSeen.Count;
    public int ReviewEdgeCountVisited => _reviewEdgesVisited.Count;

    public static ChunkManifest FindInitialManifest(RouteContentPackage package)
    {
        ArgumentNullException.ThrowIfNull(package);
        var plan = LinearRoutePlan.Build(
            package.Graph,
            package.Chunks.Values.Select(manifest => manifest.EdgeId));
        var firstEdgeId = plan.Edges[0].EdgeId;
        return package.Chunks.Values
            .Where(manifest => string.Equals(manifest.EdgeId, firstEdgeId, StringComparison.Ordinal))
            .OrderBy(manifest => manifest.StartMeters)
            .ThenBy(manifest => manifest.Id, StringComparer.Ordinal)
            .FirstOrDefault()
            ?? throw new InvalidDataException($"Route edge '{firstEdgeId}' has no chunk manifests.");
    }

    public void Configure(
        RouteContentPackage package,
        VerifiedFileChunkSource source,
        RouteChunkContent initialChunk)
    {
        if (IsInsideTree())
        {
            throw new InvalidOperationException("WorldStreamer must be configured before entering the scene tree.");
        }
        _package = package;
        _source = source;
        _routePlan = LinearRoutePlan.Build(
            package.Graph,
            package.Chunks.Values.Select(manifest => manifest.EdgeId));
        if (!string.Equals(initialChunk.EdgeId, _routePlan.Edges[0].EdgeId, StringComparison.Ordinal) ||
            initialChunk.StartMeters != 0)
        {
            throw new InvalidDataException("The initial route chunk is not the first chunk in the corridor plan.");
        }
        _currentEdgeId = initialChunk.EdgeId;
        UpdateCurrentLane();
        _manifests = package.Chunks.Values
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
        AttachChunk(initialChunk, InitialChunkBuildBudgetMilliseconds);
    }

    public override void _Ready()
    {
        if (_manifests.Count == 0)
        {
            throw new InvalidOperationException("WorldStreamer was not configured with a route package.");
        }
        RefreshDesiredChunks();
    }

    public override void _Process(double delta)
    {
        _ = delta;
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

        UpdateRouteProjection();
        UpdateCurrentEdge();
        UpdateCurrentLane();
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
        var target = GetRoadPose(Math.Min(RouteLengthMeters, _routeDistanceMeters + 20));
        _vehicle.RouteDistanceMeters = _routeDistanceMeters;
        _vehicle.TargetRoadPoint = target.Point.RelativeTo(_localOriginWorld);
        _vehicle.TargetRoadForward = target.Forward;

        var horizontal = new Vector3(_vehicle.Position.X, 0, _vehicle.Position.Z);
        if (horizontal.Length() < RebaseThresholdMeters)
        {
            return;
        }

        _localOriginWorld = _localOriginWorld.Add(horizontal);
        LocalOriginMeters = _routeDistanceMeters;
        RebaseCount++;
        _vehicle.Position -= horizontal;
        _vehicle.TargetRoadPoint -= horizontal;
        foreach (var chunk in _loaded.Values)
        {
            chunk.ShiftForOriginRebase(horizontal);
        }
    }

    public void Track(CannonballVehicle vehicle)
    {
        _vehicle = vehicle;
        vehicle.RouteDistanceMeters = _routeDistanceMeters;
        vehicle.TargetRoadPoint = InitialRoadPoint;
        vehicle.TargetRoadForward = InitialRoadForward;
    }

    public void SetReviewDistance(double distanceMeters)
    {
        _reviewTargetDistanceMeters = Math.Clamp(distanceMeters, 0, RouteLengthMeters);
        _routeDistanceMeters = _reviewTargetDistanceMeters.Value;
        _reviewTargetReady = false;
        UpdateCurrentEdge();
        RefreshDesiredChunks();
    }

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

        var desired = _manifests
            .Where(span => span.EndMeters >= first && span.StartMeters <= last)
            .Select(span => span.Manifest.Id)
            .ToHashSet(StringComparer.Ordinal);
        foreach (var (id, pending) in _pending.ToArray())
        {
            if (!desired.Contains(id))
            {
                pending.Cancellation.Cancel();
            }
        }
        foreach (var span in _manifests.Where(span => desired.Contains(span.Manifest.Id)))
        {
            var manifest = span.Manifest;
            if (!_loaded.ContainsKey(manifest.Id) &&
                !_pending.ContainsKey(manifest.Id) &&
                !_queued.Contains(manifest.Id) &&
                !_failed.Contains(manifest.Id))
            {
                _queued.Add(manifest.Id);
                _loadQueue.Enqueue(manifest.Id);
            }
        }
        StartPendingReads(desired);

        foreach (var (id, chunk) in _loaded.ToArray())
        {
            var manifest = _manifests.First(span => span.Manifest.Id == id);
            chunk.SetCollisionActive(
                manifest.EndMeters >= _routeDistanceMeters - 50 &&
                manifest.StartMeters <= _routeDistanceMeters + ActivePhysicsAheadMeters);
            if (manifest.EndMeters < first || manifest.StartMeters > last + ActivePhysicsAheadMeters)
            {
                _loaded.Remove(id);
                _content.Remove(id);
                chunk.QueueFree();
            }
        }
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
        var chunk = RoadChunk.Create(content, _frame, _localOriginWorld);
        if (chunk.BuildMilliseconds > buildBudgetMilliseconds)
        {
            chunk.Free();
            throw new InvalidOperationException(
                $"Route chunk '{content.Id}' took {chunk.BuildMilliseconds:0.000} ms to build; " +
                $"budget is {buildBudgetMilliseconds:0.000} ms.");
        }
        _content.Add(content.Id, content);
        _loaded.Add(content.Id, chunk);
        if (chunk.HasReviewGeometry())
        {
            _reviewReadyChunksSeen.Add(content.Id);
        }
        MaximumBuildMilliseconds = Math.Max(MaximumBuildMilliseconds, chunk.BuildMilliseconds);
        AddChild(chunk);
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
        var vehicleX = _localOriginWorld.X + _vehicle.Position.X;
        var vehicleZ = _localOriginWorld.Z + _vehicle.Position.Z;
        var bestDistanceSquared = double.PositiveInfinity;
        var bestRouteDistance = _routeDistanceMeters;
        var bestLateral = _lateralOffsetMeters;
        foreach (var chunk in _content.Values)
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
        _routeDistanceMeters = Math.Clamp(bestRouteDistance, 0, RouteLengthMeters);
        _lateralOffsetMeters = bestLateral;
    }

    private void UpdateCurrentLane()
    {
        var edge = _package.Graph.GetEdge(_currentEdgeId);
        var lane = edge.GetLaneSection(CurrentEdgeDistanceMeters)
            .GetClosestLane(_lateralOffsetMeters);
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
        foreach (var chunk in _content.Values.OrderBy(value =>
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
        var localPoint = pose.Point.RelativeTo(_localOriginWorld);
        _vehicle.PlaceForReview(localPoint, pose.Forward);
        _vehicle.RouteDistanceMeters = _routeDistanceMeters;
        _vehicle.TargetRoadPoint = localPoint;
        _vehicle.TargetRoadForward = pose.Forward;
        _reviewEdgesVisited.Add(_currentEdgeId);
        _reviewTargetReady = true;
    }

    private void UpdateCurrentEdge()
    {
        _currentEdgeId = _routePlan.GetEdgeAtDistance(_routeDistanceMeters).EdgeId;
    }

    private sealed record RouteManifestSpan(
        ChunkManifest Manifest,
        double StartMeters,
        double EndMeters);

    private sealed record PendingRead(
        Task<RouteChunkContent> Task,
        CancellationTokenSource Cancellation);
}
