namespace Cannonball.Core.Routes;

public readonly record struct SourceCoordinate(double Longitude, double Latitude, double ElevationMeters);

public readonly record struct RoutePosition(
    string EdgeId,
    double DistanceMeters,
    int LaneIndex,
    double LateralOffsetMeters,
    double HeadingOffsetRadians)
{
    public RoutePosition Validate(RouteEdge edge)
    {
        if (!string.Equals(EdgeId, edge.Id, StringComparison.Ordinal))
        {
            throw new ArgumentException("Route position belongs to a different edge.", nameof(edge));
        }

        if (DistanceMeters is < 0 || DistanceMeters > edge.LengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(DistanceMeters));
        }

        if (LaneIndex < 0 || LaneIndex >= edge.LaneCount)
        {
            throw new ArgumentOutOfRangeException(nameof(LaneIndex));
        }

        return this;
    }
}

public sealed record RouteNode(
    string Id,
    SourceCoordinate Source,
    string Kind,
    IReadOnlyList<string> OutgoingEdgeIds);

public sealed record RouteEdge(
    string Id,
    string FromNodeId,
    string ToNodeId,
    double LengthMeters,
    int LaneCount,
    double SpeedLimitMetersPerSecond,
    IReadOnlyList<float> CurvatureSamples,
    IReadOnlyList<float> GradeSamples,
    string RegionId,
    string GenerationProfile,
    IReadOnlyList<string> ChunkIds);

public readonly record struct RouteBounds(
    double MinimumLongitude,
    double MinimumLatitude,
    double MaximumLongitude,
    double MaximumLatitude);

public sealed record ChunkManifest(
    string Id,
    string EdgeId,
    double StartMeters,
    double EndMeters,
    string ContentHash,
    string RelativePath,
    RouteBounds Bounds,
    IReadOnlyList<string> ProbableBranchChunkIds);
