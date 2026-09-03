using Godot;

namespace Cannonball.Game.World.RoadVisuals;

/// <summary>
/// Unit-length profile meshes for instanced highway furniture. Each mesh runs
/// along Z from -0.5 to +0.5 so the existing segment transforms, which
/// stretch Z by segment length and sit the instance at the segment midpoint,
/// apply unchanged. Texturing is triplanar in the furniture shader, so no UVs
/// are needed; normals are flat per face.
/// </summary>
public static class RoadFurnitureMeshes
{
    /// <summary>
    /// A New Jersey / F-shape concrete median barrier: 0.61 m base, 0.81 m
    /// tall, 0.15 m cap, with the 55-degree lower and 84-degree upper faces
    /// FHWA drawings specify. Vertically centred so the kit's existing 0.41 m
    /// lift leaves the base on the pavement.
    /// </summary>
    public static ArrayMesh BuildJerseyBarrier(Material material)
    {
        var half = 0.405f;
        // Right half profile, bottom to top, in (x, y).
        var profile = new[]
        {
            new Vector2(0.305f, -half),
            new Vector2(0.305f, -half + 0.076f),
            new Vector2(0.200f, -half + 0.330f),
            new Vector2(0.076f, half),
        };
        var outline = new List<Vector2>();
        foreach (var point in profile)
        {
            outline.Add(point);
        }
        for (var index = profile.Length - 1; index >= 0; index--)
        {
            outline.Add(new Vector2(-profile[index].X, profile[index].Y));
        }
        return Extrude(outline, closed: true, material, capEnds: true);
    }

    /// <summary>
    /// A galvanised W-beam guardrail: 0.31 m tall, 0.083 m deep corrugation,
    /// as a thin two-sided sheet (the material disables culling). Vertically
    /// centred; the traffic face is -X.
    /// </summary>
    public static ArrayMesh BuildWBeam(Material material)
    {
        var outline = new List<Vector2>
        {
            new(0.040f, -0.155f),
            new(-0.043f, -0.110f),
            new(0.040f, -0.045f),
            new(0.010f, 0.000f),
            new(0.040f, 0.045f),
            new(-0.043f, 0.110f),
            new(0.040f, 0.155f),
        };
        return Extrude(outline, closed: false, material, capEnds: false);
    }

    private static ArrayMesh Extrude(IReadOnlyList<Vector2> outline, bool closed, Material material, bool capEnds)
    {
        using var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        var count = closed ? outline.Count : outline.Count - 1;
        for (var index = 0; index < count; index++)
        {
            var a = outline[index];
            var b = outline[(index + 1) % outline.Count];
            var a0 = new Vector3(a.X, a.Y, -0.5f);
            var a1 = new Vector3(a.X, a.Y, 0.5f);
            var b0 = new Vector3(b.X, b.Y, -0.5f);
            var b1 = new Vector3(b.X, b.Y, 0.5f);
            // Outline runs clockwise seen from +Z for the closed profile, so this
            // winding faces outward.
            surface.AddVertex(a0);
            surface.AddVertex(b1);
            surface.AddVertex(b0);
            surface.AddVertex(a0);
            surface.AddVertex(a1);
            surface.AddVertex(b1);
        }
        if (capEnds && closed)
        {
            var centre = Vector2.Zero;
            foreach (var point in outline)
            {
                centre += point;
            }
            centre /= outline.Count;
            for (var index = 0; index < outline.Count; index++)
            {
                var a = outline[index];
                var b = outline[(index + 1) % outline.Count];
                surface.AddVertex(new Vector3(centre.X, centre.Y, 0.5f));
                surface.AddVertex(new Vector3(a.X, a.Y, 0.5f));
                surface.AddVertex(new Vector3(b.X, b.Y, 0.5f));
                surface.AddVertex(new Vector3(centre.X, centre.Y, -0.5f));
                surface.AddVertex(new Vector3(b.X, b.Y, -0.5f));
                surface.AddVertex(new Vector3(a.X, a.Y, -0.5f));
            }
        }
        surface.GenerateNormals();
        var mesh = surface.Commit();
        mesh.SurfaceSetMaterial(0, material);
        return mesh;
    }
}
