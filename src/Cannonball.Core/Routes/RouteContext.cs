using System.Globalization;

namespace Cannonball.Core.Routes;

public enum RouteContextPlacementKind
{
    MileMarker,
    ExitSign,
    HighwayTransferSign,
}

public enum RouteContextMount
{
    LeftRoadside,
    RightRoadside,
    Overhead,
}

public sealed record RouteContextPlacement(
    string Id,
    RouteContextPlacementKind Kind,
    RouteContextMount Mount,
    string EdgeId,
    double DistanceMeters,
    string RouteIdentityId,
    string PrimaryText,
    string SecondaryText,
    string SignedDirection,
    string Jurisdiction,
    string ExitNumber,
    IReadOnlyList<string> RouteShields,
    string LaneGuidance,
    IReadOnlyList<string> LaneIds,
    IReadOnlyList<string> Services,
    RouteSemanticProvenance Provenance,
    bool ExactRouteReference);

public sealed record RouteContextOmission(
    string Id,
    string EdgeId,
    string RouteIdentityId,
    string Reason,
    RouteSemanticProvenance? Provenance);

public sealed record RouteContextPlan(
    IReadOnlyList<RouteContextPlacement> Placements,
    IReadOnlyList<RouteContextOmission> Omissions)
{
    public IReadOnlyList<RouteContextPlacement> ForChunk(
        double startMeters,
        double endMeters,
        bool includeEnd = false)
    {
        if (!double.IsFinite(startMeters) || !double.IsFinite(endMeters) ||
            startMeters < 0 || endMeters < startMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(startMeters));
        }

        return Placements.Where(placement =>
                placement.DistanceMeters >= startMeters &&
                (placement.DistanceMeters < endMeters ||
                    includeEnd && placement.DistanceMeters == endMeters))
            .ToArray();
    }
}

public static class RouteContextPlanner
{
    public const double MinimumSignSeparationMeters = 60;
    public const double MarkerAnchorToleranceMeters = 0.01;
    public const double DeclaredApproachSpeedMetersPerSecond = 60;
    public const double MinimumGuideSignPreviewSeconds = 1.5;

    public static RouteContextPlan BuildForEdge(
        IRouteGraph graph,
        RouteSemanticContent semantics,
        string edgeId)
    {
        ArgumentNullException.ThrowIfNull(graph);
        ArgumentNullException.ThrowIfNull(semantics);
        ArgumentException.ThrowIfNullOrWhiteSpace(edgeId);
        var edge = graph.GetEdge(edgeId);
        var identities = semantics.RouteIdentities.ToDictionary(
            identity => identity.Id,
            StringComparer.Ordinal);
        var placements = new List<RouteContextPlacement>();
        var omissions = new List<RouteContextOmission>();

        AddMileMarkers(edge, semantics, identities, placements, omissions);
        AddExitSigns(graph, edge, semantics, identities, placements, omissions);

        return new RouteContextPlan(
            placements
                .OrderBy(placement => placement.DistanceMeters)
                .ThenBy(placement => placement.Kind)
                .ThenBy(placement => placement.Id, StringComparer.Ordinal)
                .ToArray(),
            omissions
                .OrderBy(omission => omission.Id, StringComparer.Ordinal)
                .ToArray());
    }

