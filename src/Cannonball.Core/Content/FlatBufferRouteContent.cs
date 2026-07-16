using Cannonball.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Core.Content;

public sealed record RouteContentPackage(
    IRouteGraph Graph,
    IReadOnlyDictionary<string, ChunkManifest> Chunks,
    RouteContentMetadata? Metadata = null);

public sealed record RouteContentMetadata(
    string SourceId,
    string Publisher,
    string SourceUrl,
    string SourceArtifactSha256,
    string AcquisitionLockSha256,
    string RouteCrs,
    string ElevationCrs,
    string HorizontalDatum,
    string VerticalDatum,
    string ElevationUnits,
    string ElevationProductId,
    string ElevationProductTitle,
    string ElevationProductResolution,
    string ElevationArtifactSha256);

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
        if (root.SchemaVersion is not (1 or 2))
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
            var distance = new double[data.SamplesLength];
            var lateral = new float[data.SamplesLength];
            var elevation = new float[data.SamplesLength];
            for (var sampleIndex = 0; sampleIndex < data.SamplesLength; sampleIndex++)
            {
                var sample = data.Samples(sampleIndex);
                distance[sampleIndex] = sample?.DistanceMeters ?? 0;
                lateral[sampleIndex] = sample?.LateralMeters ?? 0;
                elevation[sampleIndex] = sample?.ElevationMeters ?? 0;
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
                    .ToArray())
            {
                SampleDistancesMeters = distance,
                LateralSamples = lateral,
                ElevationSamples = elevation,
            };
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

        RouteContentMetadata? metadata = null;
        if (root.SchemaVersion == 2)
        {
            var provenance = root.Provenance
                ?? throw new InvalidDataException("Route schema 2 is missing source provenance.");
            var spatial = root.SpatialReference
                ?? throw new InvalidDataException("Route schema 2 is missing spatial reference metadata.");
            metadata = new RouteContentMetadata(
                Required(provenance.SourceId, "source ID"),
                Required(provenance.Publisher, "source publisher"),
                Required(provenance.SourceUrl, "source URL"),
                RequiredSha256(provenance.ArtifactSha256, "source artifact hash"),
                RequiredSha256(provenance.AcquisitionLockSha256, "acquisition lock hash"),
                Required(spatial.RouteCrs, "route CRS"),
                Required(spatial.ElevationCrs, "elevation CRS"),
                Required(spatial.HorizontalDatum, "horizontal datum"),
                Required(spatial.VerticalDatum, "vertical datum"),
                Required(spatial.ElevationUnits, "elevation units"),
                Required(spatial.ElevationProductId, "elevation product ID"),
                Required(spatial.ElevationProductTitle, "elevation product title"),
                Required(spatial.ElevationProductResolution, "elevation product resolution"),
                RequiredSha256(spatial.ElevationArtifactSha256, "elevation artifact hash"));
        }

        return new RouteContentPackage(
            new InMemoryRouteGraph(
                Required(root.ContentVersion, "content version"),
                nodes,
                edges),
            chunks,
            metadata);
    }

    private static string Required(string? value, string description) =>
        string.IsNullOrWhiteSpace(value)
            ? throw new InvalidDataException($"Route content is missing {description}.")
            : value;

    private static string RequiredSha256(string? value, string description)
    {
        var digest = Required(value, description);
        if (digest.Length != 64 || digest.Any(character =>
                !char.IsAsciiHexDigit(character) || char.IsAsciiLetterUpper(character)))
        {
            throw new InvalidDataException($"Route content has an invalid {description}.");
        }

        return digest;
    }
}
