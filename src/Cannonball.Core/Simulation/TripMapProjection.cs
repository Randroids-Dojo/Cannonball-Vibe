using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;

namespace Cannonball.Core.Simulation;

public enum TripMapPathKind
{
    Traveled,
    Planned,
    Alternative,
}

public enum TripMapFeatureKind
{
    Exit,
    HighwayTransfer,
    ServiceStop,
}

public readonly record struct TripMapPoint(double XMeters, double YMeters);

public sealed record TripMapPathSegment(
    string Id,
    string EdgeId,
    TripMapPathKind Kind,
    IReadOnlyList<TripMapPoint> Points);

public sealed record TripMapAlternative(
    string Id,
    string ConnectorId,
    string ToEdgeId,
    string Label,
    IReadOnlyList<TripMapPathSegment> Segments);

public sealed record TripMapFeature(
    string Id,
    TripMapFeatureKind Kind,
    string Title,
    string Detail,
    double RouteDistanceMeters,
    TripMapPoint Position,
    IReadOnlyList<string> Services);

public sealed record TripMapProjectionState(
    string StartLabel,
    string DestinationLabel,
    TripMapPoint Start,
    TripMapPoint Destination,
    TripMapPoint Current,
    IReadOnlyList<TripMapPathSegment> Traveled,
    IReadOnlyList<TripMapPathSegment> Planned,
    IReadOnlyList<TripMapAlternative> Alternatives,
    IReadOnlyList<TripMapFeature> UpcomingFeatures,
    IReadOnlyList<TripMapFeature> SelectedServiceStops,
    double DistanceCompletedMeters,
    double DistanceRemainingMeters,
    double EstimatedRemainingSeconds,
    AssistProfile AssistProfile);

public static class TripMapProjector
{
    private const double GeometryTolerance = 1e-6;

    public static TripMapProjectionState Project(
        RouteContentPackage package,
        string currentEdgeId,
        double currentEdgeDistanceMeters,
        IReadOnlyList<string> routePlan,
        AssistProfile assistProfile,
        double currentSpeedMetersPerSecond)
    {
        ArgumentNullException.ThrowIfNull(package);
        ArgumentException.ThrowIfNullOrWhiteSpace(currentEdgeId);
        ArgumentNullException.ThrowIfNull(routePlan);
        var semantics = package.Semantics ?? throw new InvalidDataException(
            "Trip map requires route semantic content.");
        if (semantics.SimplifiedMapGeometry.Count == 0)
        {
            throw new InvalidDataException("Trip map requires simplified immutable map geometry.");
        }

        var linearPlan = LinearRoutePlan.Build(package.Graph, routePlan);
        var currentSpan = linearPlan.GetEdge(currentEdgeId);
        var currentEdge = package.Graph.GetEdge(currentEdgeId);
        if (!double.IsFinite(currentEdgeDistanceMeters) || currentEdgeDistanceMeters < 0 ||
            currentEdgeDistanceMeters > currentEdge.LengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(currentEdgeDistanceMeters));
        }

        var geometry = semantics.SimplifiedMapGeometry
            .GroupBy(candidate => candidate.EdgeId, StringComparer.Ordinal)
            .ToDictionary(
                group => group.Key,
                group => group.OrderBy(candidate => candidate.Lod).First(),
                StringComparer.Ordinal);
        foreach (var edgeId in linearPlan.EdgeIds)
        {
            ValidateGeometry(package.Graph.GetEdge(edgeId), GetGeometry(geometry, edgeId));
        }

