using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

namespace Cannonball.Core.Routes;

[Flags]
public enum LaneManeuver : uint
{
    Continue = 1 << 0,
    Merge = 1 << 1,
    Split = 1 << 2,
    Exit = 1 << 3,
    Entrance = 1 << 4,
    HighwayTransfer = 1 << 5,
}

public enum LaneRole
{
    General,
    Auxiliary,
    ExitOnly,
    EntranceOnly,
    Managed,
}

public enum JunctionMovement
{
    Continuation,
    Merge,
    Split,
    Exit,
    Entrance,
    HighwayTransfer,
}

public enum SemanticProvenanceKind
{
    Source,
    Derived,
    AuthoredOverride,
}

public sealed record RouteSemanticProvenance(
    SemanticProvenanceKind Kind,
    string SourceId,
    string SourceRecordId,
    string ArtifactSha256,
    string Derivation,
    string AuthoredOverrideId);

public sealed record RouteShoulder(float WidthMeters, string Kind);

public sealed record RouteLane(
    string Id,
    int Index,
    float WidthMeters,
    LaneRole Role,
    LaneManeuver AllowedManeuvers,
    RouteSemanticProvenance Provenance);

public sealed record LaneSection(
    string Id,
    string EdgeId,
    double StartMeters,
    double EndMeters,
    IReadOnlyList<RouteLane> Lanes,
    RouteShoulder LeftShoulder,
    RouteShoulder RightShoulder,
    string SignedDirection,
    RouteSemanticProvenance Provenance);

public sealed record JunctionConnector(
    string Id,
    string JunctionNodeId,
    string FromEdgeId,
    string FromLaneId,
    string ToEdgeId,
    string ToLaneId,
    JunctionMovement Movement,
    RouteSemanticProvenance Provenance);

public sealed record RouteIdentity(
    string Id,
    string System,
    string Number,
    string Shield,
    string SignedDirection,
    string LocalName,
    RouteSemanticProvenance Provenance);

public sealed record RouteExit(
    string Id,
    string JunctionNodeId,
    string RampEdgeId,
    string RouteIdentityId,
    string Number,
    string Suffix,
    IReadOnlyList<string> Destinations,
    IReadOnlyList<string> Services,
    RouteSemanticProvenance Provenance);

public sealed record MilepointAnchor(
    string Id,
    string RouteIdentityId,
    string EdgeId,
    double DistanceMeters,
    double ValueMiles,
    string Jurisdiction,
    string SignedDirection,
    RouteSemanticProvenance Provenance);

public sealed record RoadsideMarker(
    string Id,
    string Kind,
    string RouteIdentityId,
    string EdgeId,
    double DistanceMeters,
    string DisplayText,
    RouteSemanticProvenance Provenance);

public readonly record struct SimplifiedMapPoint(
    double XMeters,
    double YMeters,
    double EdgeDistanceMeters);

public sealed record SimplifiedMapGeometry(
    string EdgeId,
    int Lod,
    IReadOnlyList<SimplifiedMapPoint> Points,
    string ContentHash);

public sealed record RouteSemanticContent(
    IReadOnlyList<LaneSection> LaneSections,
    IReadOnlyList<JunctionConnector> JunctionConnectors,
    IReadOnlyList<RouteIdentity> RouteIdentities,
    IReadOnlyList<RouteExit> Exits,
    IReadOnlyList<MilepointAnchor> MilepointAnchors,
    IReadOnlyList<RoadsideMarker> RoadsideMarkers,
    IReadOnlyList<SimplifiedMapGeometry> SimplifiedMapGeometry,
    bool IsLegacySynthesis);

