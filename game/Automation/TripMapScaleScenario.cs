using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Simulation;
using System.Diagnostics;

namespace Cannonball.Game.Automation;

public sealed record TripMapScaleProfileResult(
    int EdgeCount,
    double RouteDistanceMiles,
    int GeometryLod,
    int ProjectedPointCount,
    double ProjectionMilliseconds,
    double RealTimeEstimateSeconds,
    double FixedCompressionEstimateSeconds,
    double SelectiveCruiseEstimateSeconds);

public static class TripMapScaleScenario
{
    public const int EdgeCount = 3_000;
    public const double EdgeLengthMeters = 1_609.344;
    private const double MaximumProjectionMilliseconds = 1_000;

    public static TripMapScaleProfileResult Run()
    {
        var package = CreatePackage();
        var routePlan = Enumerable.Range(0, EdgeCount)
            .Select(index => $"scale-edge-{index:D4}")
            .ToArray();
        var currentEdgeId = routePlan[EdgeCount / 2];
        var currentEdgeDistance = EdgeLengthMeters / 2;
        var stopwatch = Stopwatch.StartNew();
        var realTime = Project(
            package,
            routePlan,
            currentEdgeId,
            currentEdgeDistance,
            TripMapTravelMode.RealTime);
        stopwatch.Stop();
        var fixedCompression = Project(
            package,
            routePlan,
            currentEdgeId,
            currentEdgeDistance,
            TripMapTravelMode.FixedRatio(3));
        var selectiveCruise = Project(
            package,
            routePlan,
            currentEdgeId,
            currentEdgeDistance,
            TripMapTravelMode.SelectiveCruise(3));

        Validate(realTime, fixedCompression, selectiveCruise, stopwatch.Elapsed.TotalMilliseconds);
        return new TripMapScaleProfileResult(
            EdgeCount,
            EdgeCount,
            realTime.GeometryLod,
            realTime.ProjectedPointCount,
            stopwatch.Elapsed.TotalMilliseconds,
            realTime.EstimatedRemainingSeconds,
            fixedCompression.EstimatedRemainingSeconds,
            selectiveCruise.EstimatedRemainingSeconds);
    }

    private static TripMapProjectionState Project(
        RouteContentPackage package,
        IReadOnlyList<string> routePlan,
        string currentEdgeId,
        double currentEdgeDistance,
        TripMapTravelMode travelMode) => TripMapProjector.Project(
            package,
            currentEdgeId,
            currentEdgeDistance,
            routePlan,
            AssistProfile.Balanced,
            30,
            new TripMapProjectionOptions(
                null,
                TripMapProjectionOptions.DefaultPointBudget,
                travelMode));

    private static void Validate(
        TripMapProjectionState realTime,
        TripMapProjectionState fixedCompression,
        TripMapProjectionState selectiveCruise,
        double elapsedMilliseconds)
    {
        if (realTime.GeometryLod != 1 ||
            realTime.ProjectedPointCount is <= 0 or > TripMapProjectionOptions.DefaultPointBudget ||
            elapsedMilliseconds > MaximumProjectionMilliseconds)
        {
            throw new InvalidOperationException(
                "Continental trip-map projection exceeded its scale contract: " +
                $"lod={realTime.GeometryLod} points={realTime.ProjectedPointCount} " +
                $"elapsed_ms={elapsedMilliseconds:0.000}.");
        }
        if (realTime.DistanceCompletedMeters != fixedCompression.DistanceCompletedMeters ||
            realTime.DistanceRemainingMeters != fixedCompression.DistanceRemainingMeters ||
            realTime.Current != fixedCompression.Current ||
            Math.Abs(realTime.EstimatedRemainingSeconds / 3 -
                fixedCompression.EstimatedRemainingSeconds) > 1e-6 ||
            Math.Abs(realTime.EstimatedRemainingSeconds / 3 -
                selectiveCruise.EstimatedRemainingSeconds) > 1e-6)
        {
            throw new InvalidOperationException(
                "Trip-map compression estimates changed authoritative route progress.");
        }
    }

    private static RouteContentPackage CreatePackage()
    {
        var provenance = new RouteSemanticProvenance(
            SemanticProvenanceKind.AuthoredOverride,
            "fixture",
            "continental-scale",
            new string('c', 64),
            "Deterministic 3,000-mile scale fixture; not asserted as observed geography.",
            "p0-013-scale-v1");
        var identity = new RouteIdentity(
            "route-scale", "TEST", "3000", "automation", "east", "", provenance);
        var edges = new RouteEdge[EdgeCount];
        var connectors = new JunctionConnector[EdgeCount - 1];
        var geometry = new List<SimplifiedMapGeometry>(EdgeCount * 3);
        for (var index = 0; index < EdgeCount; index++)
        {
            var edgeId = $"scale-edge-{index:D4}";
            edges[index] = new RouteEdge(
                edgeId,
                $"scale-node-{index:D4}",
                $"scale-node-{index + 1:D4}",
                EdgeLengthMeters,
                2,
                33.528,
                [],
                [],
                "test",
                "scale",
                [])
            {
                RouteIdentityIds = [identity.Id],
            };
            var startX = index * EdgeLengthMeters;
            var startY = 40 * Math.Sin(index / 20.0);
            var endY = 40 * Math.Sin((index + 1) / 20.0);
            geometry.Add(Geometry(edgeId, 0, startX, startY, endY, 17));
            geometry.Add(Geometry(edgeId, 1, startX, startY, endY, 5));
            geometry.Add(Geometry(edgeId, 2, startX, startY, endY, 2));
            if (index > 0)
            {
                var previousEdgeId = $"scale-edge-{index - 1:D4}";
                connectors[index - 1] = new JunctionConnector(
                    $"scale-connector-{index - 1:D4}",
                    $"scale-node-{index:D4}",
                    previousEdgeId,
                    $"{previousEdgeId}:lane:0",
                    edgeId,
                    $"{edgeId}:lane:0",
                    JunctionMovement.Continuation,
                    provenance);
            }
        }
        var nodes = Enumerable.Range(0, EdgeCount + 1)
            .Select(index => new RouteNode(
                $"scale-node-{index:D4}",
                default,
                index is 0 or EdgeCount ? "route-end" : "route",
                index == EdgeCount ? [] : [$"scale-edge-{index:D4}"]))
            .ToArray();
        var semantics = new RouteSemanticContent(
            [], connectors, [identity], [], [], [], geometry, false);
        return new RouteContentPackage(
            new InMemoryRouteGraph("trip-map-scale-v1", nodes, edges),
            new Dictionary<string, ChunkManifest>(),
            Semantics: semantics);
    }

    private static SimplifiedMapGeometry Geometry(
        string edgeId,
        int lod,
        double startX,
        double startY,
        double endY,
        int pointCount)
    {
        var points = Enumerable.Range(0, pointCount)
            .Select(index =>
            {
                var fraction = index / (double)(pointCount - 1);
                return new SimplifiedMapPoint(
                    startX + (EdgeLengthMeters * fraction),
                    startY + ((endY - startY) * fraction),
                    EdgeLengthMeters * fraction);
            })
            .ToArray();
        return new SimplifiedMapGeometry(edgeId, lod, points, "fixture");
    }
}
