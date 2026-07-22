using System.Buffers.Binary;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using Cannonball.Core.Content;
using Godot;

namespace Cannonball.Game.World.Environments;

public sealed partial class RegionalEnvironmentChunk : Node3D
{
    private RegionalEnvironmentChunk()
    {
    }

    public string ChunkId { get; private set; } = string.Empty;
    public EnvironmentRegion Region { get; private set; }
    public int NearInstanceCount { get; private set; }
    public int MidInstanceCount { get; private set; }
    public int DistantInstanceCount { get; private set; }
    public int SemanticNodeCount { get; private set; }
    public double BuildMilliseconds { get; private set; }

    public static RegionalEnvironmentChunk Create(
        RouteChunkContent content,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld,
        EnvironmentVisualKit kit,
        EnvironmentRegion region,
        string stableSeed)
    {
        ArgumentNullException.ThrowIfNull(content);
        ArgumentNullException.ThrowIfNull(frame);
        ArgumentNullException.ThrowIfNull(kit);
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
            Position = anchor.RelativeTo(localOriginWorld),
        };
        EnvironmentVisualKit.MarkSemantic(
            chunk,
            $"environment.chunk.{content.Id}",
            "chunk-root");

        var random = new StableRandom(Seed(stableSeed, content.Id, region));
        var samplePoints = content.Samples
            .Select(sample => frame.ToWorld(sample).RelativeTo(anchor))
            .ToArray();
        chunk.BuildNearLayer(kit, samplePoints, ref random);
        chunk.BuildMidLayer(kit, samplePoints, ref random);
        chunk.BuildDistantLayer(kit, samplePoints, ref random);
        chunk.BuildMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        return chunk;
    }

    public void ShiftForOriginRebase(Vector3 horizontal) => Position -= horizontal;

    public EnvironmentChunkSnapshot CaptureSnapshot() => new(
        ChunkId,
        Region,
        NearInstanceCount,
        MidInstanceCount,
        DistantInstanceCount,
        SemanticNodeCount,
        BuildMilliseconds,
        !ContainsCollisionObject(this));

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

    private void BuildNearLayer(
        EnvironmentVisualKit kit,
        IReadOnlyList<Vector3> samples,
        ref StableRandom random)
    {
        var count = kit.NearInstanceBudget;
        var sparse = Region is EnvironmentRegion.Plains or EnvironmentRegion.UrbanEdge;
        if (sparse)
        {
            count = Math.Max(4, count / 2);
        }
        var mesh = Region == EnvironmentRegion.UrbanEdge ? kit.RockMesh : kit.PineMesh;
        var scale = Region == EnvironmentRegion.UrbanEdge
            ? new Vector2(1.1f, 2.8f)
            : new Vector2(3.5f, 9.0f);
        AddInstances("Near", mesh, count, samples, 145, 260, scale, 1_000, ref random);
        NearInstanceCount = count;
    }

    private void BuildMidLayer(
        EnvironmentVisualKit kit,
        IReadOnlyList<Vector3> samples,
        ref StableRandom random)
    {
        var urban = Region == EnvironmentRegion.UrbanEdge;
        var mesh = urban ? kit.BuildingMesh : kit.FoothillMesh;
        var scale = urban
            ? new Vector2(22, 70)
            : Region == EnvironmentRegion.Plains
                ? new Vector2(30, 70)
                : new Vector2(65, 150);
        AddInstances("Mid", mesh, kit.MidInstanceBudget, samples, 320, 850, scale, 4_000, ref random);
        MidInstanceCount = kit.MidInstanceBudget;
    }

    private void BuildDistantLayer(
        EnvironmentVisualKit kit,
        IReadOnlyList<Vector3> samples,
        ref StableRandom random)
    {
        var urban = Region == EnvironmentRegion.UrbanEdge;
        var mesh = urban ? kit.BuildingMesh : kit.MountainMesh;
        var scale = urban
            ? new Vector2(55, 180)
            : Region == EnvironmentRegion.Plains
                ? new Vector2(150, 340)
                : new Vector2(230, 520);
        AddInstances(
            "Distant",
            mesh,
            kit.DistantInstanceBudget,
            samples,
            1_100,
            2_600,
            scale,
            12_000,
            ref random);
        DistantInstanceCount = kit.DistantInstanceBudget;
    }

    private void AddInstances(
        string layer,
        Mesh mesh,
        int count,
        IReadOnlyList<Vector3> samples,
        float minimumLateral,
        float maximumLateral,
        Vector2 scaleRange,
        float visibilityRange,
        ref StableRandom random)
    {
        var multimesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = mesh,
            InstanceCount = count,
        };
        for (var index = 0; index < count; index++)
        {
            var progress = random.NextFloat();
            var sampleIndex = Math.Clamp(
                (int)(progress * (samples.Count - 1)),
                0,
                samples.Count - 2);
            var localProgress = progress * (samples.Count - 1) - sampleIndex;
            var point = samples[sampleIndex].Lerp(samples[sampleIndex + 1], localProgress);
            var forward = (samples[sampleIndex + 1] - samples[sampleIndex]).Normalized();
            var right = forward.Cross(Vector3.Up).Normalized();
            var side = random.NextFloat() < 0.5f ? -1 : 1;
            var lateral = Mathf.Lerp(minimumLateral, maximumLateral, random.NextFloat()) * side;
            var footprint = Mathf.Lerp(scaleRange.X, scaleRange.Y, random.NextFloat());
            var heightScale = layer == "Near"
                ? footprint
                : footprint * Mathf.Lerp(0.55f, 1.35f, random.NextFloat());
            var position = point + right * lateral;
            position.Y -= layer == "Near" ? 0 : heightScale * 0.18f;
            var basis = Basis.FromEuler(new Vector3(0, random.NextFloat() * Mathf.Tau, 0))
                .Scaled(new Vector3(footprint, heightScale, footprint));
            multimesh.SetInstanceTransform(index, new Transform3D(basis, position));
        }
        var instance = new MultiMeshInstance3D
        {
            Name = $"{layer}Instances",
            Multimesh = multimesh,
            VisibilityRangeEnd = visibilityRange,
            VisibilityRangeFadeMode = GeometryInstance3D.VisibilityRangeFadeModeEnum.Self,
            CastShadow = layer == "Distant"
                ? GeometryInstance3D.ShadowCastingSetting.Off
                : GeometryInstance3D.ShadowCastingSetting.On,
        };
        EnvironmentVisualKit.MarkSemantic(
            instance,
            $"environment.chunk.{ChunkId}.{layer.ToLowerInvariant()}",
            layer.ToLowerInvariant());
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
}

public sealed record EnvironmentChunkSnapshot(
    string ChunkId,
    EnvironmentRegion Region,
    int NearInstanceCount,
    int MidInstanceCount,
    int DistantInstanceCount,
    int SemanticNodeCount,
    double BuildMilliseconds,
    bool CollisionFree);