public static class RoutePositionMigration
{
    public static RoutePosition Migrate(RoutePosition position, RouteEdge targetEdge)
    {
        if (!string.Equals(position.EdgeId, targetEdge.Id, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Cannot migrate route position on edge '{position.EdgeId}' to '{targetEdge.Id}'.");
        }

        var section = targetEdge.GetLaneSection(position.DistanceMeters);
        RouteLane? lane = null;
        if (!string.IsNullOrWhiteSpace(position.StableLaneId))
        {
            lane = section.Lanes.SingleOrDefault(candidate =>
                string.Equals(candidate.Id, position.StableLaneId, StringComparison.Ordinal));
            if (lane is null)
            {
                throw new InvalidDataException(
                    $"Cannot migrate lane '{position.StableLaneId}' on edge '{position.EdgeId}' " +
                    $"at {position.DistanceMeters:F3} meters; no deterministic lane mapping exists.");
            }
        }
        else
        {
            lane = section.Lanes.SingleOrDefault(candidate => candidate.Index == position.LaneIndex);
            if (lane is null)
            {
                throw new InvalidDataException(
                    $"Cannot migrate legacy lane index {position.LaneIndex} on edge " +
                    $"'{position.EdgeId}' at {position.DistanceMeters:F3} meters.");
            }
        }

        return position with { LaneIndex = lane.Index, StableLaneId = lane.Id };
    }
}

public static class RouteSemanticsCompatibility
{
    public const int MaximumSimplifiedMapBytes = 16_000_000;

    public static IReadOnlyList<LaneSection> GetEffectiveLaneSections(this RouteEdge edge) =>
        edge.LaneSections.Count > 0 ? edge.LaneSections : [CreateLegacyLaneSection(edge)];

    public static RouteSemanticContent CreateLegacyContent(IEnumerable<RouteEdge> edges)
    {
        var sections = edges.Select(CreateLegacyLaneSection).ToArray();
        return new RouteSemanticContent(sections, [], [], [], [], [], [], true);
    }

    public static LaneSection GetLaneSection(this RouteEdge edge, double distanceMeters)
    {
        if (!double.IsFinite(distanceMeters) || distanceMeters < 0 || distanceMeters > edge.LengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(distanceMeters));
        }

        var sections = edge.GetEffectiveLaneSections();
        return sections.Single(section =>
            distanceMeters >= section.StartMeters &&
            (distanceMeters < section.EndMeters ||
             (distanceMeters == edge.LengthMeters && section.EndMeters == edge.LengthMeters)));
    }

    public static string ComputeMapGeometryHash(
        string edgeId,
        int lod,
        IReadOnlyList<SimplifiedMapPoint> points)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(edgeId);
        var edgeBytes = Encoding.UTF8.GetBytes(edgeId);
        using var stream = new MemoryStream();
        Span<byte> integer = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32LittleEndian(integer, checked((uint)edgeBytes.Length));
        stream.Write(integer);
        stream.Write(edgeBytes);
        BinaryPrimitives.WriteUInt32LittleEndian(integer, checked((uint)lod));
        stream.Write(integer);
        BinaryPrimitives.WriteUInt32LittleEndian(integer, checked((uint)points.Count));
        stream.Write(integer);
        Span<byte> number = stackalloc byte[8];
        foreach (var point in points)
        {
            WriteDouble(stream, number, point.XMeters);
            WriteDouble(stream, number, point.YMeters);
            WriteDouble(stream, number, point.EdgeDistanceMeters);
        }

        return Convert.ToHexString(SHA256.HashData(stream.ToArray())).ToLowerInvariant();
    }

    private static void WriteDouble(Stream stream, Span<byte> buffer, double value)
    {
        BinaryPrimitives.WriteInt64LittleEndian(buffer, BitConverter.DoubleToInt64Bits(value));
        stream.Write(buffer);
    }

    public static LaneSection CreateLegacyLaneSection(RouteEdge edge)
    {
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.Derived,
            "legacy-package",
            edge.Id,
            new string('0', 64),
            "Synthesized deterministically from the legacy edge lane count.",
            string.Empty);
        return new LaneSection(
            $"legacy:{edge.Id}:section:0",
            edge.Id,
            0,
            edge.LengthMeters,
            Enumerable.Range(0, edge.LaneCount)
                .Select(index => new RouteLane(
                    $"legacy:{edge.Id}:lane:{index}",
                    index,
                    3.6f,
                    LaneRole.General,
                    LaneManeuver.Continue,
                    provenance))
                .ToArray(),
            new RouteShoulder(0, "unknown"),
            new RouteShoulder(0, "unknown"),
            "unspecified",
            provenance);
    }
}
