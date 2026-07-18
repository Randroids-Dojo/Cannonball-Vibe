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
                    Samples = [new RouteSampleT { DistanceMeters = 0, ElevationMeters = 321 }],
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
        Assert.Equal(321, Assert.Single(package.Graph.GetEdge("edge-1").ElevationSamples));
        Assert.Equal("chunk-1", Assert.Single(package.Chunks).Key);
        Assert.NotNull(package.Semantics);
        Assert.True(package.Semantics.IsLegacySynthesis);
        Assert.Equal("legacy:edge-1:lane:1", package.Graph.GetEdge("edge-1").LaneSections[0].Lanes[1].Id);
        Assert.Equal(
            1_750,
            package.Graph.GetRemainingDistance(
                new RoutePosition("edge-1", 250, 1, 0, 0),
                ["edge-1"]));
    }

    [Fact]
    public void SchemaTwoPreservesElevationAndProvenanceMetadata()
    {
        var graphData = new RouteGraphBufferT
        {
            SchemaVersion = 2,
            ContentVersion = "official-fixture-v2",
            Nodes =
            [
                new RouteNodeDataT { Id = "west", Kind = "route", OutgoingEdgeIds = ["edge"] },
                new RouteNodeDataT { Id = "east", Kind = "route", OutgoingEdgeIds = [] },
            ],
            Edges =
            [
                new RouteEdgeDataT
                {
                    Id = "edge",
                    FromNodeId = "west",
                    ToNodeId = "east",
                    LengthMeters = 25,
                    LaneCount = 2,
                    Samples =
                    [
                        new RouteSampleT
                        {
                            DistanceMeters = 25,
                            ElevationMeters = 1_602.5f,
                            Grade = 0.03125f,
                        },
                    ],
                },
            ],
            Chunks = [],
            Provenance = new SourceProvenanceDataT
            {
                SourceId = "usdot-national-highway-planning-network",
                Publisher = "U.S. Department of Transportation",
                SourceUrl = "https://services.arcgis.com/example",
                ArtifactSha256 = new string('a', 64),
                AcquisitionLockSha256 = new string('b', 64),
            },
            SpatialReference = new SpatialReferenceDataT
            {
                RouteCrs = "EPSG:5070",
                ElevationCrs = "EPSG:4269",
                HorizontalDatum = "North American Datum of 1983",
                VerticalDatum = "North American Vertical Datum of 1988",
                ElevationUnits = "meters",
                ElevationProductId = "620de4b0d34e6c7e83ba9fde",
                ElevationProductTitle = "USGS 1/3 Arc Second n40w106 20220216",
                ElevationProductResolution = "1/3 arc-second",
                ElevationArtifactSha256 = new string('c', 64),
            },
        };
        var builder = new FlatBufferBuilder(4_096);
        var root = RouteGraphBuffer.Pack(builder, graphData);
        RouteGraphBuffer.FinishRouteGraphBufferBuffer(builder, root);

        var package = FlatBufferRouteContent.Load(builder.SizedByteArray());

        Assert.NotNull(package.Metadata);
        Assert.Equal("EPSG:5070", package.Metadata.RouteCrs);
        Assert.Equal("North American Vertical Datum of 1988", package.Metadata.VerticalDatum);
        Assert.Equal("620de4b0d34e6c7e83ba9fde", package.Metadata.ElevationProductId);
        Assert.Equal(new string('b', 64), package.Metadata.AcquisitionLockSha256);
        var edge = package.Graph.GetEdge("edge");
        Assert.Equal(1_602.5f, Assert.Single(edge.ElevationSamples));
        Assert.Equal(0.03125f, Assert.Single(edge.GradeSamples));
        Assert.Equal(25, Assert.Single(edge.SampleDistancesMeters));
    }
}
