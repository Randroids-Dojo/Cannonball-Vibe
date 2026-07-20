using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Simulation;
using System.Diagnostics;

namespace Cannonball.Core.Tests;

public sealed class TripMapProjectionTests
{
    [Fact]
    public void Projects_authoritative_progress_and_clips_paths_at_current_position()
    {
        var package = CreatePackage();

        var state = TripMapProjector.Project(
            package,
            "through",
            25,
            ["approach", "through"],
            AssistProfile.Balanced,
            25);

        Assert.Equal(125, state.DistanceCompletedMeters);
        Assert.Equal(75, state.DistanceRemainingMeters);
        Assert.InRange(state.EstimatedRemainingSeconds, 2.8, 2.9);
        Assert.Equal(new TripMapPoint(125, 0), state.Current);
        Assert.Equal(2, state.Traveled.Count);
        Assert.Single(state.Planned);
        Assert.Equal(new TripMapPoint(125, 0), state.Planned[0].Points[0]);
        Assert.Equal(new TripMapPoint(200, 0), state.Destination);
        Assert.Equal("US 36 east", state.StartLabel);
    }

    [Fact]
    public void Exposes_stable_alternatives_exits_services_and_transfers()
    {
        var package = CreatePackage();

        var state = TripMapProjector.Project(
            package,
            "approach",
            20,
            ["approach", "through"],
            AssistProfile.Accessible,
            0);

        Assert.Equal(2, state.Alternatives.Count);
        var alternative = Assert.Single(state.Alternatives, candidate =>
            candidate.ConnectorId == "connector-exit");
        Assert.Equal("connector-exit", alternative.ConnectorId);
        Assert.Contains("Exit 42A", alternative.Label);
        var exit = Assert.Single(state.UpcomingFeatures, feature =>
            feature.Kind == TripMapFeatureKind.Exit);
        Assert.Equal("Boulder Junction / Nederland", exit.Detail);
        Assert.Equal(["fuel", "food"], exit.Services);
        Assert.Single(state.SelectedServiceStops);
        Assert.Contains(state.UpcomingFeatures, feature =>
            feature.Kind == TripMapFeatureKind.HighwayTransfer);
    }

    [Fact]
    public void Rejects_chunk_only_content_without_immutable_map_geometry()
    {
        var package = CreatePackage() with
        {
            Semantics = CreatePackage().Semantics! with { SimplifiedMapGeometry = [] },
        };

        var error = Assert.Throws<InvalidDataException>(() => TripMapProjector.Project(
            package,
            "approach",
            0,
            ["approach", "through"],
            AssistProfile.Balanced,
            0));

        Assert.Contains("simplified immutable map geometry", error.Message);
    }

    [Fact]
    public void Compression_modes_change_only_estimates_and_preserve_authoritative_progress()
    {
        var package = CreatePackage();
        var realTime = TripMapProjector.Project(
            package,
            "approach",
            25,
            ["approach", "through"],
            AssistProfile.Balanced,
            0,
            TripMapProjectionOptions.Default);
        var fixedCompression = TripMapProjector.Project(
            package,
            "approach",
            25,
            ["approach", "through"],
            AssistProfile.Balanced,
            0,
            new TripMapProjectionOptions(null, 20_000, TripMapTravelMode.FixedRatio(3)));
        var selectiveCruise = TripMapProjector.Project(
            package,
            "approach",
            25,
            ["approach", "through"],
            AssistProfile.Balanced,
            0,
            new TripMapProjectionOptions(null, 20_000, TripMapTravelMode.SelectiveCruise(2.5)));

        Assert.Equal(realTime.DistanceCompletedMeters, fixedCompression.DistanceCompletedMeters);
        Assert.Equal(realTime.DistanceRemainingMeters, fixedCompression.DistanceRemainingMeters);
        Assert.Equal(realTime.Current, fixedCompression.Current);
        Assert.Equal(realTime.EstimatedRemainingSeconds / 3,
            fixedCompression.EstimatedRemainingSeconds, 9);
        Assert.Equal(realTime.EstimatedRemainingSeconds / 2.5,
            selectiveCruise.EstimatedRemainingSeconds, 9);
        Assert.Equal("fixed-3x", fixedCompression.TravelMode.Id);
        Assert.Equal(TripMapCompressionKind.SelectiveCruise,
            selectiveCruise.TravelMode.CompressionKind);
    }

