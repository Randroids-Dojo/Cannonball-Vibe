using Cannonball.Core.Content;
using Godot;

namespace Cannonball.Game.World.Environments;

public static class RegionalTerrainRibbon
{
    public const float InnerOffsetMeters = 132;
    public const float MiddleOffsetMeters = 260;
    public const float OuterOffsetMeters = 460;
    public const float VisibilityMeters = 6_000;

    /// <summary>
    /// Height of the near ground relative to the road surface: the road
    /// terrain margin, the junction terrain quads and the inner plateau
    /// of the regional ribbon all sit here, so the ground is one
    /// continuous surface from the paved edge to the middle band and
    /// every near-layer instance anchored by <see cref="SurfaceHeight"/>
    /// stands on the surface that is drawn rather than 0.16 m below it.
    /// </summary>
    public const float NearGroundOffsetMeters = -0.18f;

    /// <summary>
    /// Route-distance UVs wrap at this period so float32 texture coordinates
    /// keep sub-millimetre precision thousands of kilometres from the start
    /// line. Every ground tile size divides it, so the wrap is invisible.
    /// </summary>
    public const double UvWrapPeriodMeters = 4096;

    public static RegionalTerrainRibbonResult Build(
        RouteChunkContent content,
        RouteFrame frame,
        RouteWorldPoint anchor,
        EnvironmentVisualKit kit,
        double routeStartMeters,
        double routeLengthMeters)
    {
        ArgumentNullException.ThrowIfNull(content);
        ArgumentNullException.ThrowIfNull(frame);
        ArgumentNullException.ThrowIfNull(kit);
        if (routeLengthMeters <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(routeLengthMeters));
        }

        var selected = SelectSamples(content.Samples, kit.TerrainSampleStride);
        var points = selected
            .Select(sample => frame.ToWorld(sample).RelativeTo(anchor))
            .ToArray();
        var tangents = selected
            .Select(sample => frame.DirectionToWorld(
                sample.ProjectedTangentX,
                sample.ProjectedTangentY))
            .ToArray();
        var routeDistances = selected
            .Select(sample => routeStartMeters + sample.DistanceMeters - content.StartMeters)
            .ToArray();

