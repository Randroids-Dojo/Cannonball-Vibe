namespace Cannonball.Core.Routes;

public sealed record RoutePlanEdge(
    string EdgeId,
    double StartMeters,
    double EndMeters);

public sealed class LinearRoutePlan
{
    private readonly IReadOnlyDictionary<string, RoutePlanEdge> _edgesById;

    private LinearRoutePlan(IReadOnlyList<RoutePlanEdge> edges)
    {
        Edges = edges;
        _edgesById = edges.ToDictionary(edge => edge.EdgeId, StringComparer.Ordinal);
        TotalLengthMeters = edges[^1].EndMeters;
    }

    public IReadOnlyList<RoutePlanEdge> Edges { get; }

    public IReadOnlyList<string> EdgeIds => Edges.Select(edge => edge.EdgeId).ToArray();

    public double TotalLengthMeters { get; }

    public RoutePlanEdge GetEdge(string edgeId) =>
        _edgesById.TryGetValue(edgeId, out var edge)
            ? edge
            : throw new KeyNotFoundException($"Route plan has no edge '{edgeId}'.");

    public RoutePlanEdge GetEdgeAtDistance(double distanceMeters)
    {
        if (!double.IsFinite(distanceMeters) || distanceMeters < 0 || distanceMeters > TotalLengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(distanceMeters));
        }
        return Edges.FirstOrDefault(edge => distanceMeters < edge.EndMeters) ?? Edges[^1];
    }

    public static LinearRoutePlan Build(IRouteGraph graph, IEnumerable<string> edgeIds)
    {
        ArgumentNullException.ThrowIfNull(graph);
        ArgumentNullException.ThrowIfNull(edgeIds);

        var selected = edgeIds.ToHashSet(StringComparer.Ordinal);
        if (selected.Count == 0)
        {
            throw new ArgumentException("A route plan needs at least one edge.", nameof(edgeIds));
        }
        var edges = selected.Select(graph.GetEdge).ToDictionary(edge => edge.Id, StringComparer.Ordinal);
        var destinationNodes = edges.Values.Select(edge => edge.ToNodeId).ToHashSet(StringComparer.Ordinal);
        var starts = edges.Values
            .Where(edge => !destinationNodes.Contains(edge.FromNodeId))
            .OrderBy(edge => edge.Id, StringComparer.Ordinal)
            .ToArray();
        if (starts.Length != 1)
        {
            throw new InvalidDataException(
                $"Selected route must have exactly one starting edge; found {starts.Length}.");
        }

        var remaining = new HashSet<string>(selected, StringComparer.Ordinal);
        var ordered = new List<RouteEdge>(selected.Count);
        var current = starts[0];
        while (true)
        {
            ordered.Add(current);
            remaining.Remove(current.Id);
            if (remaining.Count == 0)
            {
                break;
            }
            var next = graph.GetOutgoingEdges(current.ToNodeId)
                .Where(edge => remaining.Contains(edge.Id))
                .OrderBy(edge => edge.Id, StringComparer.Ordinal)
                .ToArray();
            if (next.Length != 1)
            {
                throw new InvalidDataException(
                    $"Selected route is not a single directed corridor at node '{current.ToNodeId}'; " +
                    $"found {next.Length} continuing edges.");
            }
            current = next[0];
        }

        var offset = 0.0;
        var spans = new List<RoutePlanEdge>(ordered.Count);
        foreach (var edge in ordered)
        {
            if (!double.IsFinite(edge.LengthMeters) || edge.LengthMeters <= 0)
            {
                throw new InvalidDataException($"Route edge '{edge.Id}' has no positive finite length.");
            }
            spans.Add(new RoutePlanEdge(edge.Id, offset, offset + edge.LengthMeters));
            offset += edge.LengthMeters;
        }
        return new LinearRoutePlan(spans);
    }
}
