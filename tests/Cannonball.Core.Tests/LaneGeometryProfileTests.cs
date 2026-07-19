using Cannonball.Core.Routes;

namespace Cannonball.Core.Tests;

public sealed class LaneGeometryProfileTests
{
    [Fact]
    public void StableThroughLanesDoNotJumpWhenRightLaneIsAdded()
    {
        var edge = VariableLaneEdge();

        var before = LaneGeometryProfile.Evaluate(edge, 100);
        var after = LaneGeometryProfile.Evaluate(edge, 600);

        Assert.Equal(7.2, before.LaneWidthMeters, 6);
        Assert.Equal(10.8, after.LaneWidthMeters, 6);
        Assert.Equal(Center(before, "through-left"), Center(after, "through-left"), 6);
        Assert.Equal(Center(before, "through-right"), Center(after, "through-right"), 6);
        Assert.True(after.LaneRightMeters > before.LaneRightMeters);
    }

    [Fact]
    public void LaneAdditionAndDropRemainContinuousAcrossTapers()
    {
        var edge = VariableLaneEdge();

        foreach (var boundary in new[] { 400.0, 800.0, 1_200.0, 1_600.0 })
        {
            var immediatelyBefore = LaneGeometryProfile.Evaluate(edge, boundary - 0.001);
            var immediatelyAfter = LaneGeometryProfile.Evaluate(edge, boundary + 0.001);

            Assert.InRange(
                Math.Abs(immediatelyAfter.LaneLeftMeters - immediatelyBefore.LaneLeftMeters),
                0,
                0.001);
            Assert.InRange(
                Math.Abs(immediatelyAfter.LaneRightMeters - immediatelyBefore.LaneRightMeters),
                0,
                0.001);
        }
    }

    [Fact]
    public void TransitionCarriesRolesShouldersAndZeroWidthLaneBirth()
    {
        var edge = VariableLaneEdge();
        var transition = LaneGeometryProfile.GetTransitions(edge)[0];

        var transitionStart = LaneGeometryProfile.Evaluate(edge, transition.StartMeters);
        var transitionMiddle = LaneGeometryProfile.Evaluate(edge, transition.BoundaryMeters);
        var transitionEnd = LaneGeometryProfile.Evaluate(edge, transition.EndMeters);
        var entrance = transitionMiddle.Lanes.Single(lane => lane.Id == "entrance");

        Assert.Equal(0, transitionStart.Lanes.Single(lane => lane.Id == "entrance").WidthMeters, 6);
        Assert.Equal(1.8, entrance.WidthMeters, 6);
        Assert.Equal(LaneRole.EntranceOnly, entrance.Role);
        Assert.Equal(3.6, transitionEnd.Lanes.Single(lane => lane.Id == "entrance").WidthMeters, 6);
        Assert.Equal(1.5, transitionStart.LaneLeftMeters - transitionStart.PavedLeftMeters, 6);
        Assert.Equal(3.0, transitionEnd.PavedRightMeters - transitionEnd.LaneRightMeters, 6);
    }

    [Fact]
    public void HighwayTaperUsesAConstantSurveyedRate()
    {
        var edge = VariableLaneEdge();
        var transition = LaneGeometryProfile.GetTransitions(edge)[0];
        var quarter = LaneGeometryProfile.Evaluate(
            edge,
            transition.StartMeters + (transition.EndMeters - transition.StartMeters) / 4);

        Assert.Equal(
            0.9,
            quarter.Lanes.Single(lane => lane.Id == "entrance").WidthMeters,
            6);
    }

    [Fact]
    public void PersistentThroughLanesRemainOnOneControlLineAcrossEverySection()
    {
        var edge = VariableLaneEdge();
        var samples = new[] { 100.0, 600.0, 1_000.0, 1_400.0, 1_900.0 }
            .Select(distance => LaneGeometryProfile.Evaluate(edge, distance))
            .ToArray();

        Assert.All(samples, sample => Assert.Equal(-1.8, Center(sample, "through-left"), 6));
        Assert.All(samples, sample => Assert.Equal(1.8, Center(sample, "through-right"), 6));
    }

