using Godot;

namespace Cannonball.Game.World.Environments;

/// <summary>
/// Small deterministic meshes that the environment needs even when no sourced
/// or Blender-generated asset is available: a stacked-tier conifer and a
/// displaced rock. They keep the production LOD and material-slot semantics so
/// the fallback path exercises the same runtime code.
/// </summary>
public static class ProceduralMeshes
{
    /// <summary>
    /// A conifer with a trunk surface (bark material) and a crown surface
    /// (needle material) so surface counts match the generated asset.
    /// Unit height 1, unit crown radius about 0.28; instances scale to metres.
    /// </summary>
    public static ArrayMesh BuildConifer(Material bark, Material needles, int tiers, int segments)
    {
        var mesh = new ArrayMesh();
        using (var trunk = new SurfaceTool())
        {
            trunk.Begin(Mesh.PrimitiveType.Triangles);
            AddCone(trunk, radiusBottom: 0.035f, radiusTop: 0.012f, yBottom: 0, yTop: 0.92f, segments, uvRepeat: 3);
            trunk.GenerateNormals();
            trunk.GenerateTangents();
            trunk.Commit(mesh);
        }
        using (var crown = new SurfaceTool())
        {
            crown.Begin(Mesh.PrimitiveType.Triangles);
            for (var tier = 0; tier < tiers; tier++)
            {
                var t = tier / (float)tiers;
                var yBottom = 0.18f + t * 0.66f;
                var yTop = yBottom + 0.34f;
                var radius = 0.30f * (1.0f - t * 0.72f);
                AddCone(crown, radiusBottom: radius, radiusTop: 0.0f, yBottom, Mathf.Min(yTop, 1.0f), segments, uvRepeat: 1);
            }
            crown.GenerateNormals();
            crown.GenerateTangents();
            crown.Commit(mesh);
        }
        mesh.SurfaceSetMaterial(0, bark);
        mesh.SurfaceSetMaterial(1, needles);
        return mesh;
    }

    /// <summary>A noise-displaced ellipsoid boulder, radius about 1, resting on Y = 0.</summary>
    public static ArrayMesh BuildRock(uint seed, int radialSegments, int rings, Material RockMaterial)
    {
        using var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        var vertices = new List<Vector3>();
        for (var ring = 0; ring <= rings; ring++)
        {
            var v = ring / (float)rings;
            var theta = v * Mathf.Pi;
            for (var segment = 0; segment < radialSegments; segment++)
            {
                var u = segment / (float)radialSegments;
                var phi = u * Mathf.Tau;
                var direction = new Vector3(
                    Mathf.Sin(theta) * Mathf.Cos(phi),
                    Mathf.Cos(theta),
                    Mathf.Sin(theta) * Mathf.Sin(phi));
                var noise = 0.78f + 0.22f * Hash(seed, ring * 131 + segment) +
                    0.10f * Hash(seed * 7, ring * 17 + segment * 3);
                var point = direction * noise * new Vector3(1.0f, 0.72f, 0.86f);
                point.Y += 0.55f;
                vertices.Add(point);
            }
        }
        for (var ring = 0; ring < rings; ring++)
        {
            for (var segment = 0; segment < radialSegments; segment++)
            {
                var next = (segment + 1) % radialSegments;
                var a = vertices[ring * radialSegments + segment];
                var b = vertices[ring * radialSegments + next];
                var c = vertices[(ring + 1) * radialSegments + segment];
                var d = vertices[(ring + 1) * radialSegments + next];
                AddQuad(surface, a, b, d, c);
            }
        }
        surface.GenerateNormals();
        surface.GenerateTangents();
        var mesh = surface.Commit();
        mesh.SurfaceSetMaterial(0, RockMaterial);
        return mesh;
    }

    private static void AddCone(
        SurfaceTool surface,
        float radiusBottom,
        float radiusTop,
        float yBottom,
        float yTop,
        int segments,
        float uvRepeat)
    {
        for (var segment = 0; segment < segments; segment++)
        {
            var a0 = segment / (float)segments * Mathf.Tau;
            var a1 = (segment + 1) / (float)segments * Mathf.Tau;
            var b0 = new Vector3(Mathf.Cos(a0) * radiusBottom, yBottom, Mathf.Sin(a0) * radiusBottom);
            var b1 = new Vector3(Mathf.Cos(a1) * radiusBottom, yBottom, Mathf.Sin(a1) * radiusBottom);
            var t0 = new Vector3(Mathf.Cos(a0) * radiusTop, yTop, Mathf.Sin(a0) * radiusTop);
            var t1 = new Vector3(Mathf.Cos(a1) * radiusTop, yTop, Mathf.Sin(a1) * radiusTop);
            var u0 = segment / (float)segments * uvRepeat;
            var u1 = (segment + 1) / (float)segments * uvRepeat;
            surface.SetUV(new Vector2(u0, 1));
            surface.AddVertex(b0);
            surface.SetUV(new Vector2(u1, 0));
            surface.AddVertex(t1);
            surface.SetUV(new Vector2(u1, 1));
            surface.AddVertex(b1);
            surface.SetUV(new Vector2(u0, 1));
            surface.AddVertex(b0);
            surface.SetUV(new Vector2(u0, 0));
            surface.AddVertex(t0);
            surface.SetUV(new Vector2(u1, 0));
            surface.AddVertex(t1);
        }
    }

    private static void AddQuad(SurfaceTool surface, Vector3 a, Vector3 b, Vector3 c, Vector3 d)
    {
        surface.SetUV(new Vector2(0, 0));
        surface.AddVertex(a);
        surface.SetUV(new Vector2(1, 1));
        surface.AddVertex(c);
        surface.SetUV(new Vector2(1, 0));
        surface.AddVertex(b);
        surface.SetUV(new Vector2(0, 0));
        surface.AddVertex(a);
        surface.SetUV(new Vector2(0, 1));
        surface.AddVertex(d);
        surface.SetUV(new Vector2(1, 1));
        surface.AddVertex(c);
    }

    private static float Hash(uint seed, int index)
    {
        var h = unchecked(seed * 0x9e3779b1u ^ (uint)index * 0x85ebca6bu);
        h ^= h >> 13;
        h = unchecked(h * 0xc2b2ae35u);
        h ^= h >> 16;
        return (h & 0xffffffu) / 16777216.0f;
    }
}
