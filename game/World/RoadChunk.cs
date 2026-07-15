using Godot;

namespace Cannonball.Game.World;

public sealed partial class RoadChunk : Node3D
{
    private const float RoadHalfWidth = 7.2f;
    private const float SampleSpacing = 25.0f;

    public int ChunkIndex { get; private init; }
    public double StartMeters { get; private init; }
    public double EndMeters { get; private init; }

    public static RoadChunk Create(int chunkIndex, double chunkLengthMeters, double localOriginMeters)
    {
        var start = chunkIndex * chunkLengthMeters;
        var end = Math.Min(RoadMath.RouteLengthMeters, start + chunkLengthMeters);
        var chunk = new RoadChunk
        {
            Name = $"RoadChunk-{chunkIndex:D3}",
            ChunkIndex = chunkIndex,
            StartMeters = start,
            EndMeters = end,
            Position = new Vector3(RoadMath.CenterX(start), RoadMath.Elevation(start), (float)-(start - localOriginMeters)),
        };
        chunk.BuildRoad();
        chunk.BuildLaneMarkings();
        chunk.BuildScenery();
        return chunk;
    }

    public void ShiftForOriginRebase(float meters) => Position += Vector3.Back * meters;

    private void BuildRoad()
    {
        var mesh = BuildRibbonMesh();
        var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("151820"),
            Roughness = 0.94f,
        };
        AddChild(new MeshInstance3D
        {
            Name = "RoadSurface",
            Mesh = mesh,
            MaterialOverride = material,
        });

        var body = new StaticBody3D { Name = "RoadCollision", CollisionLayer = 1, CollisionMask = 2 };
        body.AddChild(new CollisionShape3D { Shape = mesh.CreateTrimeshShape() });
        AddChild(body);
    }

    private ArrayMesh BuildRibbonMesh()
    {
        var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        var segmentCount = Math.Max(1, (int)Math.Ceiling((EndMeters - StartMeters) / SampleSpacing));
        var startCenter = RoadMath.CenterX(StartMeters);
        var startElevation = RoadMath.Elevation(StartMeters);

        for (var segment = 0; segment < segmentCount; segment++)
        {
            var distance0 = StartMeters + (EndMeters - StartMeters) * segment / segmentCount;
            var distance1 = StartMeters + (EndMeters - StartMeters) * (segment + 1) / segmentCount;
            var center0 = new Vector3(
                RoadMath.CenterX(distance0) - startCenter,
                RoadMath.Elevation(distance0) - startElevation,
                (float)-(distance0 - StartMeters));
            var center1 = new Vector3(
                RoadMath.CenterX(distance1) - startCenter,
                RoadMath.Elevation(distance1) - startElevation,
                (float)-(distance1 - StartMeters));
            var direction = (center1 - center0).Normalized();
            var right = direction.Cross(Vector3.Up).Normalized();
            var left0 = center0 - right * RoadHalfWidth;
            var right0 = center0 + right * RoadHalfWidth;
            var left1 = center1 - right * RoadHalfWidth;
            var right1 = center1 + right * RoadHalfWidth;
            var v0 = (float)(distance0 / 20.0);
            var v1 = (float)(distance1 / 20.0);

            AddTriangle(surface, left0, right1, right0, new Vector2(0, v0), new Vector2(1, v1), new Vector2(1, v0));
            AddTriangle(surface, left0, left1, right1, new Vector2(0, v0), new Vector2(0, v1), new Vector2(1, v1));
        }

        surface.GenerateNormals();
        return surface.Commit();
    }

    private static void AddTriangle(
        SurfaceTool surface,
        Vector3 first,
        Vector3 second,
        Vector3 third,
        Vector2 firstUv,
        Vector2 secondUv,
        Vector2 thirdUv)
    {
        surface.SetUV(firstUv);
        surface.AddVertex(first);
        surface.SetUV(secondUv);
        surface.AddVertex(second);
        surface.SetUV(thirdUv);
        surface.AddVertex(third);
    }

    private void BuildLaneMarkings()
    {
        var dashMesh = new BoxMesh { Size = new Vector3(0.12f, 0.025f, 5.0f) };
        dashMesh.Material = new StandardMaterial3D
        {
            AlbedoColor = new Color("d8d5bc"),
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
        };

        var distances = new List<double>();
        for (var distance = StartMeters + 8; distance < EndMeters; distance += 16)
        {
            distances.Add(distance);
        }

        var multiMesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = dashMesh,
            InstanceCount = distances.Count * 2,
        };
        var startCenter = RoadMath.CenterX(StartMeters);
        var startElevation = RoadMath.Elevation(StartMeters);
        var instance = 0;
        foreach (var distance in distances)
        {
            var local = new Vector3(
                RoadMath.CenterX(distance) - startCenter,
                RoadMath.Elevation(distance) - startElevation + 0.025f,
                (float)-(distance - StartMeters));
            var tangent = new Vector3(
                RoadMath.CenterX(distance + 1) - RoadMath.CenterX(distance),
                RoadMath.Elevation(distance + 1) - RoadMath.Elevation(distance),
                -1).Normalized();
            var basis = Basis.LookingAt(tangent, Vector3.Up);
            var right = tangent.Cross(Vector3.Up).Normalized();
            multiMesh.SetInstanceTransform(instance++, new Transform3D(basis, local - right * 2.4f));
            multiMesh.SetInstanceTransform(instance++, new Transform3D(basis, local + right * 2.4f));
        }

        AddChild(new MultiMeshInstance3D { Name = "LaneMarkings", Multimesh = multiMesh });
    }

    private void BuildScenery()
    {
        var postMesh = new CylinderMesh { TopRadius = 0.12f, BottomRadius = 0.16f, Height = 1.1f };
        postMesh.Material = new StandardMaterial3D { AlbedoColor = new Color("3f4654"), Roughness = 0.9f };
        var count = Math.Max(1, (int)((EndMeters - StartMeters) / 80.0) * 2);
        var multiMesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = postMesh,
            InstanceCount = count,
        };
        var startCenter = RoadMath.CenterX(StartMeters);
        var startElevation = RoadMath.Elevation(StartMeters);
        for (var index = 0; index < count; index++)
        {
            var pairIndex = index / 2;
            var distance = Math.Min(EndMeters - 1, StartMeters + pairIndex * 80 + 25);
            var side = index % 2 == 0 ? -1.0f : 1.0f;
            var origin = new Vector3(
                RoadMath.CenterX(distance) - startCenter + side * 10.0f,
                RoadMath.Elevation(distance) - startElevation + 0.55f,
                (float)-(distance - StartMeters));
            multiMesh.SetInstanceTransform(index, new Transform3D(Basis.Identity, origin));
        }

        AddChild(new MultiMeshInstance3D { Name = "RoadsidePosts", Multimesh = multiMesh });
    }
}
