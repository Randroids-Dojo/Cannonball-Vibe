using Cannonball.Content;
using Cannonball.Core.Routes;

namespace Cannonball.Core.Content;

internal static class FlatBufferRouteSemantics
{
    private const LaneManeuver AllManeuvers =
        LaneManeuver.Continue |
        LaneManeuver.Merge |
        LaneManeuver.Split |
        LaneManeuver.Exit |
        LaneManeuver.Entrance |
        LaneManeuver.HighwayTransfer;

    public static (RouteEdge[] Edges, RouteSemanticContent Semantics) Load(
        RouteGraphBufferT root,
        IReadOnlyList<RouteNode> nodes,
        IReadOnlyList<RouteEdge> sourceEdges)
    {
        if (nodes.Select(node => node.Id).Distinct(StringComparer.Ordinal).Count() != nodes.Count ||
            sourceEdges.Select(edge => edge.Id).Distinct(StringComparer.Ordinal).Count() !=
                sourceEdges.Count)
        {
            throw new InvalidDataException(
                "Route semantics cannot validate duplicate node or edge IDs.");
        }
        var nodesById = nodes.ToDictionary(node => node.Id, StringComparer.Ordinal);
        var sourceEdgesById = sourceEdges.ToDictionary(edge => edge.Id, StringComparer.Ordinal);
        var identities = ReadIdentities(root.RouteIdentities);
        var sections = ReadSections(root.LaneSections, sourceEdgesById);
        var sectionsByEdge = sections
            .GroupBy(section => section.EdgeId, StringComparer.Ordinal)
            .ToDictionary(
                group => group.Key,
                group => group.OrderBy(section => section.StartMeters).ToArray(),
                StringComparer.Ordinal);

        var edgeDataById = (root.Edges ?? [])
            .ToDictionary(data => Required(data.Id, "edge ID"), StringComparer.Ordinal);
        var updatedEdges = new RouteEdge[sourceEdges.Count];
        for (var index = 0; index < sourceEdges.Count; index++)
        {
            var edge = sourceEdges[index];
            if (!sectionsByEdge.TryGetValue(edge.Id, out var edgeSections) || edgeSections.Length == 0)
            {
                throw new InvalidDataException($"Route schema 4 edge '{edge.Id}' has no lane sections.");
            }
            ValidateSectionCoverage(edge, edgeSections);
            var maximumLaneCount = edgeSections.Max(section => section.Lanes.Count);
            if (maximumLaneCount != edge.LaneCount)
            {
                throw new InvalidDataException(
                    $"Route edge '{edge.Id}' lane count does not match its lane sections.");
            }

            var edgeData = edgeDataById[edge.Id];
            var referencedSectionIds = (edgeData.LaneSectionIds ?? []).ToArray();
            var expectedSectionIds = edgeSections.Select(section => section.Id).ToArray();
            if (!referencedSectionIds.SequenceEqual(expectedSectionIds, StringComparer.Ordinal))
            {
                throw new InvalidDataException(
                    $"Route edge '{edge.Id}' lane-section references are not canonical.");
            }

            var routeIdentityIds = (edgeData.RouteIdentityIds ?? []).ToArray();
            if (routeIdentityIds.Length == 0 || routeIdentityIds.Any(id => !identities.ContainsKey(id)))
            {
                throw new InvalidDataException(
                    $"Route edge '{edge.Id}' has a missing or unknown route identity.");
            }
            updatedEdges[index] = edge with
            {
                LaneSections = edgeSections,
                RouteIdentityIds = routeIdentityIds,
            };
        }

        var updatedEdgesById = updatedEdges.ToDictionary(edge => edge.Id, StringComparer.Ordinal);
        var connectors = ReadAndValidateConnectors(
            root.JunctionConnectors,
            nodesById,
            updatedEdgesById);
        var exits = ReadExits(root.Exits, nodesById, updatedEdgesById, identities);
        var anchors = ReadAnchors(root.MilepointAnchors, updatedEdgesById, identities);
        var markers = ReadMarkers(root.RoadsideMarkers, updatedEdgesById, identities);
        var mapGeometry = ReadAndValidateMapGeometry(
            root.SimplifiedMapGeometry,
            updatedEdgesById);

        return (
            updatedEdges,
            new RouteSemanticContent(
                sections,
                connectors,
                identities.Values.OrderBy(identity => identity.Id, StringComparer.Ordinal).ToArray(),
                exits,
                anchors,
                markers,
                mapGeometry,
                false));
    }