    [Fact]
    public void Continental_projection_selects_a_bounded_lod_and_avoids_global_rescans()
    {
        const int edgeCount = 3_000;
        var package = CreateContinentalPackage(edgeCount);
        var routePlan = Enumerable.Range(0, edgeCount)
            .Select(index => $"edge-{index:D4}")
            .ToArray();
        var stopwatch = Stopwatch.StartNew();

        var state = TripMapProjector.Project(
            package,
            routePlan[edgeCount / 2],
            804.672,
            routePlan,
            AssistProfile.Balanced,
            30,
            new TripMapProjectionOptions(
                null,
                TripMapProjectionOptions.DefaultPointBudget,
                TripMapTravelMode.SelectiveCruise(3)));

        stopwatch.Stop();
        Assert.Equal(1, state.GeometryLod);
        Assert.InRange(state.ProjectedPointCount, 1, TripMapProjectionOptions.DefaultPointBudget);
        Assert.InRange(state.DistanceCompletedMeters / 1609.344, 1500.49, 1500.51);
        Assert.InRange(state.DistanceRemainingMeters / 1609.344, 1499.49, 1499.51);
        Assert.Equal("selective-3x", state.TravelMode.Id);
        Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(2),
            $"Continental projection took {stopwatch.Elapsed.TotalMilliseconds:0.0} ms.");
    }

    private static RouteContentPackage CreatePackage()
    {
        var approach = Edge("approach", "start", "junction", ["route-main"]);
        var through = Edge("through", "junction", "destination", ["route-main"]);
        var ramp = Edge("ramp", "junction", "ramp-end", ["route-state"]);
        var transfer = Edge("transfer", "junction", "transfer-end", ["route-interstate"]);
        var graph = new InMemoryRouteGraph(
            "trip-map-test",
            [
                new RouteNode("start", default, "route", [approach.Id]),
                new RouteNode("junction", default, "interchange", [through.Id, ramp.Id, transfer.Id]),
                new RouteNode("destination", default, "route", []),
                new RouteNode("ramp-end", default, "route", []),
                new RouteNode("transfer-end", default, "route", []),
            ],
            [approach, through, ramp, transfer]);
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            "fixture",
            "fixture",
            new string('a', 64),
            "test",
            "trip-map-test");
        var semantics = new RouteSemanticContent(
            [],
            [
                new JunctionConnector(
                    "connector-through", "junction", "approach", "lane-a", "through", "lane-b",
                    JunctionMovement.Continuation, provenance),
                new JunctionConnector(
                    "connector-exit", "junction", "approach", "lane-a", "ramp", "lane-ramp",
                    JunctionMovement.Exit, provenance),
                new JunctionConnector(
                    "connector-transfer", "junction", "approach", "lane-a", "transfer", "lane-transfer",
                    JunctionMovement.HighwayTransfer, provenance),
            ],
            [
                new RouteIdentity("route-main", "US", "36", "us", "east", "", provenance),
                new RouteIdentity("route-state", "CO", "93", "state", "north", "", provenance),
                new RouteIdentity("route-interstate", "I", "70", "interstate", "west", "", provenance),
            ],
            [
                new RouteExit(
                    "exit-42a", "junction", "ramp", "route-main", "42", "A",
                    ["Boulder Junction", "Nederland"], ["fuel", "food"], provenance),
            ],
            [],
            [],
            GeometryLods("approach", 0, 100, 0)
                .Concat(GeometryLods("through", 100, 200, 0))
                .Concat(GeometryLods("ramp", 100, 170, -50))
                .Concat(GeometryLods("transfer", 100, 170, 50))
                .ToArray(),
            false);
        return new RouteContentPackage(graph, new Dictionary<string, ChunkManifest>(), Semantics: semantics);
    }

    private static RouteEdge Edge(
        string id,
        string from,
        string to,
        IReadOnlyList<string> identities) =>
        new(id, from, to, 100, 2, 30, [], [], "test", "test", [])
        {
            RouteIdentityIds = identities,
        };

    private static IReadOnlyList<SimplifiedMapGeometry> GeometryLods(
        string edgeId,
        double startX,
        double endX,
        double endY) =>
        [
            Geometry(edgeId, 0, startX, endX, 0, endY, 5, 100),
            Geometry(edgeId, 1, startX, endX, 0, endY, 3, 100),
            Geometry(edgeId, 2, startX, endX, 0, endY, 2, 100),
        ];

    private static SimplifiedMapGeometry Geometry(
        string edgeId,
        int lod,
        double startX,
        double endX,
        double startY,
        double endY,
        int pointCount,
        double lengthMeters)
    {
        var points = Enumerable.Range(0, pointCount)
            .Select(index =>
            {
                var fraction = index / (double)(pointCount - 1);
                return new SimplifiedMapPoint(
                    startX + ((endX - startX) * fraction),
                    startY + ((endY - startY) * fraction),
                    lengthMeters * fraction);
            })
            .ToArray();
        return new SimplifiedMapGeometry(edgeId, lod, points, "fixture");
    }

    private static RouteContentPackage CreateContinentalPackage(int edgeCount)
    {
        const double edgeLength = 1609.344;
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            "fixture",
            "continental-scale",
            new string('b', 64),
            "Deterministic scale fixture; not asserted as observed geography.",
            "p0-013-scale-v1");
        var identity = new RouteIdentity(
            "route-scale", "TEST", "3000", "automation", "east", "", provenance);
        var edges = new RouteEdge[edgeCount];
        var connectors = new JunctionConnector[Math.Max(0, edgeCount - 1)];
        var geometry = new List<SimplifiedMapGeometry>(edgeCount * 3);
        for (var index = 0; index < edgeCount; index++)
        {
            var edgeId = $"edge-{index:D4}";
            edges[index] = new RouteEdge(
                edgeId,
                $"node-{index:D4}",
                $"node-{index + 1:D4}",
                edgeLength,
                2,
                33.528,
                [],
                [],
                "test",
                "scale",
                [])
            {
                RouteIdentityIds = [identity.Id],
            };
            var startX = index * edgeLength;
            var startY = 40 * Math.Sin(index / 20.0);
            var endY = 40 * Math.Sin((index + 1) / 20.0);
            geometry.Add(Geometry(
                edgeId, 0, startX, startX + edgeLength, startY, endY, 17, edgeLength));
            geometry.Add(Geometry(
                edgeId, 1, startX, startX + edgeLength, startY, endY, 5, edgeLength));
            geometry.Add(Geometry(
                edgeId, 2, startX, startX + edgeLength, startY, endY, 2, edgeLength));
            if (index > 0)
            {
                var previousEdgeId = $"edge-{index - 1:D4}";
                connectors[index - 1] = new JunctionConnector(
                    $"connector-{index - 1:D4}",
                    $"node-{index:D4}",
                    previousEdgeId,
                    $"{previousEdgeId}:lane:0",
                    edgeId,
                    $"{edgeId}:lane:0",
                    JunctionMovement.Continuation,
                    provenance);
            }
        }
        var nodes = Enumerable.Range(0, edgeCount + 1)
            .Select(index => new RouteNode(
                $"node-{index:D4}",
                default,
                index is 0 || index == edgeCount ? "route-end" : "route",
                index == edgeCount ? [] : [$"edge-{index:D4}"]))
            .ToArray();
        var semantics = new RouteSemanticContent(
            [], connectors, [identity], [], [], [], geometry, false);
        return new RouteContentPackage(
            new InMemoryRouteGraph("trip-map-continental-scale", nodes, edges),
            new Dictionary<string, ChunkManifest>(),
            Semantics: semantics);
    }
}
