using System.Security.Cryptography;
using System.Text;
using Cannonball.Content;
using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Game.Automation;

public sealed record LongRouteScenarioFixtureData(
    RouteContentPackage Package,
    VerifiedMemoryChunkSource Source,
    IReadOnlyList<string> EdgeIds,
    IReadOnlyList<string> ConnectorIds,
    double TargetDistanceMeters,
    double MaximumGeometryGapMeters,
    string SourceRootContentHash,
    string OverrideId);

public static class LongRouteScenarioFixture
{
    public const string AuthoredOverrideId = "p0-006-deterministic-long-route-v1";
    public const double MetersPerMile = 1_609.344;
    private const double TargetEdgeMeters = 12_500;
    private const double TargetChunkMeters = 2_000;
    private const double TargetSampleMeters = 200;

    public static LongRouteScenarioFixtureData Create(
        RouteContentPackage sourcePackage,
        double targetDistanceMiles,
        ulong seed)
    {
        ArgumentNullException.ThrowIfNull(sourcePackage);
        if (!double.IsFinite(targetDistanceMiles) || targetDistanceMiles <= 0 ||
            targetDistanceMiles > 1_000)
        {
            throw new ArgumentOutOfRangeException(nameof(targetDistanceMiles));
        }

        var targetMeters = targetDistanceMiles * MetersPerMile;
        var edgeCount = Math.Clamp((int)Math.Ceiling(targetMeters / TargetEdgeMeters), 1, 128);
        var edgeLength = targetMeters / edgeCount;
        var sourceHash = sourcePackage.RootContentHash.Length == 64
            ? sourcePackage.RootContentHash
            : sourcePackage.Metadata?.SourceArtifactSha256
                ?? throw new InvalidDataException("Long-route source package has no stable root hash.");
        var contentVersion =
            $"route-v4-long-{targetDistanceMiles:0.###}mi-{seed:x16}-{sourceHash[..12]}";
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            sourcePackage.Metadata?.SourceId ?? "verified-corridor",
            sourcePackage.Graph.ContentVersion,
            sourceHash,
            "Deterministic distance-complete automation corridor derived from a " +
            "checksum-verified source package; not asserted as observed geography.",
            AuthoredOverrideId);
        var routeIdentity = new RouteIdentity(
            "route-p0-006",
            "TEST",
            "500",
            "automation",
            "east",
            "Deterministic Long Route",
            provenance);

        var edges = new List<RouteEdge>(edgeCount);
        var sections = new List<LaneSection>(edgeCount);
        var connectors = new List<JunctionConnector>(Math.Max(0, edgeCount - 1));
        var manifests = new Dictionary<string, ChunkManifest>(StringComparer.Ordinal);
        var payloads = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        var maximumGap = 0.0;
        RouteChunkSample? previousFinalSample = null;

        for (var edgeIndex = 0; edgeIndex < edgeCount; edgeIndex++)
        {
            var edgeId = $"long-edge-{edgeIndex:D3}";
            var fromNodeId = $"long-node-{edgeIndex:D3}";
            var toNodeId = $"long-node-{edgeIndex + 1:D3}";
            var edgeStart = edgeIndex * edgeLength;
            var lane0 = Lane(edgeId, 0, provenance);
            var lane1 = Lane(edgeId, 1, provenance);
            var section = new LaneSection(
                $"{edgeId}:section",
                edgeId,
                0,
                edgeLength,
                [lane0, lane1],
                new RouteShoulder(1.5f, "paved"),
                new RouteShoulder(3.0f, "paved"),
                "east",
                provenance);
            var chunkCount = (int)Math.Ceiling(edgeLength / TargetChunkMeters);
            var chunkIds = new string[chunkCount];
            for (var chunkIndex = 0; chunkIndex < chunkCount; chunkIndex++)
            {
                var start = chunkIndex * edgeLength / chunkCount;
                var end = (chunkIndex + 1) * edgeLength / chunkCount;
                var sampleSegmentCount = Math.Max(2, (int)Math.Ceiling((end - start) / TargetSampleMeters));
                var samples = Enumerable.Range(0, sampleSegmentCount + 1)
                    .Select(sampleIndex =>
                    {
                        var localDistance = start +
                            (end - start) * sampleIndex / sampleSegmentCount;
                        return Sample(edgeStart + localDistance, localDistance, seed);
                    })
                    .ToArray();
                if (previousFinalSample is { } previous)
                {
                    var first = samples[0];
                    var gap = Math.Sqrt(
                        Math.Pow(first.ProjectedXMeters - previous.ProjectedXMeters, 2) +
                        Math.Pow(first.ProjectedYMeters - previous.ProjectedYMeters, 2) +
                        Math.Pow(first.ElevationMeters - previous.ElevationMeters, 2));
                    maximumGap = Math.Max(maximumGap, gap);
                }
                previousFinalSample = samples[^1];

                var chunkId = $"long-chunk-{edgeIndex:D3}-{chunkIndex:D2}";
                var bytes = BuildChunkBytes(contentVersion, chunkId, edgeId, start, end, samples);
                var hash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
                chunkIds[chunkIndex] = chunkId;
                payloads.Add(chunkId, bytes);
                manifests.Add(
                    chunkId,
                    new ChunkManifest(
                        chunkId,
                        edgeId,
                        start,
                        end,
                        hash,
                        $"memory/{chunkId}.cbck",
                        default,
                        [])
                    {
                        ByteCount = (ulong)bytes.Length,
                    });
            }

            sections.Add(section);
            edges.Add(new RouteEdge(
                edgeId,
                fromNodeId,
                toNodeId,
                edgeLength,
                2,
                40.2336,
                [],
                [],
                "authored-long-route",
                "interstate-graybox",
                chunkIds)
            {
                LaneSections = [section],
                RouteIdentityIds = [routeIdentity.Id],
            });
            if (edgeIndex > 0)
            {
                var previousEdgeId = $"long-edge-{edgeIndex - 1:D3}";
                connectors.Add(new JunctionConnector(
                    $"long-connector-{edgeIndex - 1:D3}-{edgeIndex:D3}",
                    fromNodeId,
                    previousEdgeId,
                    $"{previousEdgeId}:lane:0",
                    edgeId,
                    lane0.Id,
                    JunctionMovement.Continuation,
                    provenance));
            }
        }