    private static Dictionary<string, RouteIdentity> ReadIdentities(
        IReadOnlyList<RouteIdentityDataT>? values)
    {
        var result = new Dictionary<string, RouteIdentity>(StringComparer.Ordinal);
        foreach (var value in values ?? [])
        {
            var id = Required(value.Id, "route identity ID");
            var identity = new RouteIdentity(
                id,
                Required(value.System, $"route identity '{id}' system"),
                Required(value.Number, $"route identity '{id}' number"),
                Required(value.Shield, $"route identity '{id}' shield"),
                Required(value.SignedDirection, $"route identity '{id}' signed direction"),
                value.LocalName ?? string.Empty,
                ReadProvenance(value.Provenance, $"route identity '{id}'"));
            AddUnique(result, id, identity, "route identity");
        }
        if (result.Count == 0)
        {
            throw new InvalidDataException("Route schema 4 has no route identities.");
        }
        return result;
    }

    private static LaneSection[] ReadSections(
        IReadOnlyList<LaneSectionDataT>? values,
        IReadOnlyDictionary<string, RouteEdge> edges)
    {
        var result = new Dictionary<string, LaneSection>(StringComparer.Ordinal);
        foreach (var value in values ?? [])
        {
            var id = Required(value.Id, "lane section ID");
            var edgeId = Required(value.EdgeId, $"lane section '{id}' edge ID");
            if (!edges.TryGetValue(edgeId, out var edge))
            {
                throw new InvalidDataException(
                    $"Lane section '{id}' references unknown edge '{edgeId}'.");
            }
            if (!double.IsFinite(value.StartMeters) || !double.IsFinite(value.EndMeters) ||
                value.StartMeters < 0 || value.EndMeters <= value.StartMeters ||
                value.EndMeters > edge.LengthMeters)
            {
                throw new InvalidDataException($"Lane section '{id}' has an invalid distance range.");
            }
            var lanes = ReadLanes(value.Lanes, id);
            var section = new LaneSection(
                id,
                edgeId,
                value.StartMeters,
                value.EndMeters,
                lanes,
                ReadShoulder(value.LeftShoulder, $"lane section '{id}' left shoulder"),
                ReadShoulder(value.RightShoulder, $"lane section '{id}' right shoulder"),
                Required(value.SignedDirection, $"lane section '{id}' signed direction"),
                ReadProvenance(value.Provenance, $"lane section '{id}'"));
            AddUnique(result, id, section, "lane section");
        }
        return result.Values
            .OrderBy(section => section.EdgeId, StringComparer.Ordinal)
            .ThenBy(section => section.StartMeters)
            .ThenBy(section => section.Id, StringComparer.Ordinal)
            .ToArray();
    }