        var completed = currentSpan.StartMeters + currentEdgeDistanceMeters;
        var remaining = Math.Max(0, linearPlan.TotalLengthMeters - completed);
        var traveled = new List<TripMapPathSegment>();
        var planned = new List<TripMapPathSegment>();
        foreach (var span in linearPlan.Edges)
        {
            var edge = package.Graph.GetEdge(span.EdgeId);
            var edgeGeometry = GetGeometry(geometry, span.EdgeId);
            var traveledEnd = Math.Clamp(completed - span.StartMeters, 0, edge.LengthMeters);
            if (traveledEnd > GeometryTolerance)
            {
                AddSegment(traveled, span.EdgeId, TripMapPathKind.Traveled, edgeGeometry, 0, traveledEnd);
            }
            var plannedStart = Math.Clamp(completed - span.StartMeters, 0, edge.LengthMeters);
            if (plannedStart < edge.LengthMeters - GeometryTolerance)
            {
                AddSegment(planned, span.EdgeId, TripMapPathKind.Planned, edgeGeometry, plannedStart, edge.LengthMeters);
            }
        }

        var firstGeometry = GetGeometry(geometry, linearPlan.Edges[0].EdgeId);
        var lastSpan = linearPlan.Edges[^1];
        var lastEdge = package.Graph.GetEdge(lastSpan.EdgeId);
        var lastGeometry = GetGeometry(geometry, lastSpan.EdgeId);
        var current = PointAt(GetGeometry(geometry, currentEdgeId), currentEdgeDistanceMeters);
        var alternatives = BuildAlternatives(package, semantics, geometry, linearPlan, completed);
        var features = BuildFeatures(package, semantics, geometry, linearPlan, completed);
        var serviceStops = features
            .Where(feature => feature.Services.Count > 0)
            .Select(feature => feature with
            {
                Id = $"service.{feature.Id}",
                Kind = TripMapFeatureKind.ServiceStop,
            })
            .Take(3)
            .ToArray();

        var cruisingSpeed = currentEdge.SpeedLimitMetersPerSecond * (assistProfile switch
            {
                AssistProfile.Accessible => 0.82,
                AssistProfile.Raw => 0.94,
                _ => 0.88,
            });
        var expectedSpeed = Math.Max(currentSpeedMetersPerSecond, cruisingSpeed);

