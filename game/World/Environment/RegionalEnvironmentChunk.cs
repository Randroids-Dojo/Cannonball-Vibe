using System.Buffers.Binary;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using Cannonball.Core.Content;
using Godot;

namespace Cannonball.Game.World.Environments;

public sealed partial class RegionalEnvironmentChunk : Node3D
{
    /// <summary>Near-layer instances are grouped into cells of this route length so LOD and visibility ranges switch per cell rather than per chunk.</summary>
    public const float NearCellLengthMeters = 150;
    private const float TreeLodFadeMarginMeters = 30;
    private static readonly StringName TreeLodInverse = "tree_lod_inverse";
    private bool _treeLodFadeSupported;

    private ArrayMesh? _ownedTerrainMesh;

    private RegionalEnvironmentChunk()
    {
    }

    public string ChunkId { get; private set; } = string.Empty;
    public EnvironmentRegion Region { get; private set; }
    public int NearInstanceCount { get; private set; }
    public int MidInstanceCount { get; private set; }
    public int DistantInstanceCount { get; private set; }
    public int SemanticNodeCount { get; private set; }
    public int TerrainVertexCount { get; private set; }
    public int TerrainTriangleCount { get; private set; }
    public double BuildMilliseconds { get; private set; }
    private IReadOnlyList<Vector3> _terrainStartOuterEdge = [];
    private IReadOnlyList<Vector3> _terrainEndOuterEdge = [];
    private double _routeStartMeters;
    private double _routeEndMeters;
    private double _routeLengthMeters;

    public static RegionalEnvironmentChunk Create(
        RouteChunkContent content,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld,
        EnvironmentVisualKit kit,
        EnvironmentRegion region,
        string stableSeed,
        double routeStartMeters,
        double routeLengthMeters)
    {
        ArgumentNullException.ThrowIfNull(content);
        ArgumentNullException.ThrowIfNull(frame);
        ArgumentNullException.ThrowIfNull(kit);
        // Regional environment build cost, charged on the frame that builds it.
        // This nests inside the streamer's road region, since WorldStreamer._Process
        // reaches here through CompletePendingLoads and AttachChunk. Regions measure
        // exclusive time, so the road region is suspended for the duration and the
        // milliseconds are not counted twice.
        using var region_ = Cannonball.Core.Performance.SubsystemProfiler.Measure(
            Cannonball.Core.Performance.SubsystemProfiler.Subsystem.Environment);
        ArgumentException.ThrowIfNullOrWhiteSpace(stableSeed);
        if (content.Samples.Count < 2)
        {
            throw new InvalidDataException(
                $"Environment chunk '{content.Id}' requires at least two route samples.");
        }

        var started = Stopwatch.GetTimestamp();
        var anchor = frame.ToWorld(content.Samples[0]);
        var chunk = new RegionalEnvironmentChunk
        {
            Name = $"Environment_{content.Id}",
            ChunkId = content.Id,
            Region = region,
            _treeLodFadeSupported = RenderingServer.GetCurrentRenderingMethod() == "forward_plus",
            Position = anchor.RelativeTo(localOriginWorld),
            _routeStartMeters = routeStartMeters,
            _routeEndMeters = routeStartMeters + content.EndMeters - content.StartMeters,
            _routeLengthMeters = routeLengthMeters,
        };
        EnvironmentVisualKit.MarkSemantic(
            chunk,
            $"environment.chunk.{content.Id}",
            "chunk-root");

        var random = new StableRandom(Seed(stableSeed, content.Id, region));
        var samplePoints = content.Samples
            .Select(sample => frame.ToWorld(sample).RelativeTo(anchor))
            .ToArray();
        chunk.BuildTerrain(
            content,
            frame,
            anchor,
            kit,
            routeStartMeters,
            routeLengthMeters);
        chunk.BuildNearLayer(kit, samplePoints, ref random);
        chunk.BuildMidLayer(kit, samplePoints, ref random);
        chunk.BuildDistantLayer(kit, samplePoints, ref random);
        chunk.BuildMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        return chunk;
    }

