using System.Buffers.Binary;
using System.Text;
using Cannonball.Content;
using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Core.Tests;

public sealed class RouteSemanticsTests
{
    [Fact]
    public void SchemaFourLoadsRouteContextAndIndependentMapGeometry()
    {
        var package = FlatBufferRouteContent.Load(CreateSchemaFourBytes());

        Assert.NotNull(package.Semantics);
        Assert.False(package.Semantics.IsLegacySynthesis);
        Assert.Equal(2, Assert.Single(package.Semantics.LaneSections).Lanes.Count);
        Assert.Equal("70", Assert.Single(package.Semantics.RouteIdentities).Number);
        Assert.Equal(["Silverthorne", "Dillon"], Assert.Single(package.Semantics.Exits).Destinations);
        Assert.Equal(205.0, Assert.Single(package.Semantics.MilepointAnchors).ValueMiles);
        Assert.Equal("205", Assert.Single(package.Semantics.RoadsideMarkers).DisplayText);
        Assert.Equal([0, 1, 2], package.Semantics.SimplifiedMapGeometry.Select(item => item.Lod));

        var edge = package.Graph.GetEdge("edge");
        Assert.Equal(["section"], edge.LaneSections.Select(section => section.Id));
        Assert.Equal(["identity"], edge.RouteIdentityIds);
        new RoutePosition("edge", 50, 1, 0, 0) { StableLaneId = "lane-1" }.Validate(edge);
    }

    [Fact]
    public void SchemaFourRejectsInvalidMapGeometryHash()
    {
        var bytes = CreateSchemaFourBytes(root =>
            root.SimplifiedMapGeometry![0].ContentHash = new string('0', 64));

        var error = Assert.Throws<InvalidDataException>(() => FlatBufferRouteContent.Load(bytes));

        Assert.Contains("map geometry 'edge' LOD 0 hash is invalid", error.Message);
    }

    [Fact]
    public void SchemaFourLoadsRootBeyondGeneratedVerifierInt16Limit()
    {
        var bytes = CreateSchemaFourBytes(root =>
            root.RouteIdentities![0].LocalName = new string('x', 40_000));

        var package = FlatBufferRouteContent.Load(bytes);

        Assert.True(bytes.Length > short.MaxValue);
        Assert.Equal(
            40_000,
            Assert.Single(package.Semantics!.RouteIdentities).LocalName.Length);
    }

    [Fact]
    public void SchemaFourRejectsInvalidLargeRootOffset()
    {
        var bytes = CreateSchemaFourBytes(root =>
            root.RouteIdentities![0].LocalName = new string('x', 40_000));
        BinaryPrimitives.WriteUInt32LittleEndian(bytes, uint.MaxValue);

        var error = Assert.Throws<InvalidDataException>(() => FlatBufferRouteContent.Load(bytes));

        Assert.Contains("valid CBRG FlatBuffer", error.Message);
    }

    [Fact]
    public void SchemaFourRejectsInvalidLargeNestedStringLength()
    {
        var largeName = new string('x', 40_000);
        var bytes = CreateSchemaFourBytes(root =>
            root.RouteIdentities![0].LocalName = largeName);
        var stringPosition = bytes.AsSpan().IndexOf(Encoding.UTF8.GetBytes(largeName));
        Assert.True(stringPosition >= sizeof(uint));
        BinaryPrimitives.WriteUInt32LittleEndian(
            bytes.AsSpan(stringPosition - sizeof(uint)),
            uint.MaxValue);

        var error = Assert.Throws<InvalidDataException>(() => FlatBufferRouteContent.Load(bytes));

        Assert.Contains("valid CBRG FlatBuffer", error.Message);
    }

    [Theory]
    [InlineData("anchor")]
    [InlineData("marker")]
    public void RouteContextIdentityMustBelongToReferencedEdge(string recordKind)
    {
        var bytes = CreateSchemaFourBytes(root =>
        {
            root.RouteIdentities!.Add(new RouteIdentityDataT
            {
                Id = "other-identity",
                System = "US",
                Number = "6",
                Shield = "us",
                SignedDirection = "east",
                LocalName = "",
                Provenance = root.RouteIdentities[0].Provenance,
            });
            if (recordKind == "anchor")
            {
                root.MilepointAnchors![0].RouteIdentityId = "other-identity";
            }
            else
            {
                root.RoadsideMarkers![0].RouteIdentityId = "other-identity";
            }
        });

        var error = Assert.Throws<InvalidDataException>(() => FlatBufferRouteContent.Load(bytes));

        Assert.Contains("invalid route placement", error.Message);
    }

