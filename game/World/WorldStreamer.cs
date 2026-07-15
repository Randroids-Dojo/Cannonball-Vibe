using Cannonball.Game.Vehicle;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class WorldStreamer : Node3D
{
    public const double ChunkLengthMeters = 2_000;
    public const double VisualLookAheadMeters = 10_000;
    public const double ActivePhysicsAheadMeters = 2_000;
    public const double RetainBehindMeters = 500;
    public const double PrefetchHorizonSeconds = 112;
    public const float RebaseThresholdMeters = 1_000;

    private readonly Dictionary<int, RoadChunk> _loaded = [];
    private readonly Queue<int> _loadQueue = [];
    private readonly HashSet<int> _queued = [];
    private CannonballVehicle? _vehicle;
    private double _localOriginMeters;

    public double RouteDistanceMeters => _vehicle is null
        ? _localOriginMeters
        : Math.Clamp(_localOriginMeters - _vehicle.Position.Z, 0, RoadMath.RouteLengthMeters);

    public double LocalOriginMeters => _localOriginMeters;
    public double CurrentLookAheadMeters { get; private set; } = ActivePhysicsAheadMeters;
    public int LoadedChunkCount => _loaded.Count;
    public int RebaseCount { get; private set; }

    public override void _Ready()
    {
        LoadChunk(0);
        RefreshDesiredChunks();
    }

    public override void _Process(double delta)
    {
        _ = delta;
        RefreshDesiredChunks();
        if (_loadQueue.TryDequeue(out var chunkIndex))
        {
            _queued.Remove(chunkIndex);
            LoadChunk(chunkIndex);
        }
    }

    public override void _PhysicsProcess(double delta)
    {
        _ = delta;
        if (_vehicle is null)
        {
            return;
        }

        _vehicle.RouteDistanceMeters = RouteDistanceMeters;
        _vehicle.TargetRoadCenterX = RoadMath.CenterX(RouteDistanceMeters);
        if (_vehicle.Position.Z > -RebaseThresholdMeters)
        {
            return;
        }

        _localOriginMeters += RebaseThresholdMeters;
        RebaseCount++;
        _vehicle.Position += Vector3.Back * RebaseThresholdMeters;
        foreach (var chunk in _loaded.Values)
        {
            chunk.ShiftForOriginRebase(RebaseThresholdMeters);
        }
    }

    public void Track(CannonballVehicle vehicle)
    {
        _vehicle = vehicle;
        vehicle.RouteDistanceMeters = RouteDistanceMeters;
    }

    private void RefreshDesiredChunks()
    {
        var routeDistance = RouteDistanceMeters;
        var speed = _vehicle?.SpeedMetersPerSecond ?? 0;
        CurrentLookAheadMeters = Math.Clamp(
            speed * PrefetchHorizonSeconds,
            ActivePhysicsAheadMeters,
            VisualLookAheadMeters);
        var first = Math.Max(0, (int)Math.Floor((routeDistance - RetainBehindMeters) / ChunkLengthMeters));
        var last = Math.Min(
            (int)Math.Ceiling(RoadMath.RouteLengthMeters / ChunkLengthMeters) - 1,
            (int)Math.Floor((routeDistance + CurrentLookAheadMeters) / ChunkLengthMeters));

        for (var index = first; index <= last; index++)
        {
            if (!_loaded.ContainsKey(index) && _queued.Add(index))
            {
                _loadQueue.Enqueue(index);
            }
        }

        foreach (var index in _loaded.Keys.Where(index => index < first || index > last + 1).ToArray())
        {
            _loaded.Remove(index, out var chunk);
            chunk?.QueueFree();
        }
    }

    private void LoadChunk(int chunkIndex)
    {
        if (_loaded.ContainsKey(chunkIndex))
        {
            return;
        }

        var chunk = RoadChunk.Create(chunkIndex, ChunkLengthMeters, _localOriginMeters);
        _loaded.Add(chunkIndex, chunk);
        AddChild(chunk);
    }
}