    public EnvironmentChunkSnapshot CaptureSnapshot() => new(
        ChunkId,
        Region,
        NearInstanceCount,
        MidInstanceCount,
        DistantInstanceCount,
        SemanticNodeCount,
        TerrainVertexCount,
        TerrainTriangleCount,
        BuildMilliseconds,
        !ContainsCollisionObject(this));

    public IReadOnlyList<Vector3> GetTerrainStartOuterEdge() =>
        _terrainStartOuterEdge.Select(point => Position + point).ToArray();

    public IReadOnlyList<Vector3> GetTerrainEndOuterEdge() =>
        _terrainEndOuterEdge.Select(point => Position + point).ToArray();

    private void BuildTerrain(
        RouteChunkContent content,
        RouteFrame frame,
        RouteWorldPoint anchor,
        EnvironmentVisualKit kit,
        double routeStartMeters,
        double routeLengthMeters)
    {
        var result = RegionalTerrainRibbon.Build(
            content,
            frame,
            anchor,
            kit,
            routeStartMeters,
            routeLengthMeters);
        // Build hands over a freshly committed mesh; the instance takes its own
        // reference on assignment, so this wrapper is released with the chunk
        // rather than surviving to finalisation after engine shutdown.
        _ownedTerrainMesh = result.Mesh;
        var terrain = new MeshInstance3D
        {
            Name = "RegionalTerrainRibbon",
            Mesh = result.Mesh,
            VisibilityRangeEnd = RegionalTerrainRibbon.VisibilityMeters,
            VisibilityRangeFadeMode = GeometryInstance3D.VisibilityRangeFadeModeEnum.Self,
            CastShadow = GeometryInstance3D.ShadowCastingSetting.Off,
        };
        EnvironmentVisualKit.MarkSemantic(
            terrain,
            $"environment.chunk.{ChunkId}.terrain",
            "terrain");
        AddChild(terrain);
        TerrainVertexCount = result.VertexCount;
        TerrainTriangleCount = result.TriangleCount;
        _terrainStartOuterEdge = result.StartOuterEdge;
        _terrainEndOuterEdge = result.EndOuterEdge;
        SemanticNodeCount++;
    }