    [Fact]
    public void ClosestLaneUsesLaneWidthsAndStableTieBreaking()
    {
        var section = new LaneSection(
            "section",
            "edge",
            0,
            100,
            [Lane("left", 0, Provenance()), Lane("right", 1, Provenance())],
            Shoulder(),
            Shoulder(),
            "east",
            Provenance());

        Assert.Equal("left", section.GetClosestLane(-1.8).Id);
        Assert.Equal("right", section.GetClosestLane(1.8).Id);
        Assert.Equal("left", section.GetClosestLane(0).Id);
    }

    [Fact]
    public void LaneLookupUsesValidatedBoundaryToleranceDeterministically()
    {
        var provenance = Provenance();
        var edge = EdgeWithSections(
            new LaneSection(
                "before",
                "edge",
                0,
                50,
                [Lane("before-lane", 0, provenance)],
                Shoulder(),
                Shoulder(),
                "east",
                provenance),
            new LaneSection(
                "after",
                "edge",
                50 + 5e-10,
                100,
                [Lane("after-lane", 0, provenance)],
                Shoulder(),
                Shoulder(),
                "east",
                provenance));

        Assert.Equal("after", edge.GetLaneSection(50).Id);
        Assert.Equal("after", edge.GetLaneSection(100).Id);
    }

    [Fact]
    public void RoutePositionMigrationUsesStableLaneIdentityAcrossIndexChanges()
    {
        var provenance = Provenance();
        var target = EdgeWithSections(
            new LaneSection(
                "section-a",
                "edge",
                0,
                50,
                [Lane("lane-left", 0, provenance), Lane("lane-through", 1, provenance)],
                Shoulder(),
                Shoulder(),
                "east",
                provenance),
            new LaneSection(
                "section-b",
                "edge",
                50,
                100,
                [Lane("lane-through", 0, provenance)],
                Shoulder(),
                Shoulder(),
                "east",
                provenance));
        var saved = new RoutePosition("edge", 75, 1, 0, 0) { StableLaneId = "lane-through" };

        var migrated = RoutePositionMigration.Migrate(saved, target);

        Assert.Equal(0, migrated.LaneIndex);
        Assert.Equal("lane-through", migrated.StableLaneId);
        migrated.Validate(target);
    }

    [Fact]
    public void LegacyLaneIndexMigratesDeterministicallyOrFailsActionably()
    {
        var target = EdgeWithSections(
            new LaneSection(
                "section",
                "edge",
                0,
                100,
                [Lane("lane-0", 0, Provenance())],
                Shoulder(),
                Shoulder(),
                "east",
                Provenance()));

        var migrated = RoutePositionMigration.Migrate(
            new RoutePosition("edge", 25, 0, 0, 0),
            target);
        var error = Assert.Throws<InvalidDataException>(() => RoutePositionMigration.Migrate(
            new RoutePosition("edge", 25, 1, 0, 0),
            target));

        Assert.Equal("lane-0", migrated.StableLaneId);
        Assert.Contains("Cannot migrate legacy lane index 1", error.Message);
    }