    private static RouteLane[] ReadLanes(IReadOnlyList<RouteLaneDataT>? values, string sectionId)
    {
        if (values is null || values.Count == 0)
        {
            throw new InvalidDataException($"Lane section '{sectionId}' has no lanes.");
        }
        var laneIds = new HashSet<string>(StringComparer.Ordinal);
        var laneIndexes = new HashSet<int>();
        var lanes = new RouteLane[values.Count];
        for (var index = 0; index < values.Count; index++)
        {
            var value = values[index];
            var id = Required(value.Id, $"lane section '{sectionId}' lane ID");
            var laneIndex = checked((int)value.Index);
            var maneuvers = (LaneManeuver)value.AllowedManeuvers;
            if (!float.IsFinite(value.WidthMeters) || value.WidthMeters <= 0 ||
                maneuvers == 0 || (maneuvers & ~AllManeuvers) != 0)
            {
                throw new InvalidDataException($"Route lane '{id}' has invalid dimensions or maneuvers.");
            }
            if (!laneIds.Add(id) || !laneIndexes.Add(laneIndex))
            {
                throw new InvalidDataException(
                    $"Lane section '{sectionId}' repeats a lane ID or index.");
            }
            lanes[index] = new RouteLane(
                id,
                laneIndex,
                value.WidthMeters,
                ParseLaneRole(value.Role, id),
                maneuvers,
                ReadProvenance(value.Provenance, $"lane '{id}'"));
        }
        if (!laneIndexes.SetEquals(Enumerable.Range(0, lanes.Length)))
        {
            throw new InvalidDataException(
                $"Lane section '{sectionId}' indexes must be contiguous from zero.");
        }
        return lanes.OrderBy(lane => lane.Index).ToArray();
    }

    private static void ValidateSectionCoverage(RouteEdge edge, IReadOnlyList<LaneSection> sections)
    {
        var expectedStart = 0.0;
        foreach (var section in sections)
        {
            if (!ApproximatelyEqual(section.StartMeters, expectedStart))
            {
                throw new InvalidDataException(
                    $"Route edge '{edge.Id}' lane sections have a gap or overlap.");
            }
            expectedStart = section.EndMeters;
        }
        if (!ApproximatelyEqual(expectedStart, edge.LengthMeters))
        {
            throw new InvalidDataException(
                $"Route edge '{edge.Id}' lane sections do not cover its complete length.");
        }
    }

