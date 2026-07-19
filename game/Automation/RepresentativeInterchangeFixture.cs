using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Cannonball.Content;
using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Game.Automation;

public sealed record InterchangeGeometryValidation(
    int GradeSeparatedCrossings,
    double MinimumVerticalClearanceMeters,
    int SelfIntersections,
    int InvalidShortcuts,
    int ParallelCarriagewayPairs,
    double MaximumAbsoluteGrade,
    double MaximumAbsoluteCurvaturePerMeter,
    double MinimumSightlineMeters);

public sealed record InterchangeGeometryLimits(
    int MinimumGradeSeparatedCrossings,
    double MinimumVerticalClearanceMeters,
    int MinimumParallelCarriagewayPairs,
    int MaximumSelfIntersections,
    int MaximumInvalidShortcuts,
    double MaximumAbsoluteGrade,
    double MaximumAbsoluteCurvaturePerMeter,
    double MinimumSightlineMeters);

public sealed record RepresentativeInterchangeFixtureData(
    RouteContentPackage Package,
    VerifiedMemoryChunkSource Source,
    IReadOnlyDictionary<string, ValidatedRoutePlan> Plans,
    InterchangeGeometryValidation GeometryValidation,
    InterchangeGeometryLimits GeometryLimits,
    IReadOnlyList<string> DecisionEdgeIds,
    string OverrideId);

public static class RepresentativeInterchangeFixture
{
    public const string AuthoredOverrideId = "p0-011-representative-interchanges-v1";
    public const string StayPlanId = "stay-current-highway";
    public const string ExitPlanId = "take-diamond-exit";
    public const string TransferPlanId = "take-directional-transfer";
    public const string SemiDirectionalTransferPlanId = "take-semi-directional-transfer";
    private const string ValidationContractPath =
        "res://data/routes/fixtures/validation/legal-interchanges.json";
    private const double SightlineLookaheadMeters = 120;
    private const double SightlineEyeHeightMeters = 1.08;
    private const double SightlineTargetHeightMeters = 0.60;
    private const double SightlineSurfaceClearanceMeters = 0.10;
    private const double RepresentativeLaneWidthMeters = 3.6;

    public static RepresentativeInterchangeFixtureData Create(RouteContentPackage sourcePackage)
    {
        ArgumentNullException.ThrowIfNull(sourcePackage);
        var geometryLimits = LoadGeometryLimits();
        var sourceHash = sourcePackage.Metadata?.SourceArtifactSha256 ??
            Convert.ToHexString(SHA256.HashData(
                Encoding.UTF8.GetBytes(sourcePackage.Graph.ContentVersion))).ToLowerInvariant();
        var contentVersion = $"route-v5-interchanges-{StableSuffix(sourceHash)}";
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            sourcePackage.Metadata?.SourceId ?? "representative-corridor",
            sourcePackage.Graph.ContentVersion,
            sourceHash,
            "Deterministic diamond and directional interchange overlay derived from the " +
            "checksum-verified representative source package.",
            AuthoredOverrideId);

