namespace Cannonball.Core.Routes;

public sealed record RouteChoice(
    string ConnectorId,
    string JunctionNodeId,
    string FromEdgeId,
    string FromLaneId,
    string ToEdgeId,
    string ToLaneId,
    JunctionMovement Movement,
    IReadOnlyList<string> RouteIdentityIds,
    string ExitNumber,
    IReadOnlyList<string> Destinations);

public sealed record RoutePlanSelection(
    string Id,
    IReadOnlyList<string> EdgeIds,
    IReadOnlyList<string> ConnectorIds,
    string StartLaneId);

public sealed record ValidatedRoutePlan(
    RoutePlanSelection Selection,
    LinearRoutePlan LinearPlan,
    IReadOnlyList<RouteChoice> Transitions,
    string EndLaneId);

public sealed class RouteChoiceCatalog
{
    private readonly IRouteGraph _graph;
    private readonly RouteSemanticContent _semantics;
    private readonly IReadOnlyDictionary<string, JunctionConnector> _connectors;
    private readonly IReadOnlyDictionary<string, RouteIdentity> _identities;

    public RouteChoiceCatalog(IRouteGraph graph, RouteSemanticContent semantics)
    {
        ArgumentNullException.ThrowIfNull(graph);
        ArgumentNullException.ThrowIfNull(semantics);
        _graph = graph;
        _semantics = semantics;
        _connectors = semantics.JunctionConnectors.ToDictionary(
            connector => connector.Id,
            StringComparer.Ordinal);
        _identities = semantics.RouteIdentities.ToDictionary(
            identity => identity.Id,
            StringComparer.Ordinal);
    }

    public IReadOnlyList<RouteChoice> GetChoices(string fromEdgeId, string? fromLaneId = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(fromEdgeId);
        var edge = _graph.GetEdge(fromEdgeId);
        return _semantics.JunctionConnectors
            .Where(connector =>
                string.Equals(connector.FromEdgeId, edge.Id, StringComparison.Ordinal) &&
                (fromLaneId is null ||
                    string.Equals(connector.FromLaneId, fromLaneId, StringComparison.Ordinal)))
            .OrderBy(connector => connector.Movement)
            .ThenBy(connector => connector.ToEdgeId, StringComparer.Ordinal)
            .ThenBy(connector => connector.ToLaneId, StringComparer.Ordinal)
            .Select(ToChoice)
            .ToArray();
    }

    public ValidatedRoutePlan ValidatePlan(RoutePlanSelection selection)
    {
        ArgumentNullException.ThrowIfNull(selection);
        ArgumentException.ThrowIfNullOrWhiteSpace(selection.Id);
        ArgumentException.ThrowIfNullOrWhiteSpace(selection.StartLaneId);
        if (selection.EdgeIds.Count == 0)
        {
            throw new InvalidDataException($"Route plan '{selection.Id}' has no edges.");
        }
        if (selection.ConnectorIds.Count != selection.EdgeIds.Count - 1)
        {
            throw new InvalidDataException(
                $"Route plan '{selection.Id}' needs exactly one connector per edge transition.");
        }

        var linear = LinearRoutePlan.Build(_graph, selection.EdgeIds);
        if (!linear.EdgeIds.SequenceEqual(selection.EdgeIds, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                $"Route plan '{selection.Id}' is not in directed graph order.");
        }

        var currentLaneId = selection.StartLaneId;
        var firstSection = _graph.GetEdge(selection.EdgeIds[0]).GetLaneSection(0);
        if (!firstSection.Lanes.Any(lane =>
                string.Equals(lane.Id, currentLaneId, StringComparison.Ordinal)))
        {
            throw new InvalidDataException(
                $"Route plan '{selection.Id}' starts on unknown lane '{currentLaneId}'.");
        }

        var transitions = new List<RouteChoice>(selection.ConnectorIds.Count);
        for (var index = 0; index < selection.ConnectorIds.Count; index++)
        {
            var connectorId = selection.ConnectorIds[index];
            if (!_connectors.TryGetValue(connectorId, out var connector))
            {
                throw new InvalidDataException(
                    $"Route plan '{selection.Id}' references unknown connector '{connectorId}'.");
            }
            var expectedFromEdgeId = selection.EdgeIds[index];
            var expectedToEdgeId = selection.EdgeIds[index + 1];
            if (!string.Equals(connector.FromEdgeId, expectedFromEdgeId, StringComparison.Ordinal) ||
                !string.Equals(connector.ToEdgeId, expectedToEdgeId, StringComparison.Ordinal) ||
                !string.Equals(connector.FromLaneId, currentLaneId, StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"Route plan '{selection.Id}' connector '{connector.Id}' does not continue " +
                    $"edge '{expectedFromEdgeId}' lane '{currentLaneId}' to edge " +
                    $"'{expectedToEdgeId}'.");
            }
            var choice = ToChoice(connector);
            transitions.Add(choice);
            currentLaneId = connector.ToLaneId;
        }

        return new ValidatedRoutePlan(selection, linear, transitions, currentLaneId);
    }

    private RouteChoice ToChoice(JunctionConnector connector)
    {
        var fromEdge = _graph.GetEdge(connector.FromEdgeId);
        var toEdge = _graph.GetEdge(connector.ToEdgeId);
        if (!string.Equals(fromEdge.ToNodeId, connector.JunctionNodeId, StringComparison.Ordinal) ||
            !string.Equals(toEdge.FromNodeId, connector.JunctionNodeId, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Connector '{connector.Id}' is not incident to junction " +
                $"'{connector.JunctionNodeId}'.");
        }
        var sourceLane = fromEdge.GetLaneSection(fromEdge.LengthMeters).Lanes.SingleOrDefault(lane =>
            string.Equals(lane.Id, connector.FromLaneId, StringComparison.Ordinal));
        var targetLane = toEdge.GetLaneSection(0).Lanes.SingleOrDefault(lane =>
            string.Equals(lane.Id, connector.ToLaneId, StringComparison.Ordinal));
        if (sourceLane is null || targetLane is null)
        {
            throw new InvalidDataException(
                $"Connector '{connector.Id}' references a lane outside its edge endpoint.");
        }

        var routeIdentityIds = toEdge.RouteIdentityIds
            .Where(_identities.ContainsKey)
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray();
        var exit = _semantics.Exits
            .Where(candidate =>
                string.Equals(candidate.JunctionNodeId, connector.JunctionNodeId, StringComparison.Ordinal) &&
                string.Equals(candidate.RampEdgeId, connector.ToEdgeId, StringComparison.Ordinal))
            .OrderBy(candidate => candidate.Id, StringComparer.Ordinal)
            .FirstOrDefault();
        return new RouteChoice(
            connector.Id,
            connector.JunctionNodeId,
            connector.FromEdgeId,
            connector.FromLaneId,
            connector.ToEdgeId,
            connector.ToLaneId,
            connector.Movement,
            routeIdentityIds,
            exit is null ? string.Empty : $"{exit.Number}{exit.Suffix}",
            exit?.Destinations ?? []);
    }
}