    private static JunctionConnector[] ReadAndValidateConnectors(
        IReadOnlyList<JunctionConnectorDataT>? values,
        IReadOnlyDictionary<string, RouteNode> nodes,
        IReadOnlyDictionary<string, RouteEdge> edges)
    {
        var result = new Dictionary<string, JunctionConnector>(StringComparer.Ordinal);
        var successorKeys = new HashSet<(string FromEdge, string FromLane, string ToEdge)>();
        var crossingGroups = new Dictionary<(string FromEdge, string ToEdge), List<(int From, int To)>>();
        var incomingCoverage = new HashSet<(string Edge, string Lane)>();
        var outgoingCoverage = new HashSet<(string Edge, string Lane)>();
        foreach (var value in values ?? [])
        {
            var id = Required(value.Id, "junction connector ID");
            var nodeId = Required(value.JunctionNodeId, $"connector '{id}' junction node");
            var fromEdgeId = Required(value.FromEdgeId, $"connector '{id}' from edge");
            var toEdgeId = Required(value.ToEdgeId, $"connector '{id}' to edge");
            var fromLaneId = Required(value.FromLaneId, $"connector '{id}' from lane");
            var toLaneId = Required(value.ToLaneId, $"connector '{id}' to lane");
            if (!nodes.ContainsKey(nodeId) || !edges.TryGetValue(fromEdgeId, out var fromEdge) ||
                !edges.TryGetValue(toEdgeId, out var toEdge))
            {
                throw new InvalidDataException($"Connector '{id}' references an unknown node or edge.");
            }
            if (fromEdge.ToNodeId != nodeId || toEdge.FromNodeId != nodeId)
            {
                throw new InvalidDataException(
                    $"Connector '{id}' does not meet at its declared junction.");
            }
            var fromLane = fromEdge.GetEffectiveLaneSections().Last().Lanes
                .SingleOrDefault(lane => lane.Id == fromLaneId);
            var toLane = toEdge.GetEffectiveLaneSections().First().Lanes
                .SingleOrDefault(lane => lane.Id == toLaneId);
            if (fromLane is null || toLane is null)
            {
                throw new InvalidDataException($"Connector '{id}' references an orphan lane.");
            }
            var movement = ParseMovement(value.Movement, id);
            if (!fromLane.AllowedManeuvers.HasFlag(ManeuverForMovement(movement)))
            {
                throw new InvalidDataException(
                    $"Connector '{id}' movement is not allowed by lane '{fromLaneId}'.");
            }
            if (!successorKeys.Add((fromEdgeId, fromLaneId, toEdgeId)))
            {
                throw new InvalidDataException(
                    $"Connector '{id}' creates an ambiguous lane successor.");
            }
            var pair = (fromEdgeId, toEdgeId);
            if (!crossingGroups.TryGetValue(pair, out var lanePairs))
            {
                lanePairs = [];
                crossingGroups.Add(pair, lanePairs);
            }
            lanePairs.Add((fromLane.Index, toLane.Index));
            incomingCoverage.Add((fromEdgeId, fromLaneId));
            outgoingCoverage.Add((toEdgeId, toLaneId));
            AddUnique(
                result,
                id,
                new JunctionConnector(
                    id,
                    nodeId,
                    fromEdgeId,
                    fromLaneId,
                    toEdgeId,
                    toLaneId,
                    movement,
                    ReadProvenance(value.Provenance, $"connector '{id}'")),
                "junction connector");
        }

        foreach (var (pair, lanePairs) in crossingGroups)
        {
            var ordered = lanePairs.OrderBy(item => item.From).ThenBy(item => item.To).ToArray();
            if (ordered.Zip(ordered.Skip(1)).Any(item => item.Second.To < item.First.To))
            {
                throw new InvalidDataException(
                    $"Connectors between '{pair.FromEdge}' and '{pair.ToEdge}' cross lanes.");
            }
        }

        var incomingByNode = edges.Values.GroupBy(edge => edge.ToNodeId, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.ToArray(), StringComparer.Ordinal);
        var outgoingByNode = edges.Values.GroupBy(edge => edge.FromNodeId, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.ToArray(), StringComparer.Ordinal);
        foreach (var nodeId in incomingByNode.Keys.Intersect(outgoingByNode.Keys, StringComparer.Ordinal))
        {
            foreach (var edge in incomingByNode[nodeId])
            {
                foreach (var lane in edge.GetEffectiveLaneSections().Last().Lanes)
                {
                    if (!incomingCoverage.Contains((edge.Id, lane.Id)))
                    {
                        throw new InvalidDataException(
                            $"Junction '{nodeId}' leaves incoming lane '{lane.Id}' orphaned.");
                    }
                }
            }
            foreach (var edge in outgoingByNode[nodeId])
            {
                foreach (var lane in edge.GetEffectiveLaneSections().First().Lanes)
                {
                    if (!outgoingCoverage.Contains((edge.Id, lane.Id)))
                    {
                        throw new InvalidDataException(
                            $"Junction '{nodeId}' leaves outgoing lane '{lane.Id}' orphaned.");
                    }
                }
            }
        }

        return result.Values.OrderBy(connector => connector.Id, StringComparer.Ordinal).ToArray();
    }