        const double baseX = -780_000;
        const double baseY = 1_920_000;
        Point P(double x, double y, double elevation) => new(baseX + x, baseY + y, elevation);
        var specs = new[]
        {
            new EdgeSpec(
                "interchange-approach",
                "node-start",
                "node-diamond-decision",
                "route-us36",
                [P(0, 0, 8), P(170, 0, 8), P(330, 0, 8), P(500, 0, 8)],
                [
                    Lane("approach-stay", 0, LaneManeuver.Continue, provenance),
                    Lane("approach-exit", 1, LaneManeuver.Exit, provenance, LaneRole.ExitOnly),
                    Lane("approach-transfer", 2, LaneManeuver.Continue, provenance),
                ]),
            new EdgeSpec(
                "diamond-through",
                "node-diamond-decision",
                "node-diamond-rejoin",
                "route-us36",
                [P(500, 0, 8), P(700, 0, 8), P(900, 0, 8), P(1_100, 0, 8)],
                [
                    Lane("diamond-through-stay", 0, LaneManeuver.Continue, provenance),
                    Lane("diamond-through-transfer", 1, LaneManeuver.Continue, provenance),
                ]),
            new EdgeSpec(
                "diamond-exit-ramp",
                "node-diamond-decision",
                "node-crossroad-south",
                "route-co93",
                Bezier(
                    P(500, 0, 8),
                    P(600, 0, 8),
                    P(700, -100, 0),
                    P(700, -200, 0),
                    17),
                [Lane("diamond-exit-lane", 0, LaneManeuver.Exit, provenance, LaneRole.ExitOnly)]),
            new EdgeSpec(
                "diamond-crossroad",
                "node-crossroad-south",
                "node-crossroad-north",
                "route-co93",
                [P(700, -200, 0), P(700, -70, 0), P(700, 70, 0), P(700, 200, 0)],
                [Lane("crossroad-lane", 0, LaneManeuver.Entrance, provenance)]),
            new EdgeSpec(
                "diamond-entrance-ramp",
                "node-crossroad-north",
                "node-diamond-rejoin",
                "route-us36",
                Bezier(
                    P(700, 200, 0),
                    P(700, 350, 0),
                    P(900, 0, 8),
                    P(1_100, 0, 8),
                    17),
                [Lane("diamond-entrance-lane", 0, LaneManeuver.Entrance, provenance, LaneRole.EntranceOnly)]),
            new EdgeSpec(
                "between-interchanges",
                "node-diamond-rejoin",
                "node-transfer-decision",
                "route-us36",
                [P(1_100, 0, 8), P(1_230, 0, 8), P(1_360, 0, 8), P(1_500, 0, 8)],
                [
                    Lane("between-stay", 0, LaneManeuver.Continue, provenance),
                    Lane("between-exit-return", 1, LaneManeuver.Continue, provenance),
                    Lane("between-transfer", 2, LaneManeuver.HighwayTransfer, provenance, LaneRole.ExitOnly),
                ]),
            new EdgeSpec(
                "directional-through",
                "node-transfer-decision",
                "node-current-finish",
                "route-us36",
                [P(1_500, 0, 8), P(1_700, 0, 8), P(1_900, 0, 8), P(2_100, 0, 8)],
                [
                    Lane("directional-through-stay", 0, LaneManeuver.Continue, provenance),
                    Lane("directional-through-return", 1, LaneManeuver.Continue, provenance),
                ]),
            new EdgeSpec(
                "directional-transfer-ramp",
                "node-transfer-decision",
                "node-transfer-merge",
                "route-i25",
                Bezier(
                    P(1_500, 0, 8),
                    P(1_600, 0, 8),
                    P(1_600, 350, 16),
                    P(1_900, 350, 16),
                    17),
                [Lane("directional-transfer-lane", 0, LaneManeuver.HighwayTransfer, provenance, LaneRole.ExitOnly)]),
            new EdgeSpec(
                "receiving-highway",
                "node-transfer-merge",
                "node-transfer-finish",
                "route-i25",
                [P(1_900, 350, 16), P(2_100, 350, 16), P(2_300, 350, 16), P(2_500, 350, 16)],
                [
                    Lane("receiving-lane-0", 0, LaneManeuver.Continue, provenance),
                    Lane("receiving-lane-1", 1, LaneManeuver.Continue, provenance),
                ]),
            new EdgeSpec(
                "semi-directional-transfer-ramp",
                "node-transfer-decision",
                "node-north-transfer-merge",
                "route-i25-north",
                Bezier(
                    P(1_500, -RepresentativeLaneWidthMeters, 8),
                    P(1_600, -RepresentativeLaneWidthMeters, 10),
                    P(1_725, -390 - RepresentativeLaneWidthMeters, 16),
                    P(1_900, -400 - RepresentativeLaneWidthMeters, 16),
                    17),
                [
                    Lane("semi-directional-transfer-lane-2", 0, LaneManeuver.HighwayTransfer, provenance, LaneRole.ExitOnly),
                ]),
            new EdgeSpec(
                "north-receiving-highway",
                "node-north-transfer-merge",
                "node-north-transfer-finish",
                "route-i25-north",
                [P(1_900, -400, 16), P(2_100, -400, 16), P(2_300, -400, 16), P(2_500, -400, 16)],
                [
                    Lane("north-receiving-lane-0", 0, LaneManeuver.Continue, provenance),
                    Lane("north-receiving-lane-1", 1, LaneManeuver.Continue, provenance),
                    Lane("north-receiving-lane-2", 2, LaneManeuver.Continue, provenance),
                ]),
            new EdgeSpec(
                "opposing-carriageway",
                "node-opposing-east",
                "node-opposing-west",
                "route-i25-opposing",
                [P(2_500, 390, 16), P(2_300, 390, 16), P(2_100, 390, 16), P(1_900, 390, 16)],
                [
                    Lane("opposing-lane-0", 0, LaneManeuver.Continue, provenance),
                    Lane("opposing-lane-1", 1, LaneManeuver.Continue, provenance),
                ]),
        };

        var built = specs.Select(spec => BuildEdge(contentVersion, spec, provenance)).ToArray();
        var edges = built.Select(item => item.Edge).ToArray();
        var chunks = built.ToDictionary(item => item.Manifest.Id, item => item.Manifest, StringComparer.Ordinal);
        var chunkBytes = built.ToDictionary(item => item.Manifest.Id, item => item.Bytes, StringComparer.Ordinal);
        var nodes = BuildNodes(edges);
        var graph = new InMemoryRouteGraph(contentVersion, nodes, edges);
        var connectors = BuildConnectors(provenance);
        var identities = BuildRouteIdentities(provenance);
        var exits = BuildExits(provenance);
        var milepointAnchors = BuildMilepointAnchors(provenance);
        var roadsideMarkers = BuildRoadsideMarkers(provenance);
        var mapGeometry = built
            .SelectMany(item => new[]
            {
                BuildMapGeometry(item, lod: 0, stride: 1),
                BuildMapGeometry(item, lod: 1, stride: 4),
                BuildMapGeometry(item, lod: 2, stride: int.MaxValue),
            })
            .ToArray();
        var semantics = new RouteSemanticContent(
            built.Select(item => item.Section).ToArray(),
            connectors,
            identities,
            exits,
            milepointAnchors,
            roadsideMarkers,
            mapGeometry,
            false);

