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