    private static RouteExit[] ReadExits(
        IReadOnlyList<ExitDataT>? values,
        IReadOnlyDictionary<string, RouteNode> nodes,
        IReadOnlyDictionary<string, RouteEdge> edges,
        IReadOnlyDictionary<string, RouteIdentity> identities)
    {
        var result = new Dictionary<string, RouteExit>(StringComparer.Ordinal);
        foreach (var value in values ?? [])
        {
            var id = Required(value.Id, "exit ID");
            var nodeId = Required(value.JunctionNodeId, $"exit '{id}' junction node");
            var rampEdgeId = Required(value.RampEdgeId, $"exit '{id}' ramp edge");
            var identityId = Required(value.RouteIdentityId, $"exit '{id}' route identity");
            if (!nodes.ContainsKey(nodeId) || !edges.TryGetValue(rampEdgeId, out var ramp) ||
                ramp.FromNodeId != nodeId || !identities.ContainsKey(identityId))
            {
                throw new InvalidDataException($"Exit '{id}' has an invalid junction, ramp, or route identity.");
            }
            var destinations = RequiredStringList(value.Destinations, $"exit '{id}' destinations");
            var services = RequiredStringList(value.Services, $"exit '{id}' services");
            if (string.IsNullOrWhiteSpace(value.Number) && destinations.Length == 0)
            {
                throw new InvalidDataException($"Exit '{id}' needs a number or destination.");
            }
            AddUnique(
                result,
                id,
                new RouteExit(
                    id,
                    nodeId,
                    rampEdgeId,
                    identityId,
                    value.Number ?? string.Empty,
                    value.Suffix ?? string.Empty,
                    destinations,
                    services,
                    ReadProvenance(value.Provenance, $"exit '{id}'")),
                "exit");
        }
        return result.Values.OrderBy(item => item.Id, StringComparer.Ordinal).ToArray();
    }

    private static MilepointAnchor[] ReadAnchors(
        IReadOnlyList<MilepointAnchorDataT>? values,
        IReadOnlyDictionary<string, RouteEdge> edges,
        IReadOnlyDictionary<string, RouteIdentity> identities)
    {
        var result = new Dictionary<string, MilepointAnchor>(StringComparer.Ordinal);
        foreach (var value in values ?? [])
        {
            var id = Required(value.Id, "milepoint anchor ID");
            var edgeId = Required(value.EdgeId, $"milepoint anchor '{id}' edge");
            var identityId = Required(value.RouteIdentityId, $"milepoint anchor '{id}' route identity");
            if (!edges.TryGetValue(edgeId, out var edge) || !identities.ContainsKey(identityId) ||
                !double.IsFinite(value.DistanceMeters) || value.DistanceMeters < 0 ||
                value.DistanceMeters > edge.LengthMeters || !double.IsFinite(value.ValueMiles))
            {
                throw new InvalidDataException($"Milepoint anchor '{id}' has invalid route placement.");
            }
            AddUnique(
                result,
                id,
                new MilepointAnchor(
                    id,
                    identityId,
                    edgeId,
                    value.DistanceMeters,
                    value.ValueMiles,
                    Required(value.Jurisdiction, $"milepoint anchor '{id}' jurisdiction"),
                    Required(value.SignedDirection, $"milepoint anchor '{id}' signed direction"),
                    ReadProvenance(value.Provenance, $"milepoint anchor '{id}'")),
                "milepoint anchor");
        }
        return result.Values.OrderBy(item => item.Id, StringComparer.Ordinal).ToArray();
    }

    private static RoadsideMarker[] ReadMarkers(
        IReadOnlyList<RoadsideMarkerDataT>? values,
        IReadOnlyDictionary<string, RouteEdge> edges,
        IReadOnlyDictionary<string, RouteIdentity> identities)
    {
        var result = new Dictionary<string, RoadsideMarker>(StringComparer.Ordinal);
        foreach (var value in values ?? [])
        {
            var id = Required(value.Id, "roadside marker ID");
            var edgeId = Required(value.EdgeId, $"roadside marker '{id}' edge");
            var identityId = Required(value.RouteIdentityId, $"roadside marker '{id}' route identity");
            if (!edges.TryGetValue(edgeId, out var edge) || !identities.ContainsKey(identityId) ||
                !double.IsFinite(value.DistanceMeters) || value.DistanceMeters < 0 ||
                value.DistanceMeters > edge.LengthMeters)
            {
                throw new InvalidDataException($"Roadside marker '{id}' has invalid route placement.");
            }
            AddUnique(
                result,
                id,
                new RoadsideMarker(
                    id,
                    Required(value.Kind, $"roadside marker '{id}' kind"),
                    identityId,
                    edgeId,
                    value.DistanceMeters,
                    Required(value.DisplayText, $"roadside marker '{id}' display text"),
                    ReadProvenance(value.Provenance, $"roadside marker '{id}'")),
                "roadside marker");
        }
        return result.Values.OrderBy(item => item.Id, StringComparer.Ordinal).ToArray();
    }