    private static byte[] CreateSchemaFourBytes(Action<RouteGraphBufferT>? mutate = null)
    {
        var semanticProvenance = SemanticProvenance();
        var points = new List<SimplifiedMapPointT>
        {
            new() { XMeters = 0, YMeters = 0, EdgeDistanceMeters = 0 },
            new() { XMeters = 100, YMeters = 0, EdgeDistanceMeters = 100 },
        };
        var corePoints = points.Select(point => new Cannonball.Core.Routes.SimplifiedMapPoint(
            point.XMeters,
            point.YMeters,
            point.EdgeDistanceMeters)).ToArray();
        var root = new RouteGraphBufferT
        {
            SchemaVersion = 4,
            ContentVersion = "route-v4-semantic-fixture",
            Nodes =
            [
                new RouteNodeDataT { Id = "west", Kind = "junction", OutgoingEdgeIds = ["edge"] },
                new RouteNodeDataT { Id = "east", Kind = "route", OutgoingEdgeIds = [] },
            ],
            Edges =
            [
                new RouteEdgeDataT
                {
                    Id = "edge",
                    FromNodeId = "west",
                    ToNodeId = "east",
                    LengthMeters = 100,
                    LaneCount = 2,
                    SpeedLimitMps = 31.2928f,
                    RegionId = "fixture",
                    GenerationProfile = "graybox",
                    ChunkIds = ["chunk"],
                    Samples = [],
                    LaneSectionIds = ["section"],
                    RouteIdentityIds = ["identity"],
                },
            ],
            Chunks =
            [
                new ChunkManifestDataT
                {
                    Id = "chunk",
                    EdgeId = "edge",
                    StartMeters = 0,
                    EndMeters = 100,
                    ContentHash = new string('c', 64),
                    RelativePath = "chunks/chunk.cbck",
                    ProbableBranchChunkIds = [],
                    ByteCount = 128,
                },
            ],
            Provenance = new SourceProvenanceDataT
            {
                SourceId = "semantic-fixture",
                Publisher = "Test Federal Agency",
                SourceUrl = "https://example.gov/route",
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
                ElevationProductId = "fixture",
                ElevationProductTitle = "Fixture elevation",
                ElevationProductResolution = "fixture",
                ElevationArtifactSha256 = new string('d', 64),
            },
            LaneSections =
            [
                new LaneSectionDataT
                {
                    Id = "section",
                    EdgeId = "edge",
                    StartMeters = 0,
                    EndMeters = 100,
                    Lanes =
                    [
                        SemanticLane("lane-0", 0, semanticProvenance),
                        SemanticLane("lane-1", 1, semanticProvenance),
                    ],
                    LeftShoulder = new RouteShoulderDataT { WidthMeters = 1.5f, Kind = "paved" },
                    RightShoulder = new RouteShoulderDataT { WidthMeters = 3.0f, Kind = "paved" },
                    SignedDirection = "east",
                    Provenance = semanticProvenance,
                },
            ],
            JunctionConnectors = [],
            RouteIdentities =
            [
                new RouteIdentityDataT
                {
                    Id = "identity",
                    System = "I",
                    Number = "70",
                    Shield = "interstate",
                    SignedDirection = "east",
                    LocalName = "Veterans Memorial Highway",
                    Provenance = semanticProvenance,
                },
            ],
            Exits =
            [
                new ExitDataT
                {
                    Id = "exit-205",
                    JunctionNodeId = "west",
                    RampEdgeId = "edge",
                    RouteIdentityId = "identity",
                    Number = "205",
                    Suffix = "",
                    Destinations = ["Silverthorne", "Dillon"],
                    Services = ["fuel", "food"],
                    Provenance = semanticProvenance,
                },
            ],
            MilepointAnchors =
            [
                new MilepointAnchorDataT
                {
                    Id = "mile-205",
                    RouteIdentityId = "identity",
                    EdgeId = "edge",
                    DistanceMeters = 25,
                    ValueMiles = 205,
                    Jurisdiction = "CO",
                    SignedDirection = "east",
                    Provenance = semanticProvenance,
                },
            ],
            RoadsideMarkers =
            [
                new RoadsideMarkerDataT
                {
                    Id = "marker-205",
                    Kind = "mile",
                    RouteIdentityId = "identity",
                    EdgeId = "edge",
                    DistanceMeters = 25,
                    DisplayText = "205",
                    Provenance = semanticProvenance,
                },
            ],
            SimplifiedMapGeometry = Enumerable.Range(0, 3)
                .Select(lod => new SimplifiedMapGeometryDataT
                {
                    EdgeId = "edge",
                    Lod = checked((uint)lod),
                    Points = points,
                    ContentHash = RouteSemanticsCompatibility.ComputeMapGeometryHash(
                        "edge",
                        lod,
                        corePoints),
                })
                .ToList(),
        };
        mutate?.Invoke(root);
        var builder = new FlatBufferBuilder(16_384);
        var offset = RouteGraphBuffer.Pack(builder, root);
        RouteGraphBuffer.FinishRouteGraphBufferBuffer(builder, offset);
        return builder.SizedByteArray();
    }

    private static SemanticProvenanceDataT SemanticProvenance() => new()
    {
        Kind = "derived",
        SourceId = "semantic-fixture",
        SourceRecordId = "edge",
        ArtifactSha256 = new string('a', 64),
        Derivation = "Deterministic test fixture.",
        AuthoredOverrideId = "",
    };

    private static RouteLaneDataT SemanticLane(
        string id,
        uint index,
        SemanticProvenanceDataT provenance) => new()
    {
        Id = id,
        Index = index,
        WidthMeters = 3.6f,
        Role = "general",
        AllowedManeuvers = (uint)LaneManeuver.Continue,
        Provenance = provenance,
    };

    private static RouteSemanticProvenance Provenance() => new(
        SemanticProvenanceKind.Derived,
        "fixture",
        "edge",
        new string('a', 64),
        "Deterministic test fixture.",
        string.Empty);

    private static RouteLane Lane(
        string id,
        int index,
        RouteSemanticProvenance provenance) => new(
        id,
        index,
        3.6f,
        LaneRole.General,
        LaneManeuver.Continue,
        provenance);

    private static RouteShoulder Shoulder() => new(1.5f, "paved");

    private static RouteEdge EdgeWithSections(params LaneSection[] sections) => new(
        "edge",
        "west",
        "east",
        100,
        sections.Max(section => section.Lanes.Count),
        31.2928,
        [],
        [],
        "fixture",
        "graybox",
        [])
    {
        LaneSections = sections,
    };
}
