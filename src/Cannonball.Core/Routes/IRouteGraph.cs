namespace Cannonball.Core.Routes;

public interface IRouteGraph
{
    string ContentVersion { get; }

    RouteNode GetNode(string nodeId);

    RouteEdge GetEdge(string edgeId);

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
        }
    }

    public string ContentVersion { get; }

    public RouteNode GetNode(string nodeId) =>
        _nodes.TryGetValue(nodeId, out var node)
            ? node
            : throw new KeyNotFoundException($"Unknown route node '{nodeId}'.");

    public RouteEdge GetEdge(string edgeId) =>
        _edges.TryGetValue(edgeId, out var edge)
            ? edge
            : throw new KeyNotFoundException($"Unknown route edge '{edgeId}'.");

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
