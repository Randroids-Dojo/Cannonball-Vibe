using Cannonball.Core.Routes;

namespace Cannonball.Core.Tests;

public sealed class RouteContextPlannerTests
{
    private static readonly RouteSemanticProvenance Provenance = new(
        SemanticProvenanceKind.AuthoredOverride,
        "route-context-fixture",
        "record-1",
        new string('a', 64),
        "Deterministic route-context test fixture.",
        "p1-007-test");

    [Fact]
    public void ExactConcurrentMileMarkersKeepRouteIdentityDirectionAndMilepoint()
    {
        var fixture = CreateFixture();

        var plan = RouteContextPlanner.BuildForEdge(fixture.Graph, fixture.Semantics, "approach");

        var markers = plan.Placements
            .Where(placement => placement.Kind == RouteContextPlacementKind.MileMarker)
            .ToArray();
        Assert.Equal(2, markers.Length);
        Assert.Equal(["US 287 EAST", "US 36 EAST"], markers.Select(item => item.PrimaryText));
        Assert.All(markers, marker => Assert.Equal("MILE 42", marker.SecondaryText));
        Assert.All(markers, marker => Assert.Equal("CO", marker.Jurisdiction));
        Assert.All(markers, marker => Assert.True(marker.ExactRouteReference));
        Assert.Equal(
            [RouteContextMount.RightRoadside, RouteContextMount.LeftRoadside],
            markers.Select(marker => marker.Mount));
        Assert.DoesNotContain("1.25", string.Join(' ', markers.Select(item => item.SecondaryText)));
    }

    [Theory]
    [InlineData(18.0, "18")]
    [InlineData(18.713, "18.7")]
    [InlineData(18.75, "18.8")]
    public void MileMarkerDisplayUsesRoadSignPrecision(double valueMiles, string expected)
    {
        Assert.Equal(expected, RouteContextPlanner.FormatMilepoint(valueMiles));
    }

    [Fact]
    public void JurisdictionResetRemainsIndependentFromPreviousEdgeAndTripProgress()
    {
        var fixture = CreateFixture();

        var reset = RouteContextPlanner.BuildForEdge(fixture.Graph, fixture.Semantics, "receiving");

        var marker = Assert.Single(reset.Placements, placement =>
            placement.Kind == RouteContextPlacementKind.MileMarker);
        Assert.Equal("I 25 SOUTH", marker.PrimaryText);
        Assert.Equal("MILE 214", marker.SecondaryText);
        Assert.Equal("CO-I25", marker.Jurisdiction);
        Assert.Equal(25, marker.DistanceMeters);
    }

    [Fact]
    public void MissingOrContradictoryExactDataFailsClosed()
    {
        var fixture = CreateFixture();
        var missing = fixture.Semantics with
        {
            MilepointAnchors = fixture.Semantics.MilepointAnchors.Where(anchor =>
                anchor.RouteIdentityId != "us287").ToArray(),
        };

        var plan = RouteContextPlanner.BuildForEdge(fixture.Graph, missing, "approach");

        Assert.DoesNotContain(plan.Placements, placement => placement.RouteIdentityId == "us287");
        Assert.Contains(plan.Omissions, omission =>
            omission.RouteIdentityId == "us287" &&
            omission.Reason.Contains("No exact", StringComparison.Ordinal));
        Assert.Contains(plan.Omissions, omission =>
            omission.Id == "marker-us287-42" &&
            omission.Reason.Contains("no exact colocated", StringComparison.Ordinal));

        var contradictory = fixture.Semantics with
        {
            RoadsideMarkers = fixture.Semantics.RoadsideMarkers.Select(marker =>
                marker.Id == "marker-us36-42" ? marker with { DisplayText = "43" } : marker).ToArray(),
        };
        var error = Assert.Throws<InvalidDataException>(() =>
            RouteContextPlanner.BuildForEdge(fixture.Graph, contradictory, "approach"));
        Assert.Contains("exact anchor requires '42'", error.Message);
    }