    private static SimplifiedMapGeometry[] ReadAndValidateMapGeometry(
        IReadOnlyList<SimplifiedMapGeometryDataT>? values,
        IReadOnlyDictionary<string, RouteEdge> edges)
    {
        var result = new Dictionary<(string EdgeId, int Lod), SimplifiedMapGeometry>();
        long byteCount = 0;
        foreach (var value in values ?? [])
        {
            var edgeId = Required(value.EdgeId, "simplified map edge ID");
            var lod = checked((int)value.Lod);
            if (!edges.TryGetValue(edgeId, out var edge) || lod < 0)
            {
                throw new InvalidDataException("Simplified map geometry has an invalid edge or LOD.");
            }
            var points = (value.Points ?? [])
                .Select(point => new Routes.SimplifiedMapPoint(
                    point.XMeters,
                    point.YMeters,
                    point.EdgeDistanceMeters))
                .ToArray();
            if (points.Length < 2 || points.Any(point =>
                    !double.IsFinite(point.XMeters) ||
                    !double.IsFinite(point.YMeters) ||
                    !double.IsFinite(point.EdgeDistanceMeters)) ||
                points.Zip(points.Skip(1)).Any(pair =>
                    pair.Second.EdgeDistanceMeters <= pair.First.EdgeDistanceMeters) ||
                !ApproximatelyEqual(points[0].EdgeDistanceMeters, 0) ||
                !ApproximatelyEqual(points[^1].EdgeDistanceMeters, edge.LengthMeters))
            {
                throw new InvalidDataException(
                    $"Simplified map geometry '{edgeId}' LOD {lod} has invalid points.");
            }
            var hash = RequiredSha256(value.ContentHash, "simplified map geometry hash");
            if (hash != RouteSemanticsCompatibility.ComputeMapGeometryHash(edgeId, lod, points))
            {
                throw new InvalidDataException(
                    $"Simplified map geometry '{edgeId}' LOD {lod} hash is invalid.");
            }
            byteCount += 4L + System.Text.Encoding.UTF8.GetByteCount(edgeId) + 8L + points.Length * 24L;
            if (!result.TryAdd((edgeId, lod), new SimplifiedMapGeometry(edgeId, lod, points, hash)))
            {
                throw new InvalidDataException(
                    $"Simplified map geometry repeats edge '{edgeId}' LOD {lod}.");
            }
        }
        var expectedKeys = edges.Keys.SelectMany(edgeId => Enumerable.Range(0, 3)
            .Select(lod => (edgeId, lod))).ToHashSet();
        if (!result.Keys.ToHashSet().SetEquals(expectedKeys))
        {
            throw new InvalidDataException(
                "Simplified map geometry must contain LODs 0, 1, and 2 for every edge.");
        }
        if (byteCount >= RouteSemanticsCompatibility.MaximumSimplifiedMapBytes)
        {
            throw new InvalidDataException("Simplified map geometry exceeds the 16 MB package budget.");
        }
        return result.Values
            .OrderBy(item => item.EdgeId, StringComparer.Ordinal)
            .ThenBy(item => item.Lod)
            .ToArray();
    }

