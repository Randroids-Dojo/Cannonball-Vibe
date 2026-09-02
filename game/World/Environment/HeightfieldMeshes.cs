using Godot;

namespace Cannonball.Game.World.Environments;

/// <summary>
/// Deterministic unit-size landform meshes for the midground and distant
/// environment layers. Each mesh occupies a radius-1 footprint on XZ with its
/// summit near Y = 1 and a skirt just below Y = 0, so an instance scaled by
/// (footprint, height, footprint) sits on the terrain without exposing its rim.
/// </summary>
/// <remarks>
/// Geometry comes from value-noise FBM over a radial profile with a few
/// Gaussian sub-peaks, seeded so every platform builds identical vertices.
/// The meshes are shared kit resources; the mountain shader shades them by
/// slope and height, so a single mesh reads as a wooded hill or a snow-capped
/// massif depending only on its instance scale.
/// </remarks>
public static class HeightfieldMeshes
{
    public static ArrayMesh BuildMassif(uint seed, int radialSegments = 56, int rings = 26) =>
        Build(seed, radialSegments, rings, profileExponent: 1.35f, ridgeStrength: 0.42f, peaks: 4, peakSharpness: 6.5f, rimNoise: 0.22f);

    public static ArrayMesh BuildHill(uint seed, int radialSegments = 40, int rings = 16) =>
        Build(seed, radialSegments, rings, profileExponent: 2.2f, ridgeStrength: 0.14f, peaks: 2, peakSharpness: 2.2f, rimNoise: 0.16f);

    private static ArrayMesh Build(
        uint seed,
        int radialSegments,
        int rings,
        float profileExponent,
        float ridgeStrength,
        int peaks,
        float peakSharpness,
        float rimNoise)
    {
        var random = new Lcg(seed);
        var peakOffsets = new Vector2[peaks];
        var peakWeights = new float[peaks];
        for (var index = 0; index < peaks; index++)
        {
            var angle = random.NextFloat() * Mathf.Tau;
            var radius = index == 0 ? 0.08f : 0.18f + random.NextFloat() * 0.42f;
            peakOffsets[index] = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius;
            peakWeights[index] = index == 0 ? 1.0f : 0.45f + random.NextFloat() * 0.45f;
        }
        var noiseOffset = new Vector2(random.NextFloat() * 100, random.NextFloat() * 100);

        var vertices = new List<Vector3>();
        var uvs = new List<Vector2>();
        // Ring 0 is the summit vertex; ring `rings` is the skirt below the rim.
        vertices.Add(new Vector3(0, Height(Vector2.Zero, peakOffsets, peakWeights, profileExponent, ridgeStrength, peakSharpness, noiseOffset), 0));
        uvs.Add(new Vector2(0.5f, 0.5f));
        for (var ring = 1; ring <= rings; ring++)
        {
            var t = ring / (float)rings;
            for (var segment = 0; segment < radialSegments; segment++)
            {
                var angle = segment / (float)radialSegments * Mathf.Tau;
                var radius = t * (1.0f + rimNoise * (ValueNoise(new Vector2(angle * 1.7f, t * 3.1f) + noiseOffset) - 0.5f) * t);
                var point = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius;
                var height = ring == rings
                    ? -0.06f
                    : Height(point, peakOffsets, peakWeights, profileExponent, ridgeStrength, peakSharpness, noiseOffset);
                vertices.Add(new Vector3(point.X, height, point.Y));
                uvs.Add(new Vector2(point.X * 0.5f + 0.5f, point.Y * 0.5f + 0.5f));
            }
        }

        using var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        for (var index = 0; index < vertices.Count; index++)
        {
            surface.SetUV(uvs[index]);
            surface.AddVertex(vertices[index]);
        }
        for (var segment = 0; segment < radialSegments; segment++)
        {
            var next = (segment + 1) % radialSegments;
            surface.AddIndex(0);
            surface.AddIndex(1 + next);
            surface.AddIndex(1 + segment);
        }
        for (var ring = 1; ring < rings; ring++)
        {
            var inner = 1 + (ring - 1) * radialSegments;
            var outer = 1 + ring * radialSegments;
            for (var segment = 0; segment < radialSegments; segment++)
            {
                var next = (segment + 1) % radialSegments;
                surface.AddIndex(inner + segment);
                surface.AddIndex(outer + next);
                surface.AddIndex(outer + segment);
                surface.AddIndex(inner + segment);
                surface.AddIndex(inner + next);
                surface.AddIndex(outer + next);
            }
        }
        surface.GenerateNormals();
        surface.GenerateTangents();
        return surface.Commit();
    }

    private static float Height(
        Vector2 point,
        Vector2[] peakOffsets,
        float[] peakWeights,
        float profileExponent,
        float ridgeStrength,
        float peakSharpness,
        Vector2 noiseOffset)
    {
        var radius = Mathf.Min(point.Length(), 1.0f);
        var envelope = Mathf.Pow(1.0f - radius, profileExponent);
        var peaksSum = 0f;
        for (var index = 0; index < peakOffsets.Length; index++)
        {
            var distance = (point - peakOffsets[index]).LengthSquared();
            peaksSum += peakWeights[index] * Mathf.Exp(-distance * peakSharpness);
        }
        var ridges = 1.0f - Mathf.Abs(2.0f * Fbm(point * 2.3f + noiseOffset, 4) - 1.0f);
        var detail = Fbm(point * 6.0f + noiseOffset * 0.37f, 3) - 0.5f;
        var height = envelope * (0.35f + 0.65f * Mathf.Min(1.0f, peaksSum)) *
            (1.0f + ridgeStrength * (ridges - 0.5f) * 2.0f) + envelope * detail * 0.08f;
        return Mathf.Max(0.0f, height);
    }

    private static float Fbm(Vector2 point, int octaves)
    {
        var amplitude = 0.5f;
        var sum = 0f;
        var norm = 0f;
        for (var octave = 0; octave < octaves; octave++)
        {
            sum += ValueNoise(point) * amplitude;
            norm += amplitude;
            point = new Vector2(point.X * 2.03f + 17.1f, point.Y * 2.03f - 9.7f);
            amplitude *= 0.5f;
        }
        return sum / norm;
    }

    private static float ValueNoise(Vector2 point)
    {
        var cell = point.Floor();
        var fraction = point - cell;
        fraction = fraction * fraction * (new Vector2(3, 3) - 2 * fraction);
        var a = Hash(cell);
        var b = Hash(cell + new Vector2(1, 0));
        var c = Hash(cell + new Vector2(0, 1));
        var d = Hash(cell + new Vector2(1, 1));
        return Mathf.Lerp(Mathf.Lerp(a, b, fraction.X), Mathf.Lerp(c, d, fraction.X), fraction.Y);
    }

    private static float Hash(Vector2 cell)
    {
        var x = unchecked((uint)(int)cell.X);
        var y = unchecked((uint)(int)cell.Y);
        var h = x * 0x8da6b343u ^ y * 0xd8163841u;
        h ^= h >> 13;
        h *= 0x5bd1e995u;
        h ^= h >> 15;
        return (h & 0xffffffu) / 16777216.0f;
    }

    private struct Lcg(uint seed)
    {
        private uint _state = seed == 0 ? 0x9e3779b9u : seed;

        public float NextFloat()
        {
            _state = unchecked(_state * 1664525u + 1013904223u);
            return (_state >> 8) / 16777216.0f;
        }
    }
}
