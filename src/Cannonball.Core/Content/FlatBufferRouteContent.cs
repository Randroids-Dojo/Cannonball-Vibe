using Cannonball.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Core.Content;

public sealed record RouteContentPackage(
    IRouteGraph Graph,
    IReadOnlyDictionary<string, ChunkManifest> Chunks,
    RouteContentMetadata? Metadata = null,
    RouteSemanticContent? Semantics = null)
{
    public string RootContentHash { get; init; } = string.Empty;
}

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
    public const int MaximumRootBytes = 64_000_000;

    public static RouteContentPackage Load(string path)
    {
        try
        {
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 1,
                FileOptions.SequentialScan);
            if (stream.Length >= MaximumRootBytes)
            {
                throw new InvalidDataException("Route content root exceeds the 64 MB budget.");
            }

            var bytes = new byte[checked((int)stream.Length)];
            stream.ReadExactly(bytes);
            if (stream.ReadByte() != -1)
            {
                throw new InvalidDataException("Route content root changed while it was being read.");
            }
            return Load(bytes);
        }
        catch (FileNotFoundException)
        {
            throw new FileNotFoundException("Route content root is missing.", path);
        }
    }

    public static RouteContentPackage Load(byte[] bytes)
    {
        ArgumentNullException.ThrowIfNull(bytes);
        if (bytes.Length >= MaximumRootBytes)
        {
            throw new InvalidDataException("Route content root exceeds the 64 MB budget.");
        }
        try
        {
            return LoadCore(bytes);
        }
        catch (Exception error) when (error is IndexOutOfRangeException or
            ArgumentOutOfRangeException or OverflowException)
        {
            throw new InvalidDataException(
                "Route content contains an invalid FlatBuffer offset.",
                error);
        }
    }

    private static RouteContentPackage LoadCore(byte[] bytes)
    {
        var buffer = new ByteBuffer(bytes);
        if (!RouteGraphBuffer.RouteGraphBufferBufferHasIdentifier(buffer) ||
            !RouteGraphBuffer.VerifyRouteGraphBuffer(buffer))
        {
            throw new InvalidDataException("Route content is not a valid CBRG FlatBuffer.");
        }

        var root = RouteGraphBuffer.GetRootAsRouteGraphBuffer(buffer);
        if (root.SchemaVersion is not (1 or 2 or 3 or 4))
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
            if (!double.IsFinite(data.LengthMeters) || data.LengthMeters <= 0 || data.LaneCount <= 0)
            {
                throw new InvalidDataException($"Route edge {index} has invalid dimensions.");
            }
            if (root.SchemaVersion >= 3 && data.SamplesLength != 0)
            {
                throw new InvalidDataException("Route schema 3 or newer must not inline edge samples.");
            }
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
            if (!double.IsFinite(data.StartMeters) || !double.IsFinite(data.EndMeters) ||
                data.StartMeters < 0 || data.EndMeters <= data.StartMeters)
            {
                throw new InvalidDataException($"Chunk manifest {index} has an invalid range.");
            }
            if ((root.SchemaVersion >= 3 && data.ByteCount == 0) ||
                data.ByteCount >= FlatBufferRouteChunkContent.MaximumChunkBytes)
            {
                throw new InvalidDataException($"Chunk manifest {index} has an invalid byte count.");
            }
            var manifest = new ChunkManifest(
                Required(data.Id, "chunk id"),
                Required(data.EdgeId, "chunk edge id"),
                data.StartMeters,
                data.EndMeters,
                RequiredSha256(data.ContentHash, "chunk hash"),
                RequiredRelativePath(data.RelativePath, "chunk path"),
                default,
                Enumerable.Range(0, data.ProbableBranchChunkIdsLength)
                    .Select(data.ProbableBranchChunkIds)
                    .Where(value => value is not null)
                    .Cast<string>()
                    .ToArray())
            {
                ByteCount = data.ByteCount,
            };
            chunks.Add(manifest.Id, manifest);
        }

        RouteContentMetadata? metadata = null;
        if (root.SchemaVersion >= 2)
        {
            var provenance = root.Provenance
                ?? throw new InvalidDataException("Route schema 2 or newer is missing source provenance.");
            var spatial = root.SpatialReference
                ?? throw new InvalidDataException(
                    "Route schema 2 or newer is missing spatial reference metadata.");
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

        RouteSemanticContent semantics;
        if (root.SchemaVersion >= 4)
        {
            var loaded = FlatBufferRouteSemantics.Load(root.UnPack(), nodes, edges);
            edges = loaded.Edges;
            semantics = loaded.Semantics;
        }
        else
        {
            for (var index = 0; index < edges.Length; index++)
            {
                edges[index] = edges[index] with
                {
                    LaneSections = [RouteSemanticsCompatibility.CreateLegacyLaneSection(edges[index])],
                };
            }
            semantics = RouteSemanticsCompatibility.CreateLegacyContent(edges);
        }

        var graph = new InMemoryRouteGraph(
                Required(root.ContentVersion, "content version"),
                nodes,
                edges);
        var referenced = new HashSet<string>(StringComparer.Ordinal);
        foreach (var edge in edges)
        {
            if (root.SchemaVersion >= 3 && edge.ChunkIds.Count == 0)
            {
                throw new InvalidDataException($"Edge '{edge.Id}' has no runtime chunks.");
            }
            var expectedStart = 0.0;
            foreach (var chunkId in edge.ChunkIds)
            {
                if (!chunks.TryGetValue(chunkId, out var chunk) || chunk.EdgeId != edge.Id)
                {
                    throw new InvalidDataException(
                        $"Edge '{edge.Id}' references missing or mismatched chunk '{chunkId}'.");
                }
                if (!referenced.Add(chunkId))
                {
                    throw new InvalidDataException($"Route chunk '{chunkId}' is referenced more than once.");
                }
                if (root.SchemaVersion >= 3 &&
                    (chunk.StartMeters != expectedStart || chunk.EndMeters > edge.LengthMeters))
                {
                    throw new InvalidDataException(
                        $"Edge '{edge.Id}' chunks are not contiguous and ordered.");
                }
                expectedStart = chunk.EndMeters;
            }
            if (root.SchemaVersion >= 3 && expectedStart != edge.LengthMeters)
            {
                throw new InvalidDataException(
                    $"Edge '{edge.Id}' chunks do not cover its complete length.");
            }
        }
        if (referenced.Count != chunks.Count)
        {
            throw new InvalidDataException("Route content contains an unreferenced chunk manifest.");
        }
        foreach (var manifest in chunks.Values)
        {
            foreach (var branchChunkId in manifest.ProbableBranchChunkIds)
            {
                if (!chunks.ContainsKey(branchChunkId))
                {
                    throw new InvalidDataException(
                        $"Chunk '{manifest.Id}' references unknown probable branch '{branchChunkId}'.");
                }
            }
        }

        return new RouteContentPackage(graph, chunks, metadata, semantics)
        {
            RootContentHash = Convert.ToHexString(
                System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant(),
        };
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

    private static string RequiredRelativePath(string? value, string description)
    {
        var relativePath = Required(value, description);
        if (Path.IsPathRooted(relativePath) || relativePath.Contains('\\') ||
            relativePath.Contains(':') || relativePath.Split('/').Any(segment =>
                string.IsNullOrEmpty(segment) || segment is "." or ".."))
        {
            throw new InvalidDataException($"Route content has an invalid {description}.");
        }

        return relativePath;
    }
}