        return new TripMapProjectionState(
            RouteLabel(package.Graph.GetEdge(linearPlan.Edges[0].EdgeId), semantics, "START"),
            RouteLabel(lastEdge, semantics, "DESTINATION"),
            PointAt(firstGeometry, 0),
            PointAt(lastGeometry, lastEdge.LengthMeters),
            current,
            traveled,
            planned,
            alternatives,
            features,
            serviceStops,
            completed,
            remaining,
            expectedSpeed <= 0 ? 0 : remaining / expectedSpeed,
            assistProfile);
    }

    private static IReadOnlyList<TripMapAlternative> BuildAlternatives(
        RouteContentPackage package,
        RouteSemanticContent semantics,
        IReadOnlyDictionary<string, SimplifiedMapGeometry> geometry,
        LinearRoutePlan plan,
        double completed)
    {
        var result = new List<TripMapAlternative>();
        for (var index = 0; index < plan.Edges.Count; index++)
        {
            var span = plan.Edges[index];
            if (span.EndMeters + GeometryTolerance < completed)
            {
                continue;
            }
            var selectedNext = index + 1 < plan.Edges.Count ? plan.Edges[index + 1].EdgeId : null;
            foreach (var connector in semantics.JunctionConnectors
                .Where(candidate =>
                    string.Equals(candidate.FromEdgeId, span.EdgeId, StringComparison.Ordinal) &&
                    !string.Equals(candidate.ToEdgeId, selectedNext, StringComparison.Ordinal))
                .OrderBy(candidate => candidate.Id, StringComparer.Ordinal))
            {
                if (!geometry.TryGetValue(connector.ToEdgeId, out var targetGeometry))
                {
                    continue;
                }
                var target = package.Graph.GetEdge(connector.ToEdgeId);
                ValidateGeometry(target, targetGeometry);
                var segment = new TripMapPathSegment(
                    $"alternative.{connector.Id}.{target.Id}",
                    target.Id,
                    TripMapPathKind.Alternative,
                    Clip(targetGeometry, 0, target.LengthMeters));
                result.Add(new TripMapAlternative(
                    $"alternative.{connector.Id}",
                    connector.Id,
                    target.Id,
                    AlternativeLabel(connector, semantics),
                    [segment]));
            }
        }
        return result.Take(8).ToArray();
    }

    private static IReadOnlyList<TripMapFeature> BuildFeatures(
        RouteContentPackage package,
        RouteSemanticContent semantics,
        IReadOnlyDictionary<string, SimplifiedMapGeometry> geometry,
        LinearRoutePlan plan,
        double completed)
    {
        var result = new List<TripMapFeature>();
        for (var index = 0; index < plan.Edges.Count; index++)
        {
            var span = plan.Edges[index];
            if (span.EndMeters + GeometryTolerance < completed)
            {
                continue;
            }
            var edge = package.Graph.GetEdge(span.EdgeId);
            var position = PointAt(GetGeometry(geometry, edge.Id), edge.LengthMeters);
            foreach (var connector in semantics.JunctionConnectors
                .Where(candidate => string.Equals(candidate.FromEdgeId, edge.Id, StringComparison.Ordinal))
                .OrderBy(candidate => candidate.Id, StringComparer.Ordinal))
            {
                var exit = semantics.Exits.FirstOrDefault(candidate =>
                    string.Equals(candidate.JunctionNodeId, connector.JunctionNodeId, StringComparison.Ordinal) &&
                    string.Equals(candidate.RampEdgeId, connector.ToEdgeId, StringComparison.Ordinal));
                if (exit is not null)
                {
                    var number = string.Concat(exit.Number, exit.Suffix);
                    result.Add(new TripMapFeature(
                        $"exit.{exit.Id}",
                        TripMapFeatureKind.Exit,
                        string.IsNullOrWhiteSpace(number) ? "Exit" : $"Exit {number}",
                        exit.Destinations.Count == 0 ? "Ramp" : string.Join(" / ", exit.Destinations),
                        span.EndMeters,
                        position,
                        exit.Services));
                }
                else if (connector.Movement == JunctionMovement.HighwayTransfer)
                {
                    result.Add(new TripMapFeature(
                        $"transfer.{connector.Id}",
                        TripMapFeatureKind.HighwayTransfer,
                        "Highway transfer",
                        RouteLabel(package.Graph.GetEdge(connector.ToEdgeId), semantics, connector.ToEdgeId),
                        span.EndMeters,
                        position,
                        []));
                }
            }
        }
        return result
            .GroupBy(feature => feature.Id, StringComparer.Ordinal)
            .Select(group => group.First())
            .OrderBy(feature => feature.RouteDistanceMeters)
            .ThenBy(feature => feature.Id, StringComparer.Ordinal)
            .Take(16)
            .ToArray();
    }

    private static string AlternativeLabel(JunctionConnector connector, RouteSemanticContent semantics)
    {
        var exit = semantics.Exits.FirstOrDefault(candidate =>
            string.Equals(candidate.JunctionNodeId, connector.JunctionNodeId, StringComparison.Ordinal) &&
            string.Equals(candidate.RampEdgeId, connector.ToEdgeId, StringComparison.Ordinal));
        if (exit is not null)
        {
            var number = string.Concat(exit.Number, exit.Suffix);
            return exit.Destinations.Count > 0
                ? $"Exit {number}: {string.Join(" / ", exit.Destinations)}"
                : $"Exit {number}";
        }
        return connector.Movement == JunctionMovement.HighwayTransfer
            ? "Highway transfer"
            : connector.Movement.ToString();
    }

    private static string RouteLabel(RouteEdge edge, RouteSemanticContent semantics, string fallback)
    {
        var identity = edge.RouteIdentityIds
            .Select(id => semantics.RouteIdentities.FirstOrDefault(candidate =>
                string.Equals(candidate.Id, id, StringComparison.Ordinal)))
            .FirstOrDefault(candidate => candidate is not null);
        if (identity is null)
        {
            return fallback;
        }
        var route = string.Join(" ", new[] { identity.System, identity.Number }
            .Where(value => !string.IsNullOrWhiteSpace(value)));
        return string.Join(" ", new[] { route, identity.SignedDirection }
            .Where(value => !string.IsNullOrWhiteSpace(value)));
    }

    private static SimplifiedMapGeometry GetGeometry(
        IReadOnlyDictionary<string, SimplifiedMapGeometry> geometry,
        string edgeId) =>
        geometry.TryGetValue(edgeId, out var value)
            ? value
            : throw new InvalidDataException($"Trip map has no simplified geometry for edge '{edgeId}'.");

    private static void ValidateGeometry(RouteEdge edge, SimplifiedMapGeometry geometry)
    {
        if (geometry.Points.Count < 2 ||
            Math.Abs(geometry.Points[0].EdgeDistanceMeters) > GeometryTolerance ||
            Math.Abs(geometry.Points[^1].EdgeDistanceMeters - edge.LengthMeters) > GeometryTolerance)
        {
            throw new InvalidDataException(
                $"Trip map geometry for edge '{edge.Id}' does not span the full edge.");
        }
        for (var index = 1; index < geometry.Points.Count; index++)
        {
            if (geometry.Points[index].EdgeDistanceMeters <=
                geometry.Points[index - 1].EdgeDistanceMeters)
            {
                throw new InvalidDataException(
                    $"Trip map geometry for edge '{edge.Id}' is not strictly ordered.");
            }
        }
    }

    private static void AddSegment(
        ICollection<TripMapPathSegment> destination,
        string edgeId,
        TripMapPathKind kind,
        SimplifiedMapGeometry geometry,
        double startMeters,
        double endMeters)
    {
        var points = Clip(geometry, startMeters, endMeters);
        if (points.Count >= 2)
        {
            destination.Add(new TripMapPathSegment(
                $"{kind.ToString().ToLowerInvariant()}.{edgeId}", edgeId, kind, points));
        }
    }

    private static IReadOnlyList<TripMapPoint> Clip(
        SimplifiedMapGeometry geometry,
        double startMeters,
        double endMeters)
    {
        var start = PointAt(geometry, startMeters);
        var end = PointAt(geometry, endMeters);
        var points = new List<TripMapPoint> { start };
        points.AddRange(geometry.Points
            .Where(point => point.EdgeDistanceMeters > startMeters + GeometryTolerance &&
                point.EdgeDistanceMeters < endMeters - GeometryTolerance)
            .Select(point => new TripMapPoint(point.XMeters, point.YMeters)));
        if (DistanceSquared(points[^1], end) > GeometryTolerance * GeometryTolerance)
        {
            points.Add(end);
        }
        return points;
    }

    private static TripMapPoint PointAt(SimplifiedMapGeometry geometry, double distanceMeters)
    {
        var distance = Math.Clamp(
            distanceMeters,
            geometry.Points[0].EdgeDistanceMeters,
            geometry.Points[^1].EdgeDistanceMeters);
        for (var index = 1; index < geometry.Points.Count; index++)
        {
            var next = geometry.Points[index];
            if (distance > next.EdgeDistanceMeters)
            {
                continue;
            }
            var previous = geometry.Points[index - 1];
            var span = next.EdgeDistanceMeters - previous.EdgeDistanceMeters;
            var fraction = span <= 0 ? 0 : (distance - previous.EdgeDistanceMeters) / span;
            return new TripMapPoint(
                previous.XMeters + ((next.XMeters - previous.XMeters) * fraction),
                previous.YMeters + ((next.YMeters - previous.YMeters) * fraction));
        }
        var last = geometry.Points[^1];
        return new TripMapPoint(last.XMeters, last.YMeters);
    }

    private static double DistanceSquared(TripMapPoint first, TripMapPoint second)
    {
        var x = first.XMeters - second.XMeters;
        var y = first.YMeters - second.YMeters;
        return (x * x) + (y * y);
    }
}
