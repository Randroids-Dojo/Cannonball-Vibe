using Cannonball.Content;
using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Core.Tests;

public sealed class FlatBufferRouteContentTests
{
    [Fact]
    public void RuntimePackageLoadsIntoPortableRouteGraph()
    {
        var source = new SourceCoordinateT
        {
            Longitude = -100,
            Latitude = 40,
            ElevationMeters = 300,
        };
        var graphData = new RouteGraphBufferT
        {
            SchemaVersion = 1,
            ContentVersion = "fixture-v1",
            Nodes =
            [
                new RouteNodeDataT
                {
                    Id = "west",
                    Source = source,
                    Kind = "origin",
                    OutgoingEdgeIds = ["edge-1"],
                },
                new RouteNodeDataT
                {
                    Id = "east",
                    Source = source,
                    Kind = "finish",
                    OutgoingEdgeIds = [],
                },
            ],
            Edges =
            [
                new RouteEdgeDataT
                {
                    Id = "edge-1",
                    FromNodeId = "west",
                    ToNodeId = "east",
                    LengthMeters = 2_000,
                    LaneCount = 3,
                    SpeedLimitMps = 31.2928f,
                    RegionId = "fixture",
                    GenerationProfile = "graybox",
                    ChunkIds = ["chunk-1"],
                    Samples = [new RouteSampleT { DistanceMeters = 0 }],
                },
            ],
            Chunks =
            [
                new ChunkManifestDataT
                {
                    Id = "chunk-1",
                    EdgeId = "edge-1",
                    StartMeters = 0,
                    EndMeters = 2_000,
                    ContentHash = new string('a', 64),
                    RelativePath = "chunks/chunk-1.chunk",
                    ProbableBranchChunkIds = [],
                },
            ],
        };
        var builder = new FlatBufferBuilder(4_096);
        var root = RouteGraphBuffer.Pack(builder, graphData);
        RouteGraphBuffer.FinishRouteGraphBufferBuffer(builder, root);

        var package = FlatBufferRouteContent.Load(builder.SizedByteArray());

        Assert.Equal("fixture-v1", package.Graph.ContentVersion);
        Assert.Equal(2_000, package.Graph.GetEdge("edge-1").LengthMeters);
        Assert.Equal("chunk-1", Assert.Single(package.Chunks).Key);
        Assert.Equal(
            1_750,
            package.Graph.GetRemainingDistance(
                new RoutePosition("edge-1", 250, 1, 0, 0),
                ["edge-1"]));
    }
}
