using Cannonball.Core.Content;
using Godot;

namespace Cannonball.Game.World.Environments;

public static class RegionalTerrainRibbon
{
    public const float InnerOffsetMeters = 132;
    public const float MiddleOffsetMeters = 260;
    public const float OuterOffsetMeters = 460;
    public const float VisibilityMeters = 6_000;

    private static readonly Color MountainColor = new("5f6652");
    private static readonly Color FoothillColor = new("647650");
    private static readonly Color PlainsColor = new("718461");
    private static readonly Color UrbanColor = new("65716c");

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

        var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        surface.SetMaterial(kit.TerrainBlend);
        var vertexCount = 0;
        for (var index = 0; index < points.Length - 1; index++)
        {
            foreach (var side in new[] { -1f, 1f })
            {
                var row0 = BuildRow(
                    points[index],
                    tangents[index],
                    routeDistances[index],
                    routeLengthMeters,
                    side);
                var row1 = BuildRow(
                    points[index + 1],
                    tangents[index + 1],
                    routeDistances[index + 1],
                    routeLengthMeters,
                    side);
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
        var mesh = surface.Commit();
        var startRows = new[]
        {
            BuildRow(points[0], tangents[0], routeDistances[0], routeLengthMeters, -1),
            BuildRow(points[0], tangents[0], routeDistances[0], routeLengthMeters, 1),
        };
        var endRows = new[]
        {
            BuildRow(points[^1], tangents[^1], routeDistances[^1], routeLengthMeters, -1),
            BuildRow(points[^1], tangents[^1], routeDistances[^1], routeLengthMeters, 1),
        };
        return new RegionalTerrainRibbonResult(
            mesh,
            vertexCount,
            vertexCount / 3,
            [startRows[0][^1].Position, startRows[1][^1].Position],
            [endRows[0][^1].Position, endRows[1][^1].Position]);
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
        float side)
    {
        var right = tangent.Cross(Vector3.Up).Normalized();
        var fraction = Math.Clamp(routeDistanceMeters / routeLengthMeters, 0, 1);
        var color = TerrainColor(fraction);
        return
        [
            new TerrainVertex(
                point + right * (InnerOffsetMeters * side) +
                    Vector3.Up * SurfaceHeight(
                        routeDistanceMeters,
                        routeLengthMeters,
                        InnerOffsetMeters),
                color,
                new Vector2(0, (float)(routeDistanceMeters / 80))),
            new TerrainVertex(
                point + right * (MiddleOffsetMeters * side) +
                    Vector3.Up * SurfaceHeight(
                        routeDistanceMeters,
                        routeLengthMeters,
                        MiddleOffsetMeters),
                color.Lightened(0.035f),
                new Vector2(0.5f, (float)(routeDistanceMeters / 80))),
            new TerrainVertex(
                point + right * (OuterOffsetMeters * side) +
                    Vector3.Up * SurfaceHeight(
                        routeDistanceMeters,
                        routeLengthMeters,
                        OuterOffsetMeters),
                color,
                new Vector2(1, (float)(routeDistanceMeters / 80))),
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
            return -0.34f;
        }
        var middleHeight = outerHeight * 0.38f - 0.6f;
        if (lateral <= MiddleOffsetMeters)
        {
            var factor = (lateral - InnerOffsetMeters) /
                (MiddleOffsetMeters - InnerOffsetMeters);
            return Mathf.Lerp(-0.34f, middleHeight, factor);
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

    private static Color TerrainColor(double fraction)
    {
        if (fraction < 1.0 / 3.0)
        {
            return MountainColor.Lerp(FoothillColor, Smooth(fraction * 3));
        }
        if (fraction < 2.0 / 3.0)
        {
            return FoothillColor.Lerp(PlainsColor, Smooth((fraction - 1.0 / 3.0) * 3));
        }
        return PlainsColor.Lerp(UrbanColor, Smooth((fraction - 2.0 / 3.0) * 3));
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

public sealed record RegionalTerrainRibbonResult(
    ArrayMesh Mesh,
    int VertexCount,
    int TriangleCount,
    IReadOnlyList<Vector3> StartOuterEdge,
    IReadOnlyList<Vector3> EndOuterEdge);