    private static RouteSemanticProvenance ReadProvenance(
        SemanticProvenanceDataT? value,
        string context)
    {
        if (value is null)
        {
            throw new InvalidDataException($"Route {context} is missing provenance.");
        }
        var kind = value.Kind switch
        {
            "source" => SemanticProvenanceKind.Source,
            "derived" => SemanticProvenanceKind.Derived,
            "authored_override" => SemanticProvenanceKind.AuthoredOverride,
            _ => throw new InvalidDataException(
                $"Route {context} has unknown provenance kind '{value.Kind}'."),
        };
        var derivation = value.Derivation ?? string.Empty;
        var overrideId = value.AuthoredOverrideId ?? string.Empty;
        if (kind == SemanticProvenanceKind.Derived && string.IsNullOrWhiteSpace(derivation))
        {
            throw new InvalidDataException($"Route {context} derived provenance has no recipe.");
        }
        if (kind == SemanticProvenanceKind.AuthoredOverride && string.IsNullOrWhiteSpace(overrideId))
        {
            throw new InvalidDataException($"Route {context} authored provenance has no override ID.");
        }
        return new RouteSemanticProvenance(
            kind,
            Required(value.SourceId, $"{context} provenance source ID"),
            Required(value.SourceRecordId, $"{context} provenance source record"),
            RequiredSha256(value.ArtifactSha256, $"{context} provenance artifact hash"),
            derivation,
            overrideId);
    }

    private static RouteShoulder ReadShoulder(RouteShoulderDataT? value, string context)
    {
        if (value is null || !float.IsFinite(value.WidthMeters) || value.WidthMeters < 0)
        {
            throw new InvalidDataException($"Route {context} is missing or invalid.");
        }
        return new RouteShoulder(value.WidthMeters, Required(value.Kind, $"{context} kind"));
    }

    private static LaneRole ParseLaneRole(string? value, string laneId) => value switch
    {
        "general" => LaneRole.General,
        "auxiliary" => LaneRole.Auxiliary,
        "exit_only" => LaneRole.ExitOnly,
        "entrance_only" => LaneRole.EntranceOnly,
        "managed" => LaneRole.Managed,
        _ => throw new InvalidDataException($"Route lane '{laneId}' has unknown role '{value}'."),
    };

    private static JunctionMovement ParseMovement(string? value, string connectorId) => value switch
    {
        "continuation" => JunctionMovement.Continuation,
        "merge" => JunctionMovement.Merge,
        "split" => JunctionMovement.Split,
        "exit" => JunctionMovement.Exit,
        "entrance" => JunctionMovement.Entrance,
        "highway_transfer" => JunctionMovement.HighwayTransfer,
        _ => throw new InvalidDataException(
            $"Route connector '{connectorId}' has unknown movement '{value}'."),
    };

    private static LaneManeuver ManeuverForMovement(JunctionMovement movement) => movement switch
    {
        JunctionMovement.Continuation => LaneManeuver.Continue,
        JunctionMovement.Merge => LaneManeuver.Merge,
        JunctionMovement.Split => LaneManeuver.Split,
        JunctionMovement.Exit => LaneManeuver.Exit,
        JunctionMovement.Entrance => LaneManeuver.Entrance,
        JunctionMovement.HighwayTransfer => LaneManeuver.HighwayTransfer,
        _ => throw new ArgumentOutOfRangeException(nameof(movement)),
    };

    private static string[] RequiredStringList(
        IReadOnlyList<string>? values,
        string context)
    {
        var result = (values ?? []).ToArray();
        if (result.Any(string.IsNullOrWhiteSpace))
        {
            throw new InvalidDataException($"Route {context} contains an empty value.");
        }
        return result;
    }

    private static bool ApproximatelyEqual(double first, double second) =>
        Math.Abs(first - second) <= 1e-9;

    private static void AddUnique<T>(
        IDictionary<string, T> values,
        string id,
        T value,
        string label)
    {
        if (!values.TryAdd(id, value))
        {
            throw new InvalidDataException($"Route semantics repeats {label} ID '{id}'.");
        }
    }

    private static string Required(string? value, string description) =>
        string.IsNullOrWhiteSpace(value)
            ? throw new InvalidDataException($"Route content is missing {description}.")
            : value;

    private static string RequiredSha256(string? value, string description)
    {
        var digest = Required(value, description);
        if (digest.Length != 64 || digest.Any(character =>
                !char.IsAsciiHexDigit(character) || char.IsAsciiLetterUpper(character)))
        {
            throw new InvalidDataException($"Route content has an invalid {description}.");
        }
        return digest;
    }
}