    private static bool ContainsCollisionObject(Node node)
    {
        foreach (var child in node.GetChildren())
        {
            if (child is CollisionObject3D || ContainsCollisionObject(child))
            {
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// Trees and rocks from the road margin out to the middle terrain band,
    /// grouped in route cells with three LOD multimeshes each. Density and
    /// lateral placement follow the region: dense conifer stands in the
    /// mountains, thinning through the foothills, scattered on the plains.
    /// </summary>
    private void BuildNearLayer(
        EnvironmentVisualKit kit,
        IReadOnlyList<Vector3> samples,
        ref StableRandom random)
    {
        var (treeFactor, rockFactor, minimumLateral, maximumLateral) = Region switch
        {
            EnvironmentRegion.Mountain => (1.0f, 0.7f, 26f, 250f),
            EnvironmentRegion.Foothill => (0.55f, 0.5f, 34f, 250f),
            EnvironmentRegion.Plains => (0.07f, 0.3f, 60f, 250f),
            EnvironmentRegion.UrbanEdge => (0.14f, 0.35f, 45f, 220f),
            _ => throw new ArgumentOutOfRangeException(nameof(Region)),
        };
        var total = 0;
        var cellIndex = 0;
        foreach (var cell in Cells(samples, NearCellLengthMeters))
        {
            var treeCount = Math.Max(
                Region == EnvironmentRegion.Mountain ? 2 : 0,
                (int)Math.Round(kit.NearTreesPerHundredMeters * treeFactor * cell.LengthMeters / 100 * 2));
            var rockCount = (int)Math.Round(kit.NearRocksPerHundredMeters * rockFactor * cell.LengthMeters / 100 * 2);
            if (cellIndex == 0)
            {
                // Every chunk keeps at least one tree and one rock so the near
                // layer is never empty, which the streaming contract requires.
                treeCount = Math.Max(treeCount, 1);
                rockCount = Math.Max(rockCount, 1);
            }
            var trees = new List<Transform3D>(treeCount);
            for (var index = 0; index < treeCount; index++)
            {
                var placement = Place(cell, samples, minimumLateral, maximumLateral, ref random);
                var height = 9.5f + random.NextFloat() * 10.5f;
                var basis = Basis.FromEuler(new Vector3(0, random.NextFloat() * Mathf.Tau, 0))
                    .Scaled(new Vector3(height, height, height));
                trees.Add(new Transform3D(basis, placement));
            }
            var rocks = new List<Transform3D>(rockCount);
            for (var index = 0; index < rockCount; index++)
            {
                var placement = Place(cell, samples, minimumLateral * 0.8f, 130f, ref random);
                var size = 0.6f + random.NextFloat() * 2.4f;
                var basis = Basis.FromEuler(new Vector3(
                        (random.NextFloat() - 0.5f) * 0.3f,
                        random.NextFloat() * Mathf.Tau,
                        (random.NextFloat() - 0.5f) * 0.3f))
                    .Scaled(new Vector3(size * (0.8f + random.NextFloat() * 0.5f), size * 0.8f, size));
                placement.Y -= size * 0.12f;
                rocks.Add(new Transform3D(basis, placement));
            }
            if (trees.Count > 0)
            {
                // Visibility distance uses the instance AABB center. Different
                // authored LOD silhouettes must share that center, or one can
                // disappear before its replacement reaches the fade band.
                var meshBounds = kit.ConiferLod0.GetAabb()
                    .Merge(kit.ConiferLod1.GetAabb()).Merge(kit.ConiferLod2.GetAabb());
                var bounds = trees[0] * meshBounds;
                for (var treeIndex = 1; treeIndex < trees.Count; treeIndex++)
                {
                    bounds = bounds.Merge(trees[treeIndex] * meshBounds);
                }
                AddMultiMesh($"Near{cellIndex}Lod0", $"near.{cellIndex}.lod0", kit.ConiferLod0, trees,
                    0, kit.NearLod0Meters, GeometryInstance3D.ShadowCastingSetting.On, "near",
                    treeLodBounds: bounds);
                AddMultiMesh($"Near{cellIndex}Lod1", $"near.{cellIndex}.lod1", kit.ConiferLod1, trees,
                    kit.NearLod0Meters, kit.NearLod1Meters, GeometryInstance3D.ShadowCastingSetting.On, "near",
                    treeLodBounds: bounds, inverseLodDither: true);
                AddMultiMesh($"Near{cellIndex}Lod2", $"near.{cellIndex}.lod2", kit.ConiferLod2, trees,
                    kit.NearLod1Meters, kit.NearLod2Meters, GeometryInstance3D.ShadowCastingSetting.Off, "near",
                    treeLodBounds: bounds);
            }
            if (rocks.Count > 0)
            {
                AddMultiMesh($"Near{cellIndex}Rocks", $"near.{cellIndex}.rocks", kit.RockMesh, rocks,
                    0, kit.NearLod1Meters, GeometryInstance3D.ShadowCastingSetting.On, "near");
            }
            total += trees.Count + rocks.Count;
            cellIndex++;
        }
        NearInstanceCount = total;
    }

    private void BuildMidLayer(
        EnvironmentVisualKit kit,
        IReadOnlyList<Vector3> samples,
        ref StableRandom random)
    {
        var urban = Region == EnvironmentRegion.UrbanEdge;
        var count = kit.MidInstanceBudget;
        var transforms = new List<Transform3D>(count);
        var colors = new List<Color>(count);
        for (var index = 0; index < count; index++)
        {
            var lateral = Mathf.Lerp(320, 850, random.NextFloat());
            var placement = PlaceAtLateral(samples, random.NextFloat(), lateral * (random.NextFloat() < 0.5f ? -1 : 1), out _);
            if (urban)
            {
                var footprint = Mathf.Lerp(22, 70, random.NextFloat());
                var height = footprint * Mathf.Lerp(0.55f, 1.35f, random.NextFloat());
                placement.Y += height * 0.5f - 0.5f;
                transforms.Add(new Transform3D(
                    Basis.FromEuler(new Vector3(0, random.NextFloat() * Mathf.Tau, 0))
                        .Scaled(new Vector3(footprint, height, footprint)),
                    placement));
                colors.Add(BuildingTint(ref random));
                continue;
            }
            var hillFootprint = Region == EnvironmentRegion.Plains
                ? Mathf.Lerp(30, 70, random.NextFloat())
                : Mathf.Lerp(65, 150, random.NextFloat());
            var hillHeight = hillFootprint * Mathf.Lerp(0.16f, 0.36f, random.NextFloat());
            placement.Y -= hillHeight * 0.05f;
            transforms.Add(new Transform3D(
                Basis.FromEuler(new Vector3(0, random.NextFloat() * Mathf.Tau, 0))
                    .Scaled(new Vector3(hillFootprint, hillHeight, hillFootprint)),
                placement));
        }
        if (urban)
        {
            AddMultiMesh("MidInstances", "mid", kit.BuildingMesh, transforms, 0, 4_000,
                GeometryInstance3D.ShadowCastingSetting.On, "mid", colors);
        }
        else
        {
            var half = transforms.Count / 2;
            AddMultiMesh("MidInstances", "mid", kit.HillMesh(0), transforms.Take(half).ToList(), 0, 4_000,
                GeometryInstance3D.ShadowCastingSetting.On, "mid");
            AddMultiMesh("MidInstancesB", "mid.b", kit.HillMesh(1), transforms.Skip(half).ToList(), 0, 4_000,
                GeometryInstance3D.ShadowCastingSetting.On, "mid");
        }
        MidInstanceCount = count;
    }

    private void BuildDistantLayer(
        EnvironmentVisualKit kit,
        IReadOnlyList<Vector3> samples,
        ref StableRandom random)
    {
        var urban = Region == EnvironmentRegion.UrbanEdge;
        var count = kit.DistantInstanceBudget;
        var groups = new List<Transform3D>[3];
        for (var group = 0; group < groups.Length; group++)
        {
            groups[group] = [];
        }
        var colors = new List<Color>(count);
        for (var index = 0; index < count; index++)
        {
            var lateral = Mathf.Lerp(1_100, 2_600, random.NextFloat());
            var placement = PlaceAtLateral(samples, random.NextFloat(), lateral * (random.NextFloat() < 0.5f ? -1 : 1), out _);
            if (urban)
            {
                var footprint = Mathf.Lerp(55, 180, random.NextFloat());
                var height = footprint * Mathf.Lerp(0.55f, 1.35f, random.NextFloat());
                placement.Y += height * 0.5f - 0.5f;
                groups[0].Add(new Transform3D(
                    Basis.FromEuler(new Vector3(0, random.NextFloat() * Mathf.Tau, 0))
                        .Scaled(new Vector3(footprint, height, footprint)),
                    placement));
                colors.Add(BuildingTint(ref random));
                continue;
            }
            var massifFootprint = Region == EnvironmentRegion.Plains
                ? Mathf.Lerp(150, 340, random.NextFloat())
                : Mathf.Lerp(230, 520, random.NextFloat());
            var massifHeight = massifFootprint * (Region == EnvironmentRegion.Plains
                ? Mathf.Lerp(0.14f, 0.32f, random.NextFloat())
                : Mathf.Lerp(0.45f, 0.95f, random.NextFloat()));
            placement.Y -= massifHeight * 0.05f;
            groups[index % 3].Add(new Transform3D(
                Basis.FromEuler(new Vector3(0, random.NextFloat() * Mathf.Tau, 0))
                    .Scaled(new Vector3(massifFootprint, massifHeight, massifFootprint)),
                placement));
        }
        if (urban)
        {
            AddMultiMesh("DistantInstances", "distant", kit.BuildingMesh, groups[0], 0, 12_000,
                GeometryInstance3D.ShadowCastingSetting.Off, "distant", colors);
        }
        else
        {
            for (var group = 0; group < groups.Length; group++)
            {
                if (groups[group].Count == 0)
                {
                    continue;
                }
                var mesh = Region == EnvironmentRegion.Plains ? kit.HillMesh(group) : kit.MassifMesh(group);
                AddMultiMesh(
                    group == 0 ? "DistantInstances" : $"DistantInstances{group}",
                    group == 0 ? "distant" : $"distant.{group}",
                    mesh, groups[group], 0, 12_000,
                    GeometryInstance3D.ShadowCastingSetting.Off, "distant");
            }
        }
        DistantInstanceCount = count;
    }

    private static Color BuildingTint(ref StableRandom random)
    {
        var warmth = random.NextFloat();
        var value = 0.55f + random.NextFloat() * 0.35f;
        return new Color(
            value * (0.92f + warmth * 0.10f),
            value * (0.90f + warmth * 0.04f),
            value * (0.86f + (1 - warmth) * 0.12f));
    }

    private readonly record struct RouteCell(int StartIndex, int EndIndex, float LengthMeters, double RouteStartMeters, double RouteEndMeters);

    private IEnumerable<RouteCell> Cells(IReadOnlyList<Vector3> samples, float cellLength)
    {
        var lengths = new float[samples.Count];
        for (var index = 1; index < samples.Count; index++)
        {
            lengths[index] = lengths[index - 1] + samples[index].DistanceTo(samples[index - 1]);
        }
        var total = lengths[^1];
        if (total <= 0)
        {
            yield return new RouteCell(0, samples.Count - 1, 0, _routeStartMeters, _routeEndMeters);
            yield break;
        }
        var cells = Math.Max(1, (int)Math.Round(total / cellLength));
        var perCell = total / cells;
        var start = 0;
        for (var cell = 0; cell < cells; cell++)
        {
            var target = (cell + 1) * perCell;
            var end = start;
            while (end < samples.Count - 1 && lengths[end] < target)
            {
                end++;
            }
            if (cell == cells - 1)
            {
                end = samples.Count - 1;
            }
            if (end <= start)
            {
                end = Math.Min(samples.Count - 1, start + 1);
            }
            var fractionStart = lengths[start] / total;
            var fractionEnd = lengths[end] / total;
            yield return new RouteCell(
                start,
                end,
                lengths[end] - lengths[start],
                Mathf.Lerp((float)_routeStartMeters, (float)_routeEndMeters, fractionStart),
                Mathf.Lerp((float)_routeStartMeters, (float)_routeEndMeters, fractionEnd));
            start = end;
        }
    }

    private Vector3 Place(
        RouteCell cell,
        IReadOnlyList<Vector3> samples,
        float minimumLateral,
        float maximumLateral,
        ref StableRandom random)
    {
        var side = random.NextFloat() < 0.5f ? -1 : 1;
        // Bias toward the road so stands read as continuous cover rather than a
        // sparse band far from the driver.
        var t = random.NextFloat();
        var lateral = Mathf.Lerp(minimumLateral, maximumLateral, t * t) * side;
        var span = Math.Max(1, cell.EndIndex - cell.StartIndex);
        var progress = (cell.StartIndex + random.NextFloat() * span) / (samples.Count - 1);
        return PlaceAtLateral(samples, (float)progress, lateral, out _);
    }

    private Vector3 PlaceAtLateral(
        IReadOnlyList<Vector3> samples,
        float progress,
        float lateral,
        out Vector3 forward)
    {
        var sampleIndex = Math.Clamp(
            (int)(progress * (samples.Count - 1)),
            0,
            samples.Count - 2);
        var localProgress = progress * (samples.Count - 1) - sampleIndex;
        var point = samples[sampleIndex].Lerp(samples[sampleIndex + 1], localProgress);
        forward = (samples[sampleIndex + 1] - samples[sampleIndex]).Normalized();
        var right = forward.Cross(Vector3.Up).Normalized();
        var position = point + right * lateral;
        var routeDistance = Mathf.Lerp(
            (float)_routeStartMeters,
            (float)_routeEndMeters,
            progress);
        position.Y += RegionalTerrainRibbon.SurfaceHeight(
            routeDistance,
            _routeLengthMeters,
            lateral);
        return position;
    }

    private void AddMultiMesh(
        string name,
        string automationSuffix,
        Mesh mesh,
        IReadOnlyList<Transform3D> transforms,
        float visibilityBegin,
        float visibilityEnd,
        GeometryInstance3D.ShadowCastingSetting shadows,
        string layer,
        IReadOnlyList<Color>? colors = null,
        Aabb? treeLodBounds = null,
        bool inverseLodDither = false)
    {
        // Disposed once the instance owns it, so no wrapper survives to
        // finalisation after the engine has torn down.
        using var multimesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            UseColors = colors is not null,
            Mesh = mesh,
            InstanceCount = transforms.Count,
        };
        for (var index = 0; index < transforms.Count; index++)
        {
            multimesh.SetInstanceTransform(index, transforms[index]);
            if (colors is not null)
            {
                multimesh.SetInstanceColor(index, colors[index]);
            }
        }
        var fadeTrees = treeLodBounds.HasValue && _treeLodFadeSupported;
        var instance = new MultiMeshInstance3D
        {
            Name = name,
            Multimesh = multimesh,
            VisibilityRangeBegin = visibilityBegin,
            VisibilityRangeBeginMargin = visibilityBegin > 0
                ? fadeTrees ? TreeLodFadeMarginMeters : 12 : 0,
            VisibilityRangeEnd = visibilityEnd,
            VisibilityRangeEndMargin = fadeTrees ? TreeLodFadeMarginMeters : 12,
            VisibilityRangeFadeMode = fadeTrees
                ? GeometryInstance3D.VisibilityRangeFadeModeEnum.Self
                : GeometryInstance3D.VisibilityRangeFadeModeEnum.Disabled,
            CustomAabb = treeLodBounds ?? default,
            CastShadow = shadows,
        };
        if (fadeTrees)
        {
            instance.SetInstanceShaderParameter(TreeLodInverse, inverseLodDither);
        }
        EnvironmentVisualKit.MarkSemantic(
            instance,
            $"environment.chunk.{ChunkId}.{automationSuffix}",
            layer);
        AddChild(instance);
        SemanticNodeCount++;
    }

    private static ulong Seed(string stableSeed, string chunkId, EnvironmentRegion region)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(
            $"{stableSeed}|{chunkId}|{region}|{EnvironmentVisualKit.Version}"));
        return BinaryPrimitives.ReadUInt64LittleEndian(bytes);
    }