        if (maximumGap > 0.001)
        {
            throw new InvalidDataException(
                $"Generated long route has a {maximumGap:F6} meter geometry gap.");
        }
        var nodes = Enumerable.Range(0, edgeCount + 1)
            .Select(index => new RouteNode(
                $"long-node-{index:D3}",
                default,
                index is 0 || index == edgeCount ? "route-end" : "route",
                index == edgeCount ? [] : [$"long-edge-{index:D3}"]))
            .ToArray();
        var graph = new InMemoryRouteGraph(contentVersion, nodes, edges);
        var semantics = new RouteSemanticContent(
            sections,
            connectors,
            [routeIdentity],
            [],
            [],
            [],
            [],
            false);
        var syntheticRootMaterial = string.Join(
            '\n',
            new[] { sourceHash, contentVersion, AuthoredOverrideId }
                .Concat(manifests.Values
                    .OrderBy(manifest => manifest.Id, StringComparer.Ordinal)
                    .Select(manifest => $"{manifest.Id}:{manifest.ContentHash}:{manifest.ByteCount}")));
        var package = new RouteContentPackage(graph, manifests, sourcePackage.Metadata, semantics)
        {
            RootContentHash = Convert.ToHexString(SHA256.HashData(
                Encoding.UTF8.GetBytes(syntheticRootMaterial))).ToLowerInvariant(),
        };
        return new LongRouteScenarioFixtureData(
            package,
            new VerifiedMemoryChunkSource(package, payloads),
            edges.Select(edge => edge.Id).ToArray(),
            connectors.Select(connector => connector.Id).ToArray(),
            targetMeters,
            maximumGap,
            sourceHash,
            AuthoredOverrideId);
    }

    private static RouteLane Lane(
        string edgeId,
        int index,
        RouteSemanticProvenance provenance) => new(
        $"{edgeId}:lane:{index}",
        index,
        3.6f,
        LaneRole.General,
        LaneManeuver.Continue,
        provenance);

    private static RouteChunkSample Sample(double globalDistance, double localDistance, ulong seed)
    {
        var phase = (seed % 10_000) / 10_000.0 * Math.PI * 2;
        var lateralWave = 220 * Math.Sin(globalDistance / 30_000 + phase);
        var lateralDerivative = 220.0 / 30_000 * Math.Cos(globalDistance / 30_000 + phase);
        var tangentLength = Math.Sqrt(1 + lateralDerivative * lateralDerivative);
        var elevation = 25 + 4 * Math.Sin(globalDistance / 5_000 + phase * 0.5);
        var grade = 4.0 / 5_000 * Math.Cos(globalDistance / 5_000 + phase * 0.5);
        return new RouteChunkSample(
            localDistance,
            0,
            (float)elevation,
            0,
            (float)grade,
            -780_000 + globalDistance,
            1_920_000 + lateralWave,
            1 / tangentLength,
            lateralDerivative / tangentLength);
    }

    private static byte[] BuildChunkBytes(
        string contentVersion,
        string chunkId,
        string edgeId,
        double start,
        double end,
        IReadOnlyList<RouteChunkSample> samples)
    {
        var data = new RouteChunkBufferT
        {
            SchemaVersion = 1,
            ContentVersion = contentVersion,
            Id = chunkId,
            EdgeId = edgeId,
            StartMeters = start,
            EndMeters = end,
            Samples = samples.Select(sample => new ChunkRouteSampleT
            {
                DistanceMeters = sample.DistanceMeters,
                LateralMeters = sample.LateralMeters,
                ElevationMeters = sample.ElevationMeters,
                Curvature = sample.Curvature,
                Grade = sample.Grade,
                ProjectedXMeters = sample.ProjectedXMeters,
                ProjectedYMeters = sample.ProjectedYMeters,
                ProjectedTangentX = sample.ProjectedTangentX,
                ProjectedTangentY = sample.ProjectedTangentY,
            }).ToList(),
        };
        var builder = new FlatBufferBuilder(16_384);
        var root = RouteChunkBuffer.Pack(builder, data);
        RouteChunkBuffer.FinishRouteChunkBufferBuffer(builder, root);
        return builder.SizedByteArray();
    }
}
