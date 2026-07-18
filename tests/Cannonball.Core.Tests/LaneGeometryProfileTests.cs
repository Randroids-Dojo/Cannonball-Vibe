using Cannonball.Core.Routes;

namespace Cannonball.Core.Tests;

public sealed class LaneGeometryProfileTests
{
    [Fact]
    public void StableThroughLanesDoNotJumpWhenRightLaneIsAdded()
    {
        var edge = VariableLaneEdge();

        var before = LaneGeometryProfile.Evaluate(edge, 100);
        var after = LaneGeometryProfile.Evaluate(edge, 300);

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

        foreach (var boundary in new[] { 200.0, 400.0, 600.0 })
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

        var transitionStart = LaneGeometryProfile.Evaluate(edge, 140);
        var transitionMiddle = LaneGeometryProfile.Evaluate(edge, 200);
        var transitionEnd = LaneGeometryProfile.Evaluate(edge, 260);
        var entrance = transitionMiddle.Lanes.Single(lane => lane.Id == "entrance");

        Assert.Equal(0, transitionStart.Lanes.Single(lane => lane.Id == "entrance").WidthMeters, 6);
        Assert.Equal(1.8, entrance.WidthMeters, 6);
        Assert.Equal(LaneRole.EntranceOnly, entrance.Role);
        Assert.Equal(3.6, transitionEnd.Lanes.Single(lane => lane.Id == "entrance").WidthMeters, 6);
        Assert.Equal(1.5, transitionStart.LaneLeftMeters - transitionStart.PavedLeftMeters, 6);
        Assert.Equal(3.0, transitionEnd.PavedRightMeters - transitionEnd.LaneRightMeters, 6);
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
            800,
            4,
            40,
            [],
            [],
            "fixture",
            "topology",
            ["chunk"])
        {
            LaneSections =
            [
                Section("two", 0, 200, Lane("through-left", 0), Lane("through-right", 1)),
                Section(
                    "entrance-add",
                    200,
                    400,
                    Lane("through-left", 0),
                    Lane("through-right", 1),
                    Lane("entrance", 2, LaneRole.EntranceOnly)),
                Section(
                    "exit-split",
                    400,
                    600,
                    Lane("through-left", 0),
                    Lane("through-right", 1),
                    Lane("entrance", 2, LaneRole.Auxiliary),
                    Lane("exit", 3, LaneRole.ExitOnly)),
                Section("drop", 600, 800, Lane("through-left", 0), Lane("through-right", 1)),
            ],
        };
    }
}