    [Fact]
    public void EveryInterpolatedLaneTilesWithoutGapOrOverlap()
    {
        var edge = VariableLaneEdge();

        for (var distance = 0.0; distance <= edge.LengthMeters; distance += 5)
        {
            var lanes = LaneGeometryProfile.Evaluate(edge, distance).Lanes
                .Where(lane => lane.WidthMeters > 1e-9)
                .OrderBy(lane => lane.CenterMeters)
                .ToArray();
            for (var index = 0; index < lanes.Length - 1; index++)
            {
                var gap = lanes[index + 1].CenterMeters - lanes[index + 1].WidthMeters / 2 -
                    (lanes[index].CenterMeters + lanes[index].WidthMeters / 2);
                Assert.Equal(0, gap, 6);
            }
        }
    }

    [Fact]
    public void InteriorLaneDropWithPersistentOutsideLaneIsRejected()
    {
        var edge = VariableLaneEdge();
        var sections = edge.LaneSections.ToArray();
        var fourLaneSection = sections[2];
        var invalidThreeLaneSection = sections[3] with
        {
            Lanes =
            [
                fourLaneSection.Lanes[0],
                fourLaneSection.Lanes[1],
                fourLaneSection.Lanes[3] with { Index = 2 },
            ],
        };
        var invalid = edge with
        {
            LaneSections = sections.Select((section, index) =>
                index == 3 ? invalidThreeLaneSection : section).ToArray(),
        };

        var error = Assert.Throws<InvalidDataException>(() =>
            LaneGeometryProfile.Evaluate(invalid, 1_200));
        Assert.Contains("interior lane", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void InsufficientDistanceForDesignedTaperIsRejected()
    {
        var edge = VariableLaneEdge() with { SpeedLimitMetersPerSecond = 100 };

        var error = Assert.Throws<InvalidDataException>(() =>
            LaneGeometryProfile.Evaluate(edge, 400));
        Assert.Contains("enough taper distance", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RecommendedHighwayTransitionUsesSpeedAndFullLateralOffset()
    {
        var edge = VariableLaneEdge();

        var transitionLength = LaneGeometryProfile.GetRecommendedTransitionLengthMeters(edge);

        Assert.InRange(transitionLength, 251.9, 252.1);
        Assert.InRange(3.6 / transitionLength, 0, 1.0 / 50.0);
    }

    private static double Center(LaneGeometrySample sample, string id) =>
        sample.Lanes.Single(lane => lane.Id == id).CenterMeters;

    private static RouteEdge VariableLaneEdge()
    {
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            "variable-lane-fixture",
            "edge",
            new string('a', 64),
            "Deterministic topology regression fixture.",
            "p0-010-variable-lanes-v1");
        RouteLane Lane(string id, int index, LaneRole role = LaneRole.General) => new(
            id,
            index,
            3.6f,
            role,
            LaneManeuver.Continue | LaneManeuver.Merge | LaneManeuver.Split |
                LaneManeuver.Exit | LaneManeuver.Entrance |
                LaneManeuver.HighwayTransfer,
            provenance);
        LaneSection Section(
            string id,
            double start,
            double end,
            params RouteLane[] lanes) => new(
                id,
                "edge",
                start,
                end,
                lanes,
                new RouteShoulder(1.5f, "paved"),
                new RouteShoulder(3.0f, "paved"),
                "east",
                provenance);
        return new RouteEdge(
            "edge",
            "west",
            "east",
            2_000,
            4,
            31.2928,
            [],
            [],
            "fixture",
            "topology",
            ["chunk"])
        {
            LaneSections =
            [
                Section("two", 0, 400, Lane("through-left", 0), Lane("through-right", 1)),
                Section(
                    "entrance-add",
                    400,
                    800,
                    Lane("through-left", 0),
                    Lane("through-right", 1),
                    Lane("entrance", 2, LaneRole.EntranceOnly)),
                Section(
                    "exit-split",
                    800,
                    1_200,
                    Lane("through-left", 0),
                    Lane("through-right", 1),
                    Lane("entrance", 2, LaneRole.Auxiliary),
                    Lane("exit", 3, LaneRole.ExitOnly)),
                Section(
                    "transfer",
                    1_200,
                    1_600,
                    Lane("through-left", 0),
                    Lane("through-right", 1),
                    Lane("entrance", 2, LaneRole.ExitOnly)),
                Section(
                    "drop",
                    1_600,
                    2_000,
                    Lane("through-left", 0),
                    Lane("through-right", 1)),
            ],
        };
    }
}