    private static void AddMileMarkers(
        RouteEdge edge,
        RouteSemanticContent semantics,
        IReadOnlyDictionary<string, RouteIdentity> identities,
        ICollection<RouteContextPlacement> placements,
        ICollection<RouteContextOmission> omissions)
    {
        var anchors = semantics.MilepointAnchors
            .Where(anchor => string.Equals(anchor.EdgeId, edge.Id, StringComparison.Ordinal))
            .ToArray();
        var markers = semantics.RoadsideMarkers
            .Where(marker =>
                string.Equals(marker.EdgeId, edge.Id, StringComparison.Ordinal) &&
                string.Equals(marker.Kind, "mile", StringComparison.OrdinalIgnoreCase))
            .OrderBy(marker => marker.DistanceMeters)
            .ThenBy(marker => marker.RouteIdentityId, StringComparer.Ordinal)
            .ThenBy(marker => marker.Id, StringComparer.Ordinal)
            .ToArray();

        foreach (var identityId in edge.RouteIdentityIds.OrderBy(id => id, StringComparer.Ordinal))
        {
            if (!anchors.Any(anchor => string.Equals(
                    anchor.RouteIdentityId,
                    identityId,
                    StringComparison.Ordinal)))
            {
                omissions.Add(new RouteContextOmission(
                    $"milepoint-missing:{edge.Id}:{identityId}",
                    edge.Id,
                    identityId,
                    "No exact route-reference milepoint anchor is available; cumulative trip progress was not substituted.",
                    identities.TryGetValue(identityId, out var identity)
                        ? identity.Provenance
                        : null));
            }
        }

        var colocatedIndexes = new Dictionary<long, int>();
        foreach (var marker in markers)
        {
            if (!identities.TryGetValue(marker.RouteIdentityId, out var identity))
            {
                throw new InvalidDataException(
                    $"Roadside marker '{marker.Id}' references unknown identity " +
                    $"'{marker.RouteIdentityId}'.");
            }
            var matchingAnchors = anchors.Where(anchor =>
                    string.Equals(
                        anchor.RouteIdentityId,
                        marker.RouteIdentityId,
                        StringComparison.Ordinal) &&
                    Math.Abs(anchor.DistanceMeters - marker.DistanceMeters) <=
                        MarkerAnchorToleranceMeters)
                .OrderBy(anchor => Math.Abs(anchor.DistanceMeters - marker.DistanceMeters))
                .ThenBy(anchor => anchor.Id, StringComparer.Ordinal)
                .ToArray();
            if (matchingAnchors.Length == 0)
            {
                omissions.Add(new RouteContextOmission(
                    marker.Id,
                    edge.Id,
                    marker.RouteIdentityId,
                    "Marker omitted because no exact colocated milepoint anchor proves its route-reference value.",
                    marker.Provenance));
                continue;
            }
            var anchor = matchingAnchors[0];
            var expectedText = FormatMilepoint(anchor.ValueMiles);
            if (!string.Equals(marker.DisplayText.Trim(), expectedText, StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"Roadside marker '{marker.Id}' displays '{marker.DisplayText}' but its " +
                    $"exact anchor requires '{expectedText}'.");
            }
            if (!string.Equals(
                    identity.SignedDirection,
                    anchor.SignedDirection,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    $"Roadside marker '{marker.Id}' has contradictory route and anchor directions.");
            }

            var positionKey = checked((long)Math.Round(marker.DistanceMeters * 100));
            colocatedIndexes.TryGetValue(positionKey, out var colocatedIndex);
            colocatedIndexes[positionKey] = colocatedIndex + 1;
            placements.Add(new RouteContextPlacement(
                marker.Id,
                RouteContextPlacementKind.MileMarker,
                colocatedIndex % 2 == 0
                    ? RouteContextMount.RightRoadside
                    : RouteContextMount.LeftRoadside,
                edge.Id,
                marker.DistanceMeters,
                identity.Id,
                $"{identity.System} {identity.Number} {anchor.SignedDirection}".ToUpperInvariant(),
                $"MILE {expectedText}",
                anchor.SignedDirection,
                anchor.Jurisdiction,
                string.Empty,
                [FormatRouteShield(identity)],
                string.Empty,
                [],
                [],
                marker.Provenance,
                true));
        }
    }

