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
