using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Simulation;

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
            [
                Geometry("approach", 0, 100, 0),
                Geometry("through", 100, 200, 0),
                Geometry("ramp", 100, 170, -50),
                Geometry("transfer", 100, 170, 50),
            ],
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

    private static SimplifiedMapGeometry Geometry(
        string edgeId,
        double startX,
        double endX,
        double endY) =>
        new(
            edgeId,
            0,
            [
                new SimplifiedMapPoint(startX, 0, 0),
                new SimplifiedMapPoint(endX, endY, 100),
            ],
            "fixture");
}