    private static void AddExitSigns(
        IRouteGraph graph,
        RouteEdge edge,
        RouteSemanticContent semantics,
        IReadOnlyDictionary<string, RouteIdentity> identities,
        ICollection<RouteContextPlacement> placements,
        ICollection<RouteContextOmission> omissions)
    {
        var signDistances = new List<double>();
        foreach (var routeExit in semantics.Exits
                     .Where(candidate => string.Equals(
                         candidate.JunctionNodeId,
                         edge.ToNodeId,
                         StringComparison.Ordinal))
                     .OrderBy(candidate => candidate.Id, StringComparer.Ordinal))
        {
            if (!edge.RouteIdentityIds.Contains(routeExit.RouteIdentityId, StringComparer.Ordinal) ||
                !identities.TryGetValue(routeExit.RouteIdentityId, out var currentIdentity))
            {
                continue;
            }
            var connectors = semantics.JunctionConnectors.Where(connector =>
                    string.Equals(connector.FromEdgeId, edge.Id, StringComparison.Ordinal) &&
                    string.Equals(connector.ToEdgeId, routeExit.RampEdgeId, StringComparison.Ordinal) &&
                    connector.Movement is JunctionMovement.Exit or JunctionMovement.HighwayTransfer)
                .OrderBy(connector => connector.FromLaneId, StringComparer.Ordinal)
                .ToArray();
            if (connectors.Length == 0)
            {
                omissions.Add(new RouteContextOmission(
                    routeExit.Id,
                    edge.Id,
                    routeExit.RouteIdentityId,
                    "Exit sign omitted because no exit or highway-transfer lane connector reaches its ramp.",
                    routeExit.Provenance));
                continue;
            }

            var rampEdge = graph.GetEdge(routeExit.RampEdgeId);
            var isTransfer = connectors.Any(connector =>
                connector.Movement == JunctionMovement.HighwayTransfer);
            var minimumPreviewMeters =
                DeclaredApproachSpeedMetersPerSecond * MinimumGuideSignPreviewSeconds;
            var approach = Math.Clamp(edge.LengthMeters * 0.30, minimumPreviewMeters, 320);
            var distance = edge.LengthMeters - approach;
            while (distance >= 0 && signDistances.Any(existing =>
                       Math.Abs(existing - distance) < MinimumSignSeparationMeters))
            {
                distance -= MinimumSignSeparationMeters;
            }
            if (distance < 0)
            {
                omissions.Add(new RouteContextOmission(
                    routeExit.Id,
                    edge.Id,
                    routeExit.RouteIdentityId,
                    "Guide sign omitted because the approach cannot satisfy deterministic minimum separation and preview distance.",
                    routeExit.Provenance));
                continue;
            }
            signDistances.Add(distance);
            var exitNumber = $"{routeExit.Number}{routeExit.Suffix}";
            var destinationText = string.Join(" / ", routeExit.Destinations);
            var primary = isTransfer
                ? string.IsNullOrWhiteSpace(exitNumber)
                    ? "TO"
                    : $"EXIT {exitNumber} // TO"
                : string.IsNullOrWhiteSpace(exitNumber)
                    ? "EXIT"
                    : $"EXIT {exitNumber}";
            var routeShields = new[] { FormatRouteShield(currentIdentity) }
                .Concat(rampEdge.RouteIdentityIds
                    .Where(identityId => !string.Equals(
                        identityId,
                        currentIdentity.Id,
                        StringComparison.Ordinal))
                    .Select(identityId => identities.TryGetValue(identityId, out var identity)
                        ? $"TO {FormatRouteShield(identity)}"
                        : throw new InvalidDataException(
                            $"Exit '{routeExit.Id}' ramp references unknown route identity " +
                            $"'{identityId}'.")))
                .Distinct(StringComparer.Ordinal)
                .ToArray();
            var laneIds = connectors
                .Select(connector => connector.FromLaneId)
                .Distinct(StringComparer.Ordinal)
                .ToArray();
            placements.Add(new RouteContextPlacement(
                $"sign:{routeExit.Id}",
                isTransfer
                    ? RouteContextPlacementKind.HighwayTransferSign
                    : RouteContextPlacementKind.ExitSign,
                RouteContextMount.Overhead,
                edge.Id,
                distance,
                currentIdentity.Id,
                primary.ToUpperInvariant(),
                destinationText.ToUpperInvariant(),
                currentIdentity.SignedDirection,
                string.Empty,
                exitNumber,
                routeShields,
                FormatLaneGuidance(edge, laneIds),
                laneIds,
                routeExit.Services,
                routeExit.Provenance,
                true));
        }
    }

    public static string FormatMilepoint(double valueMiles)
    {
        if (!double.IsFinite(valueMiles))
        {
            throw new ArgumentOutOfRangeException(nameof(valueMiles));
        }
        return valueMiles.ToString("0.###", CultureInfo.InvariantCulture);
    }

    private static string FormatRouteShield(RouteIdentity identity) =>
        $"{identity.System} {identity.Number} {identity.SignedDirection}".ToUpperInvariant();

    private static string FormatLaneGuidance(RouteEdge edge, IReadOnlyCollection<string> laneIds)
    {
        var lanes = edge.GetLaneSection(edge.LengthMeters).Lanes
            .OrderBy(lane => lane.Index)
            .ToArray();
        var selected = lanes
            .Where(lane => laneIds.Contains(lane.Id, StringComparer.Ordinal))
            .ToArray();
        if (selected.Length != laneIds.Count)
        {
            throw new InvalidDataException(
                $"Guide-sign connector on edge '{edge.Id}' references an unknown approach lane.");
        }

        var selectedIndexes = selected.Select(lane => lane.Index).Order().ToArray();
        var contiguous = selectedIndexes.Zip(selectedIndexes.Skip(1))
            .All(pair => pair.Second == pair.First + 1);
        var label = selected.Length == 1 ? "LANE" : "LANES";
        if (contiguous && selectedIndexes[^1] == lanes.Max(lane => lane.Index))
        {
            return selected.Length == 1 ? "RIGHT LANE" : $"RIGHT {selected.Length} {label}";
        }
        if (contiguous && selectedIndexes[0] == lanes.Min(lane => lane.Index))
        {
            return selected.Length == 1 ? "LEFT LANE" : $"LEFT {selected.Length} {label}";
        }
        return $"{label} {string.Join('-', selectedIndexes.Select(index => index + 1))}";
    }
}
