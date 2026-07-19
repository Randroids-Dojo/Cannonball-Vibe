using Cannonball.Core.Routes;

namespace Cannonball.Core.Tests;

public sealed class RouteGraphTests
{
    [Fact]
    public void RemainingDistanceUsesAuthoritativeEdgeDistance()
    {
        var graph = CreateGraph();
        var position = new RoutePosition("edge-west", 250, 1, 0, 0);

        var remaining = graph.GetRemainingDistance(position, ["edge-west", "edge-east"]);

        Assert.Equal(2_750, remaining);
    }

    [Fact]
    public void InvalidLaneIsRejected()
    {
        var edge = CreateGraph().GetEdge("edge-west");
        var position = new RoutePosition(edge.Id, 10, edge.LaneCount, 0, 0);

        Assert.Throws<ArgumentOutOfRangeException>(() => position.Validate(edge));
    }

    [Fact]
    public void DividedCarriagewaysRequireAReciprocalOpposingPair()
    {
        var eastbound = Edge("eastbound", "west-a", "east-a") with
        {
            RoadwayKind = RoadwayKind.DividedCarriageway,
            CarriagewayGroupId = "i70-pair",
            OpposingEdgeId = "westbound",
        };
        var westbound = Edge("westbound", "east-b", "west-b") with
        {
            RoadwayKind = RoadwayKind.DividedCarriageway,
            CarriagewayGroupId = "i70-pair",
            OpposingEdgeId = "eastbound",
        };
        var nodes = new[]
        {
            Node("west-a", eastbound.Id), Node("east-a"),
            Node("east-b", westbound.Id), Node("west-b"),
        };

        var graph = new InMemoryRouteGraph("paired", nodes, [eastbound, westbound]);
        var invalid = westbound with { OpposingEdgeId = "missing" };

        Assert.Equal("westbound", graph.GetEdge("eastbound").OpposingEdgeId);
        Assert.Equal("westbound", graph.GetOpposingEdge("eastbound")?.Id);
        var error = Assert.Throws<ArgumentException>(() =>
            new InMemoryRouteGraph("invalid", nodes, [eastbound, invalid]));
        Assert.Contains("reciprocal pair", error.Message);
    }

    [Fact]
    public void OneWayRampCannotMasqueradeAsAnOpposingCarriageway()
    {
        var ramp = Edge("ramp", "start", "end") with
        {
            RoadwayKind = RoadwayKind.OneWayRamp,
            OpposingEdgeId = "other",
        };

        var error = Assert.Throws<ArgumentException>(() => new InMemoryRouteGraph(
            "invalid",
            [Node("start", ramp.Id), Node("end")],
            [ramp]));

        Assert.Contains("cannot declare carriageway pairing", error.Message);
    }

    private static RouteNode Node(string id, params string[] outgoing) =>
        new(id, default, "route", outgoing);

    private static RouteEdge Edge(string id, string from, string to) => new(
        id, from, to, 100, 2, 30, [], [], "test", "graybox", []);

    private static InMemoryRouteGraph CreateGraph()
    {
        var source = new SourceCoordinate(-100, 40, 300);
        var nodes = new[]
        {
            new RouteNode("west", source, "origin", ["edge-west"]),
            new RouteNode("middle", source, "interchange", ["edge-east"]),
            new RouteNode("east", source, "finish", []),
        };
        var edges = new[]
        {
            new RouteEdge("edge-west", "west", "middle", 1_000, 3, 31, [], [], "test", "graybox", ["chunk-0"]),
            new RouteEdge("edge-east", "middle", "east", 2_000, 3, 31, [], [], "test", "graybox", ["chunk-1"]),
        };
        return new InMemoryRouteGraph("test-v1", nodes, edges);
    }
}

public sealed class LinearRoutePlanTests
{
    [Fact]
    public void Orders_connected_edges_and_maps_global_distance_to_edge_spans()
    {
        var first = Edge("first", "start", "middle", 100);
        var second = Edge("second", "middle", "end", 250);
        var graph = new InMemoryRouteGraph(
            "route-test",
            [
                new RouteNode("start", default, "route", [first.Id]),
                new RouteNode("middle", default, "route", [second.Id]),
                new RouteNode("end", default, "route", []),
            ],
            [second, first]);

        var plan = LinearRoutePlan.Build(graph, [second.Id, first.Id]);

        Assert.Equal([first.Id, second.Id], plan.EdgeIds);
        Assert.Equal(350, plan.TotalLengthMeters);
        Assert.Equal(first.Id, plan.GetEdgeAtDistance(99.9).EdgeId);
        Assert.Equal(second.Id, plan.GetEdgeAtDistance(100).EdgeId);
        Assert.Equal(100, plan.GetEdge(second.Id).StartMeters);
        Assert.Equal(350, plan.GetEdge(second.Id).EndMeters);
    }

    [Fact]
    public void Rejects_a_selected_branch_instead_of_guessing_a_path()
    {
        var first = Edge("first", "start", "junction", 100);
        var left = Edge("left", "junction", "left-end", 100);
        var right = Edge("right", "junction", "right-end", 100);
        var graph = new InMemoryRouteGraph(
            "route-test",
            [
                new RouteNode("start", default, "route", [first.Id]),
                new RouteNode("junction", default, "junction", [left.Id, right.Id]),
                new RouteNode("left-end", default, "route", []),
                new RouteNode("right-end", default, "route", []),
            ],
            [first, left, right]);

        var error = Assert.Throws<InvalidDataException>(
            () => LinearRoutePlan.Build(graph, [first.Id, left.Id, right.Id]));

        Assert.Contains("single directed corridor", error.Message);
    }