    [Fact]
    public void ExitAndTransferSignsCarryLaneDestinationsServicesAndSeparation()
    {
        var fixture = CreateFixture();

        var plan = RouteContextPlanner.BuildForEdge(fixture.Graph, fixture.Semantics, "approach");

        var exit = Assert.Single(plan.Placements, placement =>
            placement.Kind == RouteContextPlacementKind.ExitSign);
        Assert.Equal("EXIT 42A", exit.PrimaryText);
        Assert.Equal("BOULDER JUNCTION / NEDERLAND", exit.SecondaryText);
        Assert.Equal(["lane-exit"], exit.LaneIds);
        Assert.Equal(["US 36 EAST", "TO CO 93 NORTH"], exit.RouteShields);
        Assert.Equal("LANE 2", exit.LaneGuidance);
        Assert.Equal(["fuel", "food"], exit.Services);

        var transfer = Assert.Single(plan.Placements, placement =>
            placement.Kind == RouteContextPlacementKind.HighwayTransferSign);
        Assert.Equal("EXIT 44 // TO", transfer.PrimaryText);
        Assert.Equal("INTERSTATE 25 SOUTH / DENVER", transfer.SecondaryText);
        Assert.Equal(["lane-transfer"], transfer.LaneIds);
        Assert.Equal(["US 36 EAST", "TO I 25 SOUTH"], transfer.RouteShields);
        Assert.Equal("RIGHT LANE", transfer.LaneGuidance);
        Assert.True(Math.Abs(exit.DistanceMeters - transfer.DistanceMeters) >=
            RouteContextPlanner.MinimumSignSeparationMeters);
    }

    [Fact]
    public void ChunkOwnershipUsesExactHalfOpenBoundaries()
    {
        var plan = new RouteContextPlan(
            [
                Placement("before-start", 99.9999995),
                Placement("at-start", 100),
                Placement("before-end", 199.9999995),
                Placement("at-end", 200),
            ],
            []);

        Assert.Equal(
            ["at-start", "before-end"],
            plan.ForChunk(100, 200).Select(placement => placement.Id));
        Assert.Equal(
            ["at-start", "before-end", "at-end"],
            plan.ForChunk(100, 200, includeEnd: true).Select(placement => placement.Id));
    }