        using var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        surface.SetMaterial(kit.Ground);
        var vertexCount = 0;
        for (var index = 0; index < points.Length - 1; index++)
        {
            var uv0 = WrapUv(routeDistances[index]);
            var uv1 = uv0 + (routeDistances[index + 1] - routeDistances[index]);
            foreach (var side in new[] { -1f, 1f })
            {
                var row0 = BuildRow(
                    points[index],
                    tangents[index],
                    routeDistances[index],
                    routeLengthMeters,
                    side,
                    uv0);
                var row1 = BuildRow(
                    points[index + 1],
                    tangents[index + 1],
                    routeDistances[index + 1],
                    routeLengthMeters,
                    side,
                    uv1);
                for (var band = 0; band < 2; band++)
                {
                    if (side < 0)
                    {
                        AddTriangle(
                            surface,
                            row0[band],
                            row1[band + 1],
                            row0[band + 1]);
                        AddTriangle(
                            surface,
                            row0[band],
                            row1[band],
                            row1[band + 1]);
                    }
                    else
                    {
                        AddTriangle(
                            surface,
                            row0[band],
                            row0[band + 1],
                            row1[band + 1]);
                        AddTriangle(
                            surface,
                            row0[band],
                            row1[band + 1],
                            row1[band]);
                    }
                    vertexCount += 6;
                }
            }
        }
        surface.GenerateNormals();
        surface.GenerateTangents();
        var mesh = surface.Commit();
        var startRows = new[]
        {
            BuildRow(points[0], tangents[0], routeDistances[0], routeLengthMeters, -1, 0),
            BuildRow(points[0], tangents[0], routeDistances[0], routeLengthMeters, 1, 0),
        };
        var endRows = new[]
        {
            BuildRow(points[^1], tangents[^1], routeDistances[^1], routeLengthMeters, -1, 0),
            BuildRow(points[^1], tangents[^1], routeDistances[^1], routeLengthMeters, 1, 0),
        };
        return new RegionalTerrainRibbonResult(
            mesh,
            vertexCount,
            vertexCount / 3,
            [startRows[0][^1].Position, startRows[1][^1].Position],
            [endRows[0][^1].Position, endRows[1][^1].Position]);
    }

    private static readonly float[] CollisionBandOffsetsMeters =
        [InnerOffsetMeters, MiddleOffsetMeters, OuterOffsetMeters];

    /// <summary>
    /// The ground collider for a run of road stations: from each paved edge
    /// out to <see cref="OuterOffsetMeters"/> on the same analytic surface
    /// the ribbon draws, so a car that leaves the road at speed is held by
    /// the ground it sees rather than dropping off the end of the drawn
    /// margin. Triangles wind clockwise seen from above, which Godot treats
    /// as the front face for ray casts. Without a route length (a chunk off
    /// the plan) the surface is the flat near-ground offset.
    /// </summary>
    public static ArrayMesh BuildGroundCollisionMesh(
        IReadOnlyList<GroundStation> stations,
        double routeLengthMeters)
    {
        ArgumentNullException.ThrowIfNull(stations);
        if (stations.Count < 2)
        {
            throw new ArgumentException("A ground collider needs at least two stations.", nameof(stations));
        }
        using var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        for (var index = 0; index < stations.Count - 1; index++)
        {
            foreach (var side in new[] { -1f, 1f })
            {
                var row0 = CollisionRow(stations[index], side, routeLengthMeters);
                var row1 = CollisionRow(stations[index + 1], side, routeLengthMeters);
                for (var band = 0; band < row0.Length - 1; band++)
                {
                    var a = row0[band];
                    var b = row0[band + 1];
                    var c = row1[band];
                    var d = row1[band + 1];
                    if (side < 0)
                    {
                        AddCollisionTriangle(surface, a, b, d);
                        AddCollisionTriangle(surface, a, d, c);
                    }
                    else
                    {
                        AddCollisionTriangle(surface, a, d, b);
                        AddCollisionTriangle(surface, a, c, d);
                    }
                }
            }
        }
        return surface.Commit();
    }

    private static Vector3[] CollisionRow(GroundStation station, float side, double routeLengthMeters)
    {
        var pavedEdge = side < 0 ? station.PavedLeftMeters : station.PavedRightMeters;
        var row = new Vector3[CollisionBandOffsetsMeters.Length + 1];
        row[0] = CollisionVertex(station, (float)pavedEdge, routeLengthMeters);
        for (var band = 0; band < CollisionBandOffsetsMeters.Length; band++)
        {
            // A band inside the paved edge collapses onto it rather than folding back.
            var lateral = side * Math.Max(CollisionBandOffsetsMeters[band], (float)Math.Abs(pavedEdge));
            row[band + 1] = CollisionVertex(station, lateral, routeLengthMeters);
        }
        return row;
    }

    private static Vector3 CollisionVertex(GroundStation station, float lateral, double routeLengthMeters)
    {
        var height = double.IsFinite(routeLengthMeters) && routeLengthMeters > 0
            ? SurfaceHeight(station.RouteDistanceMeters, routeLengthMeters, lateral)
            : NearGroundOffsetMeters;
        return station.Center + station.Right * lateral + Vector3.Up * height;
    }

    private static void AddCollisionTriangle(SurfaceTool surface, Vector3 a, Vector3 b, Vector3 c)
    {
        surface.AddVertex(a);
        surface.AddVertex(b);
        surface.AddVertex(c);
    }

    /// <summary>Route distance folded into the UV wrap period.</summary>
    public static double WrapUv(double routeDistanceMeters)
    {
        var wrapped = routeDistanceMeters % UvWrapPeriodMeters;
        return wrapped < 0 ? wrapped + UvWrapPeriodMeters : wrapped;
    }

    /// <summary>
    /// Ground-shader layer weights for a point on the route: R is dry grass,
    /// G is bare dirt, B is extra rock. The representative corridor blends
    /// mountain, foothill, plains and urban-edge thirds like the region bands.
    /// </summary>
    public static Color GroundWeights(double routeDistanceMeters, double routeLengthMeters)
    {
        var fraction = routeLengthMeters <= 0
            ? 0
            : Math.Clamp(routeDistanceMeters / routeLengthMeters, 0, 1);
        var mountain = new Color(0.10f, 0.06f, 0.14f);
        var foothill = new Color(0.38f, 0.12f, 0.04f);
        var plains = new Color(0.88f, 0.22f, 0.0f);
        var urban = new Color(0.62f, 0.55f, 0.0f);
        if (fraction < 1.0 / 3.0)
        {
            return mountain.Lerp(foothill, Smooth(fraction * 3));
        }
        if (fraction < 2.0 / 3.0)
        {
            return foothill.Lerp(plains, Smooth((fraction - 1.0 / 3.0) * 3));
        }
        return plains.Lerp(urban, Smooth((fraction - 2.0 / 3.0) * 3));
    }

    private static IReadOnlyList<RouteChunkSample> SelectSamples(
        IReadOnlyList<RouteChunkSample> samples,
        int stride)
    {
        var result = new List<RouteChunkSample> { samples[0] };
        for (var index = stride; index < samples.Count - 1; index += stride)
        {
            result.Add(samples[index]);
        }
        if (result[^1].DistanceMeters != samples[^1].DistanceMeters)
        {
            result.Add(samples[^1]);
        }
        return result;
    }

    private static TerrainVertex[] BuildRow(
        Vector3 point,
        Vector3 tangent,
        double routeDistanceMeters,
        double routeLengthMeters,
        float side,
        double uvDistance)
    {
        var right = tangent.Cross(Vector3.Up).Normalized();
        var color = GroundWeights(routeDistanceMeters, routeLengthMeters);
        var v = (float)uvDistance;
        return
        [
            new TerrainVertex(
                point + right * (InnerOffsetMeters * side) +
                    Vector3.Up * SurfaceHeight(
                        routeDistanceMeters,
                        routeLengthMeters,
                        InnerOffsetMeters),
                color,
                new Vector2(InnerOffsetMeters * side, v)),
            new TerrainVertex(
                point + right * (MiddleOffsetMeters * side) +
                    Vector3.Up * SurfaceHeight(
                        routeDistanceMeters,
                        routeLengthMeters,
                        MiddleOffsetMeters),
                color,
                new Vector2(MiddleOffsetMeters * side, v)),
            new TerrainVertex(
                point + right * (OuterOffsetMeters * side) +
                    Vector3.Up * SurfaceHeight(
                        routeDistanceMeters,
                        routeLengthMeters,
                        OuterOffsetMeters),
                color,
                new Vector2(OuterOffsetMeters * side, v)),
        ];
    }

    public static float SurfaceHeight(
        double routeDistanceMeters,
        double routeLengthMeters,
        float lateralMeters)
    {
        var fraction = Math.Clamp(routeDistanceMeters / routeLengthMeters, 0, 1);
        var outerHeight = TerrainHeight(routeDistanceMeters, fraction);
        var lateral = Math.Abs(lateralMeters);
        if (lateral <= InnerOffsetMeters)
        {
            return NearGroundOffsetMeters;
        }
        var middleHeight = outerHeight * 0.38f - 0.6f;
        if (lateral <= MiddleOffsetMeters)
        {
            var factor = (lateral - InnerOffsetMeters) /
                (MiddleOffsetMeters - InnerOffsetMeters);
            return Mathf.Lerp(NearGroundOffsetMeters, middleHeight, factor);
        }
        if (lateral <= OuterOffsetMeters)
        {
            var factor = (lateral - MiddleOffsetMeters) /
                (OuterOffsetMeters - MiddleOffsetMeters);
            return Mathf.Lerp(middleHeight, outerHeight, factor);
        }
        return outerHeight;
    }

    private static float TerrainHeight(double routeDistanceMeters, double fraction)
    {
        var amplitude = BlendByRoute(fraction, 17, 8, 2.5f, 1.2f);
        var broad = Math.Sin(routeDistanceMeters / 760 * Math.PI * 2);
        var detail = Math.Sin(routeDistanceMeters / 230 * Math.PI * 2 + 0.7);
        return (float)(-1.2 + broad * amplitude + detail * amplitude * 0.22);
    }

    private static float BlendByRoute(
        double fraction,
        float mountain,
        float foothill,
        float plains,
        float urban)
    {
        if (fraction < 1.0 / 3.0)
        {
            return Mathf.Lerp(mountain, foothill, Smooth(fraction * 3));
        }
        if (fraction < 2.0 / 3.0)
        {
            return Mathf.Lerp(foothill, plains, Smooth((fraction - 1.0 / 3.0) * 3));
        }
        return Mathf.Lerp(plains, urban, Smooth((fraction - 2.0 / 3.0) * 3));
    }

    private static float Smooth(double value)
    {
        var bounded = (float)Math.Clamp(value, 0, 1);
        return bounded * bounded * (3 - 2 * bounded);
    }

    private static void AddTriangle(
        SurfaceTool surface,
        TerrainVertex first,
        TerrainVertex second,
        TerrainVertex third)
    {
        AddVertex(surface, first);
        AddVertex(surface, second);
        AddVertex(surface, third);
    }

    private static void AddVertex(SurfaceTool surface, TerrainVertex vertex)
    {
        surface.SetColor(vertex.Color);
        surface.SetUV(vertex.Uv);
        surface.AddVertex(vertex.Position);
    }

    private sealed record TerrainVertex(Vector3 Position, Color Color, Vector2 Uv);
}

/// <summary>
/// A road cross-section for the ground collider: centreline point, unit
/// right vector, route distance and the paved edges as signed lateral offsets.
/// </summary>
public readonly record struct GroundStation(
    Vector3 Center,
    Vector3 Right,
    double RouteDistanceMeters,
    double PavedLeftMeters,
    double PavedRightMeters);

public sealed record RegionalTerrainRibbonResult(
    ArrayMesh Mesh,
    int VertexCount,
    int TriangleCount,
    IReadOnlyList<Vector3> StartOuterEdge,
    IReadOnlyList<Vector3> EndOuterEdge);
