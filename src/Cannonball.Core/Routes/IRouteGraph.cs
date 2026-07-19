namespace Cannonball.Core.Routes;

public interface IRouteGraph
{
    string ContentVersion { get; }

    RouteNode GetNode(string nodeId);

    RouteEdge GetEdge(string edgeId);

    RouteEdge? GetOpposingEdge(string edgeId);

    IReadOnlyList<RouteEdge> GetOutgoingEdges(string nodeId);

    double GetRemainingDistance(RoutePosition position, IReadOnlyList<string> routePlan);
}
public interface IChunkSource
{
    ValueTask<ChunkManifest> GetManifestAsync(string chunkId, CancellationToken cancellationToken = default);

    ValueTask<ReadOnlyMemory<byte>> ReadChunkAsync(string chunkId, CancellationToken cancellationToken = default);
}

public sealed class InMemoryRouteGraph : IRouteGraph
{
    private readonly IReadOnlyDictionary<string, RouteNode> _nodes;
    private readonly IReadOnlyDictionary<string, RouteEdge> _edges;

    public InMemoryRouteGraph(string contentVersion, IEnumerable<RouteNode> nodes, IEnumerable<RouteEdge> edges)
    {
        ContentVersion = contentVersion;
        _nodes = nodes.ToDictionary(node => node.Id, StringComparer.Ordinal);
        _edges = edges.ToDictionary(edge => edge.Id, StringComparer.Ordinal);

        foreach (var edge in _edges.Values)
        {
            if (!_nodes.ContainsKey(edge.FromNodeId) || !_nodes.ContainsKey(edge.ToNodeId))
            {
                throw new ArgumentException($"Edge '{edge.Id}' references a missing node.", nameof(edges));
            }
            ValidateCarriageway(edge);
        }
    }

    public string ContentVersion { get; }

    private void ValidateCarriageway(RouteEdge edge)
    {
        var signedDirections = edge.LaneSections
            .Select(section => NormalizeDirection(section.SignedDirection))
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        if (signedDirections.Length > 1)
        {
            throw new ArgumentException(
                $"Route edge '{edge.Id}' changes signed direction between lane sections.",
                "edges");
        }
        if (edge.RoadwayKind != RoadwayKind.DividedCarriageway)
        {
            if (!string.IsNullOrWhiteSpace(edge.CarriagewayGroupId) ||
                !string.IsNullOrWhiteSpace(edge.OpposingEdgeId))
            {
                throw new ArgumentException(
                    $"Non-divided edge '{edge.Id}' cannot declare carriageway pairing.",
                    "edges");
            }
            return;
        }

        if (string.IsNullOrWhiteSpace(edge.CarriagewayGroupId) ||
            string.IsNullOrWhiteSpace(edge.OpposingEdgeId) ||
            string.Equals(edge.Id, edge.OpposingEdgeId, StringComparison.Ordinal) ||
            !_edges.TryGetValue(edge.OpposingEdgeId, out var opposing))
        {
            throw new ArgumentException(
                $"Divided carriageway edge '{edge.Id}' needs a distinct, existing opposing edge.",
                "edges");
        }
        if (opposing.RoadwayKind != RoadwayKind.DividedCarriageway ||
            !string.Equals(opposing.OpposingEdgeId, edge.Id, StringComparison.Ordinal) ||
            !string.Equals(
                opposing.CarriagewayGroupId,
                edge.CarriagewayGroupId,
                StringComparison.Ordinal))
        {
            throw new ArgumentException(
                $"Divided carriageway edge '{edge.Id}' does not have a reciprocal pair.",
                "edges");
        }
        if (signedDirections.Length == 1 && opposing.LaneSections.Count > 0 &&
            !AreOpposingDirections(
                signedDirections[0],
                opposing.LaneSections[0].SignedDirection))
        {
            throw new ArgumentException(
                $"Divided carriageway edge '{edge.Id}' does not declare the opposite " +
                "signed direction from its pair.",
                "edges");
        }
    }

    private static bool AreOpposingDirections(string first, string second)
    {
        return (NormalizeDirection(first), NormalizeDirection(second)) is
            ("east", "west") or ("west", "east") or
            ("north", "south") or ("south", "north");
    }

    private static string NormalizeDirection(string value) =>
        value.Trim().ToLowerInvariant() switch
        {
            "eastbound" => "east",
            "westbound" => "west",
            "northbound" => "north",
            "southbound" => "south",
            _ => value.Trim().ToLowerInvariant(),
        };

    public RouteNode GetNode(string nodeId) =>
        _nodes.TryGetValue(nodeId, out var node)
            ? node
            : throw new KeyNotFoundException($"Unknown route node '{nodeId}'.");

    public RouteEdge GetEdge(string edgeId) =>
        _edges.TryGetValue(edgeId, out var edge)
            ? edge
            : throw new KeyNotFoundException($"Unknown route edge '{edgeId}'.");

    public RouteEdge? GetOpposingEdge(string edgeId)
    {
        var edge = GetEdge(edgeId);
        return edge.RoadwayKind == RoadwayKind.DividedCarriageway
            ? GetEdge(edge.OpposingEdgeId)
            : null;
    }

    public IReadOnlyList<RouteEdge> GetOutgoingEdges(string nodeId) =>
        GetNode(nodeId).OutgoingEdgeIds.Select(GetEdge).ToArray();

    public double GetRemainingDistance(RoutePosition position, IReadOnlyList<string> routePlan)
    {
        var current = GetEdge(position.EdgeId);
        position.Validate(current);

        var remaining = current.LengthMeters - position.DistanceMeters;
        var currentIndex = routePlan.IndexOf(position.EdgeId);
        if (currentIndex < 0)
        {
            throw new ArgumentException("The route plan does not contain the current edge.", nameof(routePlan));
        }

        for (var index = currentIndex + 1; index < routePlan.Count; index++)
        {
            remaining += GetEdge(routePlan[index]).LengthMeters;
        }

        return remaining;
    }
}

internal static class ReadOnlyListExtensions
{
    public static int IndexOf<T>(this IReadOnlyList<T> values, T value)
    {
        var comparer = EqualityComparer<T>.Default;
        for (var index = 0; index < values.Count; index++)
        {
            if (comparer.Equals(values[index], value))
            {
                return index;
            }
        }

        return -1;
    }
}