    private struct StableRandom(ulong state)
    {
        private ulong _state = state == 0 ? 0x9e3779b97f4a7c15UL : state;

        public float NextFloat()
        {
            _state ^= _state >> 12;
            _state ^= _state << 25;
            _state ^= _state >> 27;
            var value = _state * 0x2545f4914f6cdd1dUL;
            return (value >> 40) / 16777216.0f;
        }
    }

    // The terrain ribbon mesh is built per chunk and handed over by
    // RegionalTerrainRibbon.Build. Its C# wrapper is RefCounted, so left
    // undisposed it survives to finalisation after the engine has torn down.
    //
    // Predelete fires only on actual destruction, unlike _ExitTree which also
    // fires on reparenting, so releasing here cannot strand a live chunk.
    public override void _Notification(int what)
    {
        if (what == NotificationPredelete)
        {
            _ownedTerrainMesh?.Dispose();
            _ownedTerrainMesh = null;
        }
    }
}

public sealed record EnvironmentChunkSnapshot(
    string ChunkId,
    EnvironmentRegion Region,
    int NearInstanceCount,
    int MidInstanceCount,
    int DistantInstanceCount,
    int SemanticNodeCount,
    int TerrainVertexCount,
    int TerrainTriangleCount,
    double BuildMilliseconds,
    bool CollisionFree);
