using Cannonball.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Core.Content;

public sealed record RouteContentPackage(
    IRouteGraph Graph,
    IReadOnlyDictionary<string, ChunkManifest> Chunks);

public static class FlatBufferRouteContent
{
    public static RouteContentPackage Load(string path) => Load(File.ReadAllBytes(path));

    public static RouteContentPackage Load(byte[] bytes)
    {
        ArgumentNullException.ThrowIfNull(bytes);
        var buffer = new ByteBuffer(bytes);
        if (!RouteGraphBuffer.RouteGraphBufferBufferHasIdentifier(buffer) ||
            !RouteGraphBuffer.VerifyRouteGraphBuffer(buffer))
        {
            throw new InvalidDataException("Route content is not a valid CBRG FlatBuffer.");
        }

        var root = RouteGraphBuffer.GetRootAsRouteGraphBuffer(buffer);
        if (root.SchemaVersion != 1)
        {
            throw new InvalidDataException($"Unsupported route schema {root.SchemaVersion}.");
        }

        var nodes = new RouteNode[root.NodesLength];
        for (var index = 0; index < nodes.Length; index++)
        {
            var data = root.Nodes(index)
                ?? throw new InvalidDataException($"Route node {index} is missing.");
            var source = data.Source;
            nodes[index] = new RouteNode(
                Required(data.Id, "node id"),
                source.HasValue
                    ? new Cannonball.Core.Routes.SourceCoordinate(
                        source.Value.Longitude,
                        source.Value.Latitude,
                        source.Value.ElevationMeters)
                    : default,
                data.Kind ?? "route",
                Enumerable.Range(0, data.OutgoingEdgeIdsLength)
                    .Select(data.OutgoingEdgeIds)
                    .Where(value => value is not null)
                    .Cast<string>()
                    .ToArray());
        }

        var edges = new RouteEdge[root.EdgesLength];
        for (var index = 0; index < edges.Length; index++)
        {
            var data = root.Edges(index)
                ?? throw new InvalidDataException($"Route edge {index} is missing.");
            var curvature = new float[data.SamplesLength];
            var grade = new float[data.SamplesLength];
            for (var sampleIndex = 0; sampleIndex < data.SamplesLength; sampleIndex++)
            {
                var sample = data.Samples(sampleIndex);
                curvature[sampleIndex] = sample?.Curvature ?? 0;
                grade[sampleIndex] = sample?.Grade ?? 0;
            }

            edges[index] = new RouteEdge(
                Required(data.Id, "edge id"),
                Required(data.FromNodeId, "from node id"),
                Required(data.ToNodeId, "to node id"),
                data.LengthMeters,
                data.LaneCount,
                data.SpeedLimitMps,
                curvature,
                grade,
                data.RegionId ?? "unassigned",
                data.GenerationProfile ?? "interstate",
                Enumerable.Range(0, data.ChunkIdsLength)
                    .Select(data.ChunkIds)
                    .Where(value => value is not null)
                    .Cast<string>()
                    .ToArray());
        }

        var chunks = new Dictionary<string, ChunkManifest>(StringComparer.Ordinal);
        for (var index = 0; index < root.ChunksLength; index++)
        {
            var data = root.Chunks(index)
                ?? throw new InvalidDataException($"Chunk manifest {index} is missing.");
            var manifest = new ChunkManifest(
                Required(data.Id, "chunk id"),
                Required(data.EdgeId, "chunk edge id"),
                data.StartMeters,
                data.EndMeters,
                Required(data.ContentHash, "chunk hash"),
                data.RelativePath ?? string.Empty,
                default,
                Enumerable.Range(0, data.ProbableBranchChunkIdsLength)
                    .Select(data.ProbableBranchChunkIds)
                    .Where(value => value is not null)
                    .Cast<string>()
                    .ToArray());
            chunks.Add(manifest.Id, manifest);
        }

        return new RouteContentPackage(
            new InMemoryRouteGraph(
                Required(root.ContentVersion, "content version"),
                nodes,
                edges),
            chunks);
    }

    private static string Required(string? value, string description) =>
        string.IsNullOrWhiteSpace(value)
            ? throw new InvalidDataException($"Route content is missing {description}.")
            : value;
}