        var decisionChunks = new[]
        {
            chunks["chunk-interchange-approach"],
            chunks["chunk-between-interchanges"],
        };
        chunks[decisionChunks[0].Id] = decisionChunks[0] with
        {
            ProbableBranchChunkIds =
            [
                "chunk-diamond-through",
                "chunk-diamond-exit-ramp",
            ],
        };
        chunks[decisionChunks[1].Id] = decisionChunks[1] with
        {
            ProbableBranchChunkIds =
            [
                "chunk-directional-through",
                "chunk-directional-transfer-ramp",
                "chunk-semi-directional-transfer-ramp",
            ],
        };
        var package = new RouteContentPackage(graph, chunks, sourcePackage.Metadata, semantics)
        {
            RootContentHash = sourcePackage.RootContentHash,
        };
        var source = new VerifiedMemoryChunkSource(package, chunkBytes);
        var catalog = new RouteChoiceCatalog(graph, semantics);
        var plans = BuildPlanSelections().ToDictionary(
            plan => plan.Id,
            catalog.ValidatePlan,
            StringComparer.Ordinal);
        var validation = ValidateGeometry(built, graph, connectors, geometryLimits);
        return new RepresentativeInterchangeFixtureData(
            package,
            source,
            plans,
            validation,
            geometryLimits,
            ["interchange-approach", "between-interchanges"],
            AuthoredOverrideId);
    }

    private static IReadOnlyList<RoutePlanSelection> BuildPlanSelections() =>
    [
        new RoutePlanSelection(
            StayPlanId,
            [
                "interchange-approach",
                "diamond-through",
                "between-interchanges",
                "directional-through",
            ],
            ["connector-stay", "connector-stay-rejoin", "connector-stay-finish"],
            "approach-stay"),
        new RoutePlanSelection(
            ExitPlanId,
            [
                "interchange-approach",
                "diamond-exit-ramp",
                "diamond-crossroad",
                "diamond-entrance-ramp",
                "between-interchanges",
                "directional-through",
            ],
            [
                "connector-diamond-exit",
                "connector-exit-crossroad",
                "connector-crossroad-entrance",
                "connector-entrance-rejoin",
                "connector-return-finish",
            ],
            "approach-exit"),
        new RoutePlanSelection(
            TransferPlanId,
            [
                "interchange-approach",
                "diamond-through",
                "between-interchanges",
                "directional-transfer-ramp",
                "receiving-highway",
            ],
            [
                "connector-transfer-approach",
                "connector-transfer-rejoin",
                "connector-highway-transfer",
                "connector-transfer-merge",
            ],
            "approach-transfer"),
        new RoutePlanSelection(
            SemiDirectionalTransferPlanId,
            [
                "interchange-approach",
                "diamond-through",
                "between-interchanges",
                "semi-directional-transfer-ramp",
                "north-receiving-highway",
            ],
            [
                "connector-transfer-approach",
                "connector-transfer-rejoin",
                "connector-semi-highway-transfer",
                "connector-semi-transfer-merge",
            ],
            "approach-transfer"),
    ];

    private static IReadOnlyList<JunctionConnector> BuildConnectors(
        RouteSemanticProvenance provenance) =>
    [
        Connector("connector-stay", "node-diamond-decision", "interchange-approach", "approach-stay", "diamond-through", "diamond-through-stay", JunctionMovement.Continuation, provenance),
        Connector("connector-transfer-approach", "node-diamond-decision", "interchange-approach", "approach-transfer", "diamond-through", "diamond-through-transfer", JunctionMovement.Continuation, provenance),
        Connector("connector-diamond-exit", "node-diamond-decision", "interchange-approach", "approach-exit", "diamond-exit-ramp", "diamond-exit-lane", JunctionMovement.Exit, provenance),
        Connector("connector-stay-rejoin", "node-diamond-rejoin", "diamond-through", "diamond-through-stay", "between-interchanges", "between-stay", JunctionMovement.Continuation, provenance),
        Connector("connector-transfer-rejoin", "node-diamond-rejoin", "diamond-through", "diamond-through-transfer", "between-interchanges", "between-transfer", JunctionMovement.Continuation, provenance),
        Connector("connector-exit-crossroad", "node-crossroad-south", "diamond-exit-ramp", "diamond-exit-lane", "diamond-crossroad", "crossroad-lane", JunctionMovement.Exit, provenance),
        Connector("connector-crossroad-entrance", "node-crossroad-north", "diamond-crossroad", "crossroad-lane", "diamond-entrance-ramp", "diamond-entrance-lane", JunctionMovement.Entrance, provenance),
        Connector("connector-entrance-rejoin", "node-diamond-rejoin", "diamond-entrance-ramp", "diamond-entrance-lane", "between-interchanges", "between-exit-return", JunctionMovement.Entrance, provenance),
        Connector("connector-stay-finish", "node-transfer-decision", "between-interchanges", "between-stay", "directional-through", "directional-through-stay", JunctionMovement.Continuation, provenance),
        Connector("connector-return-finish", "node-transfer-decision", "between-interchanges", "between-exit-return", "directional-through", "directional-through-return", JunctionMovement.Continuation, provenance),
        Connector("connector-highway-transfer", "node-transfer-decision", "between-interchanges", "between-transfer", "directional-transfer-ramp", "directional-transfer-lane", JunctionMovement.HighwayTransfer, provenance),
        Connector("connector-transfer-merge", "node-transfer-merge", "directional-transfer-ramp", "directional-transfer-lane", "receiving-highway", "receiving-lane-0", JunctionMovement.HighwayTransfer, provenance),
        Connector("connector-semi-highway-transfer", "node-transfer-decision", "between-interchanges", "between-transfer", "semi-directional-transfer-ramp", "semi-directional-transfer-lane-2", JunctionMovement.HighwayTransfer, provenance),
        Connector("connector-semi-transfer-merge", "node-north-transfer-merge", "semi-directional-transfer-ramp", "semi-directional-transfer-lane-2", "north-receiving-highway", "north-receiving-lane-2", JunctionMovement.HighwayTransfer, provenance),
    ];

    private static IReadOnlyList<RouteIdentity> BuildRouteIdentities(
        RouteSemanticProvenance provenance) =>
    [
        new RouteIdentity("route-us36", "US", "36", "us", "east", "Boulder Turnpike", provenance),
        new RouteIdentity("route-us287", "US", "287", "us", "east", "Federal Boulevard", provenance),
        new RouteIdentity("route-co93", "CO", "93", "state", "north", "Foothills Highway", provenance),
        new RouteIdentity("route-i25", "I", "25", "interstate", "south", "Valley Highway", provenance),
        new RouteIdentity("route-i25-north", "I", "25", "interstate", "north", "Valley Highway", provenance),
        new RouteIdentity("route-i25-opposing", "I", "25", "interstate", "north", "Valley Highway", provenance),
    ];

    private static IReadOnlyList<MilepointAnchor> BuildMilepointAnchors(
        RouteSemanticProvenance provenance) =>
    [
        new MilepointAnchor("mile-us36-42", "route-us36", "interchange-approach", 100, 42, "CO-US36", "east", provenance),
        new MilepointAnchor("mile-us287-250", "route-us287", "interchange-approach", 100, 250, "CO-US287", "east", provenance),
        new MilepointAnchor("mile-us36-43", "route-us36", "between-interchanges", 250, 43, "CO-US36", "east", provenance),
        new MilepointAnchor("mile-i25-214", "route-i25", "receiving-highway", 100, 214, "CO-I25", "south", provenance),
        new MilepointAnchor("mile-i25-216", "route-i25-north", "north-receiving-highway", 100, 216, "CO-I25", "north", provenance),
        new MilepointAnchor("mile-i25-215-north", "route-i25-opposing", "opposing-carriageway", 100, 215, "CO-I25", "north", provenance),
    ];

    private static IReadOnlyList<RoadsideMarker> BuildRoadsideMarkers(
        RouteSemanticProvenance provenance) =>
    [
        new RoadsideMarker("marker-us36-42", "mile", "route-us36", "interchange-approach", 100, "42", provenance),
        new RoadsideMarker("marker-us287-250", "mile", "route-us287", "interchange-approach", 100, "250", provenance),
        new RoadsideMarker("marker-us36-43", "mile", "route-us36", "between-interchanges", 250, "43", provenance),
        new RoadsideMarker("marker-us36-missing-anchor", "mile", "route-us36", "between-interchanges", 400, "44", provenance),
        new RoadsideMarker("marker-i25-214", "mile", "route-i25", "receiving-highway", 100, "214", provenance),
        new RoadsideMarker("marker-i25-216", "mile", "route-i25-north", "north-receiving-highway", 100, "216", provenance),
        new RoadsideMarker("marker-i25-215-north", "mile", "route-i25-opposing", "opposing-carriageway", 100, "215", provenance),
    ];

    private static IReadOnlyList<RouteExit> BuildExits(RouteSemanticProvenance provenance) =>
    [
        new RouteExit(
            "exit-42a",
            "node-diamond-decision",
            "diamond-exit-ramp",
            "route-us36",
            "42",
            "A",
            ["Boulder Junction", "Nederland"],
            ["fuel", "food"],
            provenance),
        new RouteExit(
            "transfer-44",
            "node-transfer-decision",
            "directional-transfer-ramp",
            "route-us36",
            "44",
            string.Empty,
            ["Interstate 25 South", "Denver"],
            [],
            provenance),
        new RouteExit(
            "transfer-44b",
            "node-transfer-decision",
            "semi-directional-transfer-ramp",
            "route-us36",
            "44",
            "B",
            ["Interstate 25 North", "Fort Collins"],
            [],
            provenance),
    ];

    private static BuiltEdge BuildEdge(
        string contentVersion,
        EdgeSpec spec,
        RouteSemanticProvenance provenance)
    {
        const int sampleSegments = 25;
        var raw = spec.ControlPoints.Count == 4
            ? Enumerable.Range(0, sampleSegments + 1)
                .Select(index => Evaluate(spec.ControlPoints, index / (double)sampleSegments))
                .ToArray()
            : spec.ControlPoints.ToArray();
        var distances = new double[raw.Length];
        for (var index = 1; index < raw.Length; index++)
        {
            distances[index] = distances[index - 1] + raw[index - 1].DistanceTo(raw[index]);
        }
        var length = distances[^1];
        var samples = raw.Select((point, index) =>
        {
            var before = raw[Math.Max(0, index - 1)];
            var after = raw[Math.Min(raw.Length - 1, index + 1)];
            var tangentLength = Math.Sqrt(
                Math.Pow(after.X - before.X, 2) + Math.Pow(after.Y - before.Y, 2));
            var horizontalSpan = Math.Max(1e-6, tangentLength);
            var tangentX = (after.X - before.X) / horizontalSpan;
            var tangentY = (after.Y - before.Y) / horizontalSpan;
            var grade = (float)((after.Elevation - before.Elevation) / horizontalSpan);
            var curvature = 0f;
            if (index > 0 && index < raw.Length - 1)
            {
                var incomingX = point.X - before.X;
                var incomingY = point.Y - before.Y;
                var outgoingX = after.X - point.X;
                var outgoingY = after.Y - point.Y;
                var headingChange = Math.Atan2(
                    incomingX * outgoingY - incomingY * outgoingX,
                    incomingX * outgoingX + incomingY * outgoingY);
                var incomingLength = Math.Sqrt(
                    incomingX * incomingX + incomingY * incomingY);
                var outgoingLength = Math.Sqrt(
                    outgoingX * outgoingX + outgoingY * outgoingY);
                var averageSegmentLength = Math.Max(
                    1e-6,
                    (incomingLength + outgoingLength) / 2);
                curvature = (float)(headingChange / averageSegmentLength);
            }
            return new RouteChunkSample(
                distances[index],
                0,
                (float)point.Elevation,
                curvature,
                grade,
                point.X,
                point.Y,
                tangentX,
                tangentY);
        }).ToArray();
        var chunkId = $"chunk-{spec.Id}";
        var bytes = BuildChunkBytes(contentVersion, chunkId, spec.Id, length, samples);
        var hash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        var manifest = new ChunkManifest(
            chunkId,
            spec.Id,
            0,
            length,
            hash,
            $"memory/{chunkId}.cbck",
            default,
            [])
        {
            ByteCount = (ulong)bytes.Length,
        };
        var section = new LaneSection(
            $"section-{spec.Id}",
            spec.Id,
            0,
            length,
            spec.Lanes,
            new RouteShoulder(1.5f, "paved"),
            new RouteShoulder(2.5f, "paved"),
            spec.RouteIdentityId switch
            {
                "route-i25" => "south",
                "route-i25-north" => "north",
                "route-i25-opposing" => "north",
                _ => "east",
            },
            provenance);
        var edge = new RouteEdge(
            spec.Id,
            spec.FromNodeId,
            spec.ToNodeId,
            length,
            spec.Lanes.Count,
            31.2928,
            [],
            [],
            "authored-representative-interchanges",
            "interstate-graybox",
            [chunkId])
        {
            LaneSections = [section],
            RouteIdentityIds = spec.Id == "interchange-approach"
                ? [spec.RouteIdentityId, "route-us287"]
                : [spec.RouteIdentityId],
            RoadwayKind = spec.Id switch
            {
                "receiving-highway" or "opposing-carriageway" =>
                    RoadwayKind.DividedCarriageway,
                "diamond-exit-ramp" or "diamond-entrance-ramp" or
                    "directional-transfer-ramp" or "semi-directional-transfer-ramp" =>
                    RoadwayKind.OneWayRamp,
                _ => RoadwayKind.Unclassified,
            },
            CarriagewayGroupId = spec.Id is "receiving-highway" or "opposing-carriageway"
                ? "i25-representative-pair"
                : string.Empty,
            OpposingEdgeId = spec.Id switch
            {
                "receiving-highway" => "opposing-carriageway",
                "opposing-carriageway" => "receiving-highway",
                _ => string.Empty,
            },
        };
        return new BuiltEdge(edge, section, manifest, bytes, samples);
    }

    private static byte[] BuildChunkBytes(
        string contentVersion,
        string chunkId,
        string edgeId,
        double length,
        IReadOnlyList<RouteChunkSample> samples)
    {
        var data = new RouteChunkBufferT
        {
            SchemaVersion = 1,
            ContentVersion = contentVersion,
            Id = chunkId,
            EdgeId = edgeId,
            StartMeters = 0,
            EndMeters = length,
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

    private static SimplifiedMapGeometry BuildMapGeometry(
        BuiltEdge built,
        int lod,
        int stride)
    {
        var selected = new List<RouteChunkSample> { built.Samples[0] };
        if (stride != int.MaxValue)
        {
            for (var index = stride; index < built.Samples.Count - 1; index += stride)
            {
                selected.Add(built.Samples[index]);
            }
        }
        selected.Add(built.Samples[^1]);
        var points = selected
            .Select(sample => new Cannonball.Core.Routes.SimplifiedMapPoint(
                sample.ProjectedXMeters,
                sample.ProjectedYMeters,
                sample.DistanceMeters))
            .ToArray();
        return new SimplifiedMapGeometry(
            built.Edge.Id,
            lod,
            points,
            RouteSemanticsCompatibility.ComputeMapGeometryHash(built.Edge.Id, lod, points));
    }

    private static IReadOnlyList<RouteNode> BuildNodes(IReadOnlyList<RouteEdge> edges)
    {
        var ids = edges
            .SelectMany(edge => new[] { edge.FromNodeId, edge.ToNodeId })
            .Distinct(StringComparer.Ordinal)
            .OrderBy(id => id, StringComparer.Ordinal);
        return ids.Select(id => new RouteNode(
            id,
            default,
            id.Contains("decision", StringComparison.Ordinal) ? "interchange" : "route",
            edges.Where(edge => string.Equals(edge.FromNodeId, id, StringComparison.Ordinal))
                .Select(edge => edge.Id)
                .OrderBy(edgeId => edgeId, StringComparer.Ordinal)
                .ToArray())).ToArray();
    }

    private static InterchangeGeometryValidation ValidateGeometry(
        IReadOnlyList<BuiltEdge> built,
        IRouteGraph graph,
        IReadOnlyList<JunctionConnector> connectors,
        InterchangeGeometryLimits limits)
    {
        ValidateRampLaneConnections(built, connectors);
        var selfIntersections = built.Sum(edge => CountSelfIntersections(edge.Samples));
        var gradeSeparatedCrossings = 0;
        var minimumClearance = double.PositiveInfinity;
        for (var leftIndex = 0; leftIndex < built.Count; leftIndex++)
        {
            for (var rightIndex = leftIndex + 1; rightIndex < built.Count; rightIndex++)
            {
                var left = built[leftIndex];
                var right = built[rightIndex];
                if (ShareNode(left.Edge, right.Edge))
                {
                    continue;
                }
                foreach (var leftSegment in Segments(left.Samples))
                {
                    foreach (var rightSegment in Segments(right.Samples))
                    {
                        if (!TryIntersection(leftSegment, rightSegment, out var leftFactor, out var rightFactor))
                        {
                            continue;
                        }
                        var leftElevation = Lerp(
                            leftSegment.Start.ElevationMeters,
                            leftSegment.End.ElevationMeters,
                            leftFactor);
                        var rightElevation = Lerp(
                            rightSegment.Start.ElevationMeters,
                            rightSegment.End.ElevationMeters,
                            rightFactor);
                        var clearance = Math.Abs(leftElevation - rightElevation);
                        if (clearance < 5)
                        {
                            throw new InvalidDataException(
                                $"Edges '{left.Edge.Id}' and '{right.Edge.Id}' create an " +
                                $"unconnected shortcut with {clearance:F3} m clearance.");
                        }
                        gradeSeparatedCrossings++;
                        minimumClearance = Math.Min(minimumClearance, clearance);
                    }
                }
            }
        }

        var invalidShortcuts = connectors.Count(connector =>
        {
            var from = graph.GetEdge(connector.FromEdgeId);
            var to = graph.GetEdge(connector.ToEdgeId);
            return !string.Equals(from.ToNodeId, connector.JunctionNodeId, StringComparison.Ordinal) ||
                !string.Equals(to.FromNodeId, connector.JunctionNodeId, StringComparison.Ordinal);
        });
        var parallelCarriagewayPairs = CountParallelCarriagewayPairs(built);
        var maximumAbsoluteGrade = built
            .SelectMany(edge => edge.Samples)
            .Max(sample => Math.Abs(sample.Grade));
        var maximumAbsoluteCurvature = built
            .SelectMany(edge => edge.Samples)
            .Max(sample => Math.Abs(sample.Curvature));
        var sightlines = built
            .SelectMany(edge => Sightlines(edge.Samples, SightlineLookaheadMeters))
            .ToArray();
        var expectedSightlines = built.Sum(edge =>
            CountSightlineCandidates(edge.Samples, SightlineLookaheadMeters));
        var minimumSightline = sightlines.Length == 0 || sightlines.Length != expectedSightlines
            ? 0
            : sightlines.Min();
        if (selfIntersections > limits.MaximumSelfIntersections ||
            invalidShortcuts > limits.MaximumInvalidShortcuts ||
            gradeSeparatedCrossings < limits.MinimumGradeSeparatedCrossings ||
            minimumClearance < limits.MinimumVerticalClearanceMeters ||
            parallelCarriagewayPairs < limits.MinimumParallelCarriagewayPairs ||
            maximumAbsoluteGrade > limits.MaximumAbsoluteGrade ||
            maximumAbsoluteCurvature > limits.MaximumAbsoluteCurvaturePerMeter ||
            minimumSightline < limits.MinimumSightlineMeters)
        {
            throw new InvalidDataException(
                "Representative interchange geometry did not satisfy its topology gates: " +
                $"self_intersections={selfIntersections}, invalid_shortcuts={invalidShortcuts}, " +
                $"grade_separated_crossings={gradeSeparatedCrossings}, " +
                $"parallel_carriageway_pairs={parallelCarriagewayPairs}, " +
                $"max_abs_grade={maximumAbsoluteGrade:F6}, " +
                $"max_abs_curvature_per_m={maximumAbsoluteCurvature:F6}, " +
                $"minimum_sightline_m={minimumSightline:F3}, " +
                $"edge_metrics={string.Join(';', built.Select(edge =>
                    $"{edge.Edge.Id}:g={edge.Samples.Max(sample => Math.Abs(sample.Grade)):F6}," +
                    $"c={edge.Samples.Max(sample => Math.Abs(sample.Curvature)):F6}"))}.");
        }
        return new InterchangeGeometryValidation(
            gradeSeparatedCrossings,
            minimumClearance,
            selfIntersections,
            invalidShortcuts,
            parallelCarriagewayPairs,
            maximumAbsoluteGrade,
            maximumAbsoluteCurvature,
            minimumSightline);
    }

    private static int CountParallelCarriagewayPairs(IReadOnlyList<BuiltEdge> built)
    {
        var count = 0;
        for (var leftIndex = 0; leftIndex < built.Count; leftIndex++)
        {
            for (var rightIndex = leftIndex + 1; rightIndex < built.Count; rightIndex++)
            {
                var left = built[leftIndex].Samples;
                var right = built[rightIndex].Samples;
                var sameDirection =
                    HorizontalDistance(left[0], right[0]) <= 75 &&
                    HorizontalDistance(left[^1], right[^1]) <= 75;
                var oppositeDirection =
                    HorizontalDistance(left[0], right[^1]) <= 75 &&
                    HorizontalDistance(left[^1], right[0]) <= 75;
                if (sameDirection || oppositeDirection)
                {
                    count++;
                }
            }
        }
        return count;
    }

    private static void ValidateRampLaneConnections(
        IReadOnlyList<BuiltEdge> built,
        IReadOnlyList<JunctionConnector> connectors)
    {
        foreach (var edge in built.Where(candidate =>
            candidate.Edge.Id.EndsWith("-ramp", StringComparison.Ordinal)))
        {
            foreach (var lane in edge.Section.Lanes)
            {
                var hasIncoming = connectors.Any(connector =>
                    connector.ToEdgeId == edge.Edge.Id && connector.ToLaneId == lane.Id);
                var hasOutgoing = connectors.Any(connector =>
                    connector.FromEdgeId == edge.Edge.Id && connector.FromLaneId == lane.Id);
                if (!hasIncoming || !hasOutgoing)
                {
                    throw new InvalidDataException(
                        $"Ramp edge '{edge.Edge.Id}' lane '{lane.Id}' is disconnected: " +
                        $"incoming={hasIncoming}, outgoing={hasOutgoing}.");
                }
            }
        }
    }

    private static double HorizontalDistance(RouteChunkSample left, RouteChunkSample right)
    {
        var deltaX = right.ProjectedXMeters - left.ProjectedXMeters;
        var deltaY = right.ProjectedYMeters - left.ProjectedYMeters;
        return Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
    }

    private static IEnumerable<double> Sightlines(
        IReadOnlyList<RouteChunkSample> samples,
        double lookaheadMeters)
    {
        for (var startIndex = 0; startIndex < samples.Count - 1; startIndex++)
        {
            var targetDistance = samples[startIndex].DistanceMeters + lookaheadMeters;
            var endIndex = startIndex + 1;
            while (endIndex < samples.Count &&
                samples[endIndex].DistanceMeters < targetDistance)
            {
                endIndex++;
            }
            if (endIndex >= samples.Count)
            {
                continue;
            }
            var start = samples[startIndex];
            var end = samples[endIndex];
            var routeSpan = end.DistanceMeters - start.DistanceMeters;
            var startEyeElevation = start.ElevationMeters + SightlineEyeHeightMeters;
            var targetElevation = end.ElevationMeters + SightlineTargetHeightMeters;
            var blocked = false;
            for (var index = startIndex + 1; index < endIndex; index++)
            {
                var fraction = (samples[index].DistanceMeters - start.DistanceMeters) /
                    routeSpan;
                var rayElevation = Lerp(startEyeElevation, targetElevation, fraction);
                if (samples[index].ElevationMeters + SightlineSurfaceClearanceMeters >=
                    rayElevation)
                {
                    blocked = true;
                    break;
                }
            }
            if (blocked)
            {
                continue;
            }
            var deltaX = samples[endIndex].ProjectedXMeters -
                samples[startIndex].ProjectedXMeters;
            var deltaY = samples[endIndex].ProjectedYMeters -
                samples[startIndex].ProjectedYMeters;
            yield return Math.Sqrt(deltaX * deltaX + deltaY * deltaY);
        }
    }

    private static int CountSightlineCandidates(
        IReadOnlyList<RouteChunkSample> samples,
        double lookaheadMeters) => samples.Count(sample =>
            sample.DistanceMeters + lookaheadMeters <= samples[^1].DistanceMeters);

    private static InterchangeGeometryLimits LoadGeometryLimits()
    {
        var json = Godot.FileAccess.GetFileAsString(ValidationContractPath);
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new InvalidDataException(
                $"Missing representative interchange contract '{ValidationContractPath}'.");
        }
        using var document = JsonDocument.Parse(json);
        var metrics = document.RootElement.GetProperty("required_metrics");
        return new InterchangeGeometryLimits(
            metrics.GetProperty("minimum_grade_separated_crossings").GetInt32(),
            metrics.GetProperty("minimum_vertical_clearance_meters").GetDouble(),
            metrics.GetProperty("minimum_parallel_carriageway_pairs").GetInt32(),
            metrics.GetProperty("maximum_self_intersections").GetInt32(),
            metrics.GetProperty("maximum_invalid_shortcuts").GetInt32(),
            metrics.GetProperty("maximum_absolute_grade").GetDouble(),
            metrics.GetProperty("maximum_absolute_curvature_per_meter").GetDouble(),
            metrics.GetProperty("minimum_sightline_meters").GetDouble());
    }

    private static int CountSelfIntersections(IReadOnlyList<RouteChunkSample> samples)
    {
        var segments = Segments(samples).ToArray();
        var count = 0;
        for (var first = 0; first < segments.Length; first++)
        {
            for (var second = first + 2; second < segments.Length; second++)
            {
                if (TryIntersection(segments[first], segments[second], out _, out _))
                {
                    count++;
                }
            }
        }
        return count;
    }

    private static IEnumerable<Segment> Segments(IReadOnlyList<RouteChunkSample> samples) =>
        Enumerable.Range(0, samples.Count - 1)
            .Select(index => new Segment(samples[index], samples[index + 1]));

    private static bool TryIntersection(
        Segment left,
        Segment right,
        out double leftFactor,
        out double rightFactor)
    {
        var leftX = left.End.ProjectedXMeters - left.Start.ProjectedXMeters;
        var leftY = left.End.ProjectedYMeters - left.Start.ProjectedYMeters;
        var rightX = right.End.ProjectedXMeters - right.Start.ProjectedXMeters;
        var rightY = right.End.ProjectedYMeters - right.Start.ProjectedYMeters;
        var denominator = leftX * rightY - leftY * rightX;
        if (Math.Abs(denominator) < 1e-9)
        {
            leftFactor = 0;
            rightFactor = 0;
            return false;
        }
        var deltaX = right.Start.ProjectedXMeters - left.Start.ProjectedXMeters;
        var deltaY = right.Start.ProjectedYMeters - left.Start.ProjectedYMeters;
        leftFactor = (deltaX * rightY - deltaY * rightX) / denominator;
        rightFactor = (deltaX * leftY - deltaY * leftX) / denominator;
        const double endpointTolerance = 1e-6;
        return leftFactor > endpointTolerance && leftFactor < 1 - endpointTolerance &&
            rightFactor > endpointTolerance && rightFactor < 1 - endpointTolerance;
    }

    private static bool ShareNode(RouteEdge left, RouteEdge right) =>
        left.FromNodeId == right.FromNodeId || left.FromNodeId == right.ToNodeId ||
        left.ToNodeId == right.FromNodeId || left.ToNodeId == right.ToNodeId;

    private static Point Evaluate(IReadOnlyList<Point> points, double factor)
    {
        var inverse = 1 - factor;
        return new Point(
            inverse * inverse * inverse * points[0].X +
                3 * inverse * inverse * factor * points[1].X +
                3 * inverse * factor * factor * points[2].X +
                factor * factor * factor * points[3].X,
            inverse * inverse * inverse * points[0].Y +
                3 * inverse * inverse * factor * points[1].Y +
                3 * inverse * factor * factor * points[2].Y +
                factor * factor * factor * points[3].Y,
            inverse * inverse * inverse * points[0].Elevation +
                3 * inverse * inverse * factor * points[1].Elevation +
                3 * inverse * factor * factor * points[2].Elevation +
                factor * factor * factor * points[3].Elevation);
    }

    private static RouteLane Lane(
        string id,
        int index,
        LaneManeuver maneuvers,
        RouteSemanticProvenance provenance,
        LaneRole role = LaneRole.General) =>
        new(id, index, (float)RepresentativeLaneWidthMeters, role, maneuvers, provenance);

    private static JunctionConnector Connector(
        string id,
        string junction,
        string fromEdge,
        string fromLane,
        string toEdge,
        string toLane,
        JunctionMovement movement,
        RouteSemanticProvenance provenance) =>
        new(id, junction, fromEdge, fromLane, toEdge, toLane, movement, provenance);

    private static string StableSuffix(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
            $"{value}:{AuthoredOverrideId}"))).ToLowerInvariant()[..16];

    private static double Lerp(double first, double second, double factor) =>
        first + (second - first) * factor;

    private static IReadOnlyList<Point> Bezier(
        Point start,
        Point firstControl,
        Point secondControl,
        Point end,
        int sampleCount)
    {
        if (sampleCount < 2)
        {
            throw new ArgumentOutOfRangeException(nameof(sampleCount));
        }
        var samples = new Point[sampleCount];
        for (var index = 0; index < sampleCount; index++)
        {
            var factor = index / (double)(sampleCount - 1);
            var inverse = 1 - factor;
            samples[index] = new Point(
                inverse * inverse * inverse * start.X +
                    3 * inverse * inverse * factor * firstControl.X +
                    3 * inverse * factor * factor * secondControl.X +
                    factor * factor * factor * end.X,
                inverse * inverse * inverse * start.Y +
                    3 * inverse * inverse * factor * firstControl.Y +
                    3 * inverse * factor * factor * secondControl.Y +
                    factor * factor * factor * end.Y,
                inverse * inverse * inverse * start.Elevation +
                    3 * inverse * inverse * factor * firstControl.Elevation +
                    3 * inverse * factor * factor * secondControl.Elevation +
                    factor * factor * factor * end.Elevation);
        }
        return samples;
    }

    private sealed record EdgeSpec(
        string Id,
        string FromNodeId,
        string ToNodeId,
        string RouteIdentityId,
        IReadOnlyList<Point> ControlPoints,
        IReadOnlyList<RouteLane> Lanes);

    private sealed record BuiltEdge(
        RouteEdge Edge,
        LaneSection Section,
        ChunkManifest Manifest,
        byte[] Bytes,
        IReadOnlyList<RouteChunkSample> Samples);

    private readonly record struct Point(double X, double Y, double Elevation)
    {
        public double DistanceTo(Point other) => Math.Sqrt(
            Math.Pow(other.X - X, 2) +
            Math.Pow(other.Y - Y, 2) +
            Math.Pow(other.Elevation - Elevation, 2));
    }

    private readonly record struct Segment(RouteChunkSample Start, RouteChunkSample End);
}