    private static (InMemoryRouteGraph Graph, RouteSemanticContent Semantics) CreateFixture()
    {
        var identities = new[]
        {
            Identity("us36", "US", "36", "east"),
            Identity("us287", "US", "287", "east"),
            Identity("co93", "CO", "93", "north"),
            Identity("i25", "I", "25", "south"),
        };
        var approachLanes = new[]
        {
            Lane("lane-through", 0, LaneRole.General, LaneManeuver.Continue),
            Lane("lane-exit", 1, LaneRole.ExitOnly, LaneManeuver.Exit),
            Lane("lane-transfer", 2, LaneRole.ExitOnly, LaneManeuver.HighwayTransfer),
        };
        var approach = Edge(
            "approach",
            "start",
            "junction",
            1_000,
            ["us36", "us287"],
            approachLanes);
        var exitRamp = Edge(
            "exit-ramp",
            "junction",
            "exit-end",
            300,
            ["co93"],
            [Lane("exit-ramp-lane", 0, LaneRole.ExitOnly, LaneManeuver.Exit)]);
        var transferRamp = Edge(
            "transfer-ramp",
            "junction",
            "transfer-end",
            400,
            ["i25"],
            [Lane("transfer-ramp-lane", 0, LaneRole.ExitOnly, LaneManeuver.HighwayTransfer)]);
        var receiving = Edge(
            "receiving",
            "transfer-end",
            "finish",
            500,
            ["i25"],
            [Lane("receiving-lane", 0, LaneRole.General, LaneManeuver.Continue)]);
        var nodes = new[]
        {
            new RouteNode("start", default, "start", ["approach"]),
            new RouteNode("junction", default, "junction", ["exit-ramp", "transfer-ramp"]),
            new RouteNode("exit-end", default, "end", []),
            new RouteNode("transfer-end", default, "junction", ["receiving"]),
            new RouteNode("finish", default, "end", []),
        };
        var graph = new InMemoryRouteGraph(
            "route-context-test",
            nodes,
            [approach, exitRamp, transferRamp, receiving]);
        var anchors = new[]
        {
            Anchor("anchor-us36-42", "us36", "approach", 100, 42, "CO", "east"),
            Anchor("anchor-us287-42", "us287", "approach", 100, 42, "CO", "east"),
            Anchor("anchor-i25-214", "i25", "receiving", 25, 214, "CO-I25", "south"),
        };
        var markers = new[]
        {
            Marker("marker-us36-42", "us36", "approach", 100, "42"),
            Marker("marker-us287-42", "us287", "approach", 100, "42"),
            Marker("marker-i25-214", "i25", "receiving", 25, "214"),
        };
        var connectors = new[]
        {
            new JunctionConnector(
                "connector-exit",
                "junction",
                "approach",
                "lane-exit",
                "exit-ramp",
                "exit-ramp-lane",
                JunctionMovement.Exit,
                Provenance),
            new JunctionConnector(
                "connector-transfer",
                "junction",
                "approach",
                "lane-transfer",
                "transfer-ramp",
                "transfer-ramp-lane",
                JunctionMovement.HighwayTransfer,
                Provenance),
        };
        var exits = new[]
        {
            new RouteExit(
                "exit-42a",
                "junction",
                "exit-ramp",
                "us36",
                "42",
                "A",
                ["Boulder Junction", "Nederland"],
                ["fuel", "food"],
                Provenance),
            new RouteExit(
                "transfer-44",
                "junction",
                "transfer-ramp",
                "us36",
                "44",
                string.Empty,
                ["Interstate 25 South", "Denver"],
                [],
                Provenance),
        };
        return (
            graph,
            new RouteSemanticContent(
                [.. approach.LaneSections, .. exitRamp.LaneSections, .. transferRamp.LaneSections, .. receiving.LaneSections],
                connectors,
                identities,
                exits,
                anchors,
                markers,
                [],
                false));
    }

    private static RouteIdentity Identity(string id, string system, string number, string direction) =>
        new(id, system, number, system == "I" ? "interstate" : "us", direction, id, Provenance);

    private static RouteContextPlacement Placement(string id, double distance) =>
        new(
            id,
            RouteContextPlacementKind.MileMarker,
            RouteContextMount.RightRoadside,
            "edge",
            distance,
            "route",
            "ROUTE",
            "MILE 1",
            "east",
            "CO",
            string.Empty,
            [],
            string.Empty,
            [],
            [],
            Provenance,
            true);

    private static MilepointAnchor Anchor(
        string id,
        string identityId,
        string edgeId,
        double distance,
        double value,
        string jurisdiction,
        string direction) =>
        new(id, identityId, edgeId, distance, value, jurisdiction, direction, Provenance);

    private static RoadsideMarker Marker(
        string id,
        string identityId,
        string edgeId,
        double distance,
        string text) =>
        new(id, "mile", identityId, edgeId, distance, text, Provenance);

    private static RouteLane Lane(
        string id,
        int index,
        LaneRole role,
        LaneManeuver maneuvers) =>
        new(id, index, 3.6f, role, maneuvers, Provenance);

    private static RouteEdge Edge(
        string id,
        string from,
        string to,
        double length,
        IReadOnlyList<string> identities,
        IReadOnlyList<RouteLane> lanes) =>
        new(
            id,
            from,
            to,
            length,
            lanes.Count,
            30,
            [0, 0],
            [0, 0],
            "test",
            "route-context",
            [$"chunk-{id}"])
        {
            LaneSections =
            [
                new LaneSection(
                    $"section-{id}",
                    id,
                    0,
                    length,
                    lanes,
                    new RouteShoulder(1.5f, "paved"),
                    new RouteShoulder(2.5f, "paved"),
                    identities.Contains("i25", StringComparer.Ordinal) ? "south" : "east",
                    Provenance),
            ],
            RouteIdentityIds = identities,
        };
}