    private static RouteEdge Edge(string id, string from, string to, double length) => new(
        id,
        from,
        to,
        length,
        2,
        30,
        [],
        [],
        "test",
        "test",
        []);
}

public sealed class RouteChoiceCatalogTests
{
    [Fact]
    public void ExposesStableManeuverRouteAndDestinationMetadata()
    {
        var fixture = CreateFixture();
        var catalog = new RouteChoiceCatalog(fixture.Graph, fixture.Semantics);

        var choices = catalog.GetChoices("approach");

        Assert.Equal(2, choices.Count);
        var exit = Assert.Single(choices, choice => choice.Movement == JunctionMovement.Exit);
        Assert.Equal("connector-exit", exit.ConnectorId);
        Assert.Equal("42A", exit.ExitNumber);
        Assert.Equal(["Boulder Junction", "Nederland"], exit.Destinations);
        Assert.Equal(["route-crossroad"], exit.RouteIdentityIds);
    }

    [Fact]
    public void ValidatesExplicitLaneConnectorChainWithoutGuessingAtBranch()
    {
        var fixture = CreateFixture();
        var catalog = new RouteChoiceCatalog(fixture.Graph, fixture.Semantics);
        var selection = new RoutePlanSelection(
            "take-exit",
            ["approach", "exit-ramp"],
            ["connector-exit"],
            "approach-exit");

        var plan = catalog.ValidatePlan(selection);

        Assert.Equal(selection.EdgeIds, plan.LinearPlan.EdgeIds);
        Assert.Equal("ramp-lane", plan.EndLaneId);
        Assert.Equal(JunctionMovement.Exit, Assert.Single(plan.Transitions).Movement);
    }

    [Fact]
    public void RejectsConnectorThatDoesNotContinueSelectedLane()
    {
        var fixture = CreateFixture();
        var catalog = new RouteChoiceCatalog(fixture.Graph, fixture.Semantics);
        var selection = new RoutePlanSelection(
            "invalid",
            ["approach", "through"],
            ["connector-through"],
            "approach-exit");

        var error = Assert.Throws<InvalidDataException>(() => catalog.ValidatePlan(selection));

        Assert.Contains("does not continue", error.Message);
    }

    private static (InMemoryRouteGraph Graph, RouteSemanticContent Semantics) CreateFixture()
    {
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            "fixture",
            "fixture",
            new string('a', 64),
            "test",
            "route-choice-test");
        RouteLane Lane(string id, int index, LaneManeuver maneuvers) =>
            new(id, index, 3.6f, LaneRole.General, maneuvers, provenance);
        RouteEdge Edge(
            string id,
            string from,
            string to,
            IReadOnlyList<RouteLane> lanes,
            params string[] identities) =>
            new RouteEdge(id, from, to, 100, lanes.Count, 30, [], [], "test", "test", [])
            {
                LaneSections =
                [
                    new LaneSection(
                        $"{id}-section",
                        id,
                        0,
                        100,
                        lanes,
                        new RouteShoulder(1, "paved"),
                        new RouteShoulder(1, "paved"),
                        "east",
                        provenance),
                ],
                RouteIdentityIds = identities,
            };
        var approach = Edge(
            "approach",
            "start",
            "junction",
            [
                Lane("approach-through", 0, LaneManeuver.Continue),
                Lane("approach-exit", 1, LaneManeuver.Exit),
            ],
            "route-main");
        var through = Edge(
            "through",
            "junction",
            "through-end",
            [Lane("through-lane", 0, LaneManeuver.Continue)],
            "route-main");
        var ramp = Edge(
            "exit-ramp",
            "junction",
            "ramp-end",
            [Lane("ramp-lane", 0, LaneManeuver.Continue)],
            "route-crossroad");
        var graph = new InMemoryRouteGraph(
            "route-choice-test",
            [
                new RouteNode("start", default, "route", [approach.Id]),
                new RouteNode("junction", default, "interchange", [through.Id, ramp.Id]),
                new RouteNode("through-end", default, "route", []),
                new RouteNode("ramp-end", default, "route", []),
            ],
            [approach, through, ramp]);
        var identities = new[]
        {
            new RouteIdentity("route-main", "US", "36", "us", "east", "", provenance),
            new RouteIdentity("route-crossroad", "CO", "93", "state", "north", "", provenance),
        };
        var connectors = new[]
        {
            new JunctionConnector(
                "connector-through",
                "junction",
                approach.Id,
                "approach-through",
                through.Id,
                "through-lane",
                JunctionMovement.Continuation,
                provenance),
            new JunctionConnector(
                "connector-exit",
                "junction",
                approach.Id,
                "approach-exit",
                ramp.Id,
                "ramp-lane",
                JunctionMovement.Exit,
                provenance),
        };
        var exit = new RouteExit(
            "exit-42a",
            "junction",
            ramp.Id,
            "route-main",
            "42",
            "A",
            ["Boulder Junction", "Nederland"],
            ["fuel"],
            provenance);
        var semantics = new RouteSemanticContent(
            [.. approach.LaneSections, .. through.LaneSections, .. ramp.LaneSections],
            connectors,
            identities,
            [exit],
            [],
            [],
            [],
            false);
        return (graph, semantics);
    }
}
