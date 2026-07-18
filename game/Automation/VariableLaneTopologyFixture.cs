using Cannonball.Core.Content;
using Cannonball.Core.Routes;

namespace Cannonball.Game.Automation;

public sealed record VariableLaneTopologyOverlay(
    RouteContentPackage Package,
    string EdgeId,
    IReadOnlyList<double> TransitionDistancesMeters,
    string OverrideId);

public static class VariableLaneTopologyFixture
{
    public const string AuthoredOverrideId = "p0-010-variable-lanes-v1";

    public static VariableLaneTopologyOverlay Apply(RouteContentPackage package)
    {
        ArgumentNullException.ThrowIfNull(package);
        var edgeIds = package.Chunks.Values
            .Select(chunk => chunk.EdgeId)
            .Distinct(StringComparer.Ordinal)
            .ToHashSet(StringComparer.Ordinal);
        var edges = edgeIds.Select(package.Graph.GetEdge).ToArray();
        var selected = edges
            .Where(edge => edge.GetEffectiveLaneSections().First().Lanes.Count >= 2)
            .OrderByDescending(edge => edge.LengthMeters)
            .ThenBy(edge => edge.Id, StringComparer.Ordinal)
            .FirstOrDefault()
            ?? throw new InvalidDataException(
                "Variable-lane topology fixture needs an edge with at least two source lanes.");

        var sourceSection = selected.GetEffectiveLaneSections().First();
        var sourceLanes = sourceSection.Lanes.OrderBy(lane => lane.Index).Take(2).ToArray();
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            sourceSection.Provenance.SourceId,
            sourceSection.Provenance.SourceRecordId,
            sourceSection.Provenance.ArtifactSha256,
            "Deterministic authored topology overlay derived from the verified source corridor.",
            AuthoredOverrideId);
        var width = Math.Max(3.0f, sourceLanes.Average(lane => lane.WidthMeters));
        RouteLane Through(RouteLane source, int index) => source with
        {
            Index = index,
            Role = LaneRole.General,
            AllowedManeuvers = LaneManeuver.Continue | LaneManeuver.Merge |
                LaneManeuver.Split | LaneManeuver.Exit | LaneManeuver.HighwayTransfer,
            Provenance = provenance,
        };
        RouteLane Added(string suffix, int index, LaneRole role, LaneManeuver maneuvers) => new(
            $"{selected.Id}:topology:{suffix}",
            index,
            width,
            role,
            maneuvers,
            provenance);

        var throughLeft = Through(sourceLanes[0], 0);
        var throughRight = Through(sourceLanes[1], 1);
        var entrance = Added(
            "entrance",
            2,
            LaneRole.EntranceOnly,
            LaneManeuver.Entrance | LaneManeuver.Merge | LaneManeuver.Continue);
        var auxiliary = entrance with
        {
            Role = LaneRole.Auxiliary,
            AllowedManeuvers = LaneManeuver.Continue | LaneManeuver.Merge |
                LaneManeuver.Split | LaneManeuver.Exit,
        };
        var exit = Added(
            "exit-transfer",
            3,
            LaneRole.ExitOnly,
            LaneManeuver.Split | LaneManeuver.Exit | LaneManeuver.HighwayTransfer);
        var retainedExit = exit with { Index = 2 };
        var boundaries = Enumerable.Range(1, 4)
            .Select(index => selected.LengthMeters * index / 5.0)
            .ToArray();
        LaneSection Section(string suffix, double start, double end, params RouteLane[] lanes) => new(
            $"{selected.Id}:topology:{suffix}",
            selected.Id,
            start,
            end,
            lanes,
            new RouteShoulder(1.5f, "paved"),
            new RouteShoulder(3.0f, "paved"),
            sourceSection.SignedDirection,
            provenance);
        var sections = new LaneSection[]
        {
            Section("through", 0, boundaries[0], throughLeft, throughRight),
            Section(
                "entrance-merge",
                boundaries[0],
                boundaries[1],
                throughLeft,
                throughRight,
                entrance),
            Section(
                "auxiliary-and-exit-split",
                boundaries[1],
                boundaries[2],
                throughLeft,
                throughRight,
                auxiliary,
                exit),
            Section(
                "highway-transfer",
                boundaries[2],
                boundaries[3],
                throughLeft,
                throughRight,
                retainedExit),
            Section("through-restored", boundaries[3], selected.LengthMeters, throughLeft, throughRight),
        };
        var overlayEdge = selected with { LaneCount = 4, LaneSections = sections };
        var overlayEdges = edges
            .Select(edge => edge.Id == selected.Id ? overlayEdge : edge)
            .ToArray();
        var nodes = overlayEdges
            .SelectMany(edge => new[] { edge.FromNodeId, edge.ToNodeId })
            .Distinct(StringComparer.Ordinal)
            .Select(package.Graph.GetNode)
            .Select(node => node with
            {
                OutgoingEdgeIds = node.OutgoingEdgeIds
                    .Where(edgeIds.Contains)
                    .ToArray(),
            })
            .ToArray();
        var graph = new InMemoryRouteGraph(package.Graph.ContentVersion, nodes, overlayEdges);
        var sourceSemantics = package.Semantics ?? RouteSemanticsCompatibility.CreateLegacyContent(edges);
        var semantics = sourceSemantics with
        {
            LaneSections = sourceSemantics.LaneSections
                .Where(section => section.EdgeId != selected.Id)
                .Concat(sections)
                .ToArray(),
            IsLegacySynthesis = false,
        };
        return new VariableLaneTopologyOverlay(
            package with { Graph = graph, Semantics = semantics },
            selected.Id,
            boundaries,
            AuthoredOverrideId);
    }
}
