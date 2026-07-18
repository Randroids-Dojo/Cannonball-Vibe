using System.Diagnostics;
using Cannonball.Core.Content;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class RoadChunk : Node3D
{
    private const float RoadHalfWidth = 7.2f;
    private StaticBody3D? _collisionBody;
    private ArrayMesh _roadMesh = null!;

    public string ChunkId { get; private init; } = string.Empty;
    public string EdgeId { get; private init; } = string.Empty;
    public double StartMeters { get; private init; }
    public double EndMeters { get; private init; }
    public double BuildMilliseconds { get; private set; }
    public bool HasCollision => _collisionBody is not null;

    public bool HasReviewGeometry()
    {
        var road = GetNodeOrNull<MeshInstance3D>("RoadSurface");
        var terrain = GetNodeOrNull<MeshInstance3D>("TerrainShoulders");
        var scenery = GetNodeOrNull<MultiMeshInstance3D>("TerrainScenery");
        return road is { Visible: true, Mesh: not null } &&
            road.Mesh.GetAabb().Size.LengthSquared() > 0 &&
            terrain is { Visible: true, Mesh: not null } &&
            terrain.Mesh.GetAabb().Size.LengthSquared() > 0 &&
            scenery is { Visible: true, Multimesh: not null } &&
            scenery.Multimesh.InstanceCount > 0;
    }

    public static RoadChunk Create(
        RouteChunkContent content,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld)
    {
        var started = Stopwatch.GetTimestamp();
        var anchor = frame.ToWorld(content.Samples[0]);
        var points = content.Samples
            .Select(sample => frame.ToWorld(sample).RelativeTo(anchor))
            .ToArray();
        var tangents = content.Samples
            .Select(sample => frame.DirectionToWorld(
                sample.ProjectedTangentX,
                sample.ProjectedTangentY))
            .ToArray();
        var chunk = new RoadChunk
        {
            Name = $"RoadChunk-{content.Id}",
            ChunkId = content.Id,
            EdgeId = content.EdgeId,
            StartMeters = content.StartMeters,
            EndMeters = content.EndMeters,
            Position = anchor.RelativeTo(localOriginWorld),
        };
        chunk.BuildTerrain(points, tangents, content.Samples);
        chunk.BuildRoad(points, tangents, content.Samples);
        chunk.BuildLaneMarkings(points, tangents);
        chunk.BuildScenery(points, tangents);
        chunk.BuildMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        return chunk;
    }

    public double SetCollisionActive(bool active)
    {
        if (active == HasCollision)
        {
            return 0;
        }
        if (!active)
        {
            var body = _collisionBody!;
            body.CollisionLayer = 0;
            body.ProcessMode = ProcessModeEnum.Disabled;
            RemoveChild(body);
            body.Free();
            _collisionBody = null;
            return 0;
        }

        var started = Stopwatch.GetTimestamp();
        _collisionBody = new StaticBody3D
        {
            Name = "RoadCollision",
            CollisionLayer = 1,
            CollisionMask = 2,
        };
        _collisionBody.AddChild(new CollisionShape3D { Shape = _roadMesh.CreateTrimeshShape() });
        AddChild(_collisionBody);
        return Stopwatch.GetElapsedTime(started).TotalMilliseconds;
    }

    public void ShiftForOriginRebase(Vector3 shift) => Position -= shift;

    private void BuildRoad(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<RouteChunkSample> samples)
    {
        _roadMesh = BuildRibbonMesh(points, tangents, samples, RoadHalfWidth, 0);
        var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("151820"),
            Roughness = 0.94f,
        };
        AddChild(new MeshInstance3D
        {
            Name = "RoadSurface",
            Mesh = _roadMesh,
            MaterialOverride = material,
        });
    }

    private static ArrayMesh BuildRibbonMesh(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<RouteChunkSample> samples,
        float halfWidth,
        float verticalOffset)
    {
        var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        for (var index = 0; index < points.Count - 1; index++)
        {
            var center0 = points[index] + Vector3.Up * verticalOffset;
            var center1 = points[index + 1] + Vector3.Up * verticalOffset;
            var right0Direction = tangents[index].Cross(Vector3.Up).Normalized();
            var right1Direction = tangents[index + 1].Cross(Vector3.Up).Normalized();
            var left0 = center0 - right0Direction * halfWidth;
            var right0 = center0 + right0Direction * halfWidth;
            var left1 = center1 - right1Direction * halfWidth;
            var right1 = center1 + right1Direction * halfWidth;
            var v0 = (float)(samples[index].DistanceMeters / 20.0);
            var v1 = (float)(samples[index + 1].DistanceMeters / 20.0);

            AddTriangle(surface, left0, right1, right0, new Vector2(0, v0), new Vector2(1, v1), new Vector2(1, v0));
            AddTriangle(surface, left0, left1, right1, new Vector2(0, v0), new Vector2(0, v1), new Vector2(1, v1));
        }

        surface.GenerateNormals();
        return surface.Commit();
    }

    private void BuildTerrain(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<RouteChunkSample> samples)
    {
        var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("344536"),
            Roughness = 1.0f,
        };
        AddChild(new MeshInstance3D
        {
            Name = "TerrainShoulders",
            Mesh = BuildRibbonMesh(points, tangents, samples, 48, -0.18f),
            MaterialOverride = material,
        });
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

    private void BuildLaneMarkings(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents)
    {
        var transforms = new List<Transform3D>();
        for (var index = 0; index < points.Count - 1; index++)
        {
            var segment = points[index + 1] - points[index];
            if (segment.LengthSquared() < 0.001f)
            {
                continue;
            }
            var tangent = (tangents[index] + tangents[index + 1]).Normalized();
            var right = tangent.Cross(Vector3.Up).Normalized();
            var basis = Basis.LookingAt(tangent, Vector3.Up);
            var center = points[index].Lerp(points[index + 1], 0.5f) + Vector3.Up * 0.025f;
            transforms.Add(new Transform3D(basis, center - right * 2.4f));
            transforms.Add(new Transform3D(basis, center + right * 2.4f));
        }

        var dashMesh = new BoxMesh { Size = new Vector3(0.12f, 0.025f, 5.0f) };
        dashMesh.Material = new StandardMaterial3D
        {
            AlbedoColor = new Color("d8d5bc"),
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
        };
        var multiMesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = dashMesh,
            InstanceCount = transforms.Count,
        };
        for (var index = 0; index < transforms.Count; index++)
        {
            multiMesh.SetInstanceTransform(index, transforms[index]);
        }
        AddChild(new MultiMeshInstance3D { Name = "LaneMarkings", Multimesh = multiMesh });
    }

    private void BuildScenery(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents)
    {
        var transforms = new List<Transform3D>();
        for (var index = 0; index < points.Count - 1; index++)
        {
            var tangent = tangents[index];
            var right = tangent.Cross(Vector3.Up).Normalized();
            transforms.Add(new Transform3D(Basis.Identity, points[index] - right * 10 + Vector3.Up * 0.55f));
            transforms.Add(new Transform3D(Basis.Identity, points[index] + right * 10 + Vector3.Up * 0.55f));
        }

        var postMesh = new CylinderMesh { TopRadius = 0.12f, BottomRadius = 0.16f, Height = 1.1f };
        postMesh.Material = new StandardMaterial3D
        {
            AlbedoColor = new Color("d6d0ad"),
            Roughness = 0.9f,
        };
        var multiMesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = postMesh,
            InstanceCount = transforms.Count,
        };
        for (var index = 0; index < transforms.Count; index++)
        {
            multiMesh.SetInstanceTransform(index, transforms[index]);
        }
        AddChild(new MultiMeshInstance3D { Name = "RoadsidePosts", Multimesh = multiMesh });

        var treeTransforms = new List<Transform3D>();
        for (var index = 0; index < points.Count - 1; index += 2)
        {
            var right = tangents[index].Cross(Vector3.Up).Normalized();
            var distance = 19 + index % 3 * 2;
            treeTransforms.Add(new Transform3D(
                Basis.Identity,
                points[index] - right * distance + Vector3.Up * 2.25f));
            treeTransforms.Add(new Transform3D(
                Basis.Identity,
                points[index] + right * distance + Vector3.Up * 2.25f));
        }
        var treeMesh = new CylinderMesh
        {
            TopRadius = 0,
            BottomRadius = 1.35f,
            Height = 4.5f,
            Material = new StandardMaterial3D
            {
                AlbedoColor = new Color("557052"),
                Roughness = 1.0f,
            },
        };
        var treeMultiMesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = treeMesh,
            InstanceCount = treeTransforms.Count,
        };
        for (var index = 0; index < treeTransforms.Count; index++)
        {
            treeMultiMesh.SetInstanceTransform(index, treeTransforms[index]);
        }
        AddChild(new MultiMeshInstance3D { Name = "TerrainScenery", Multimesh = treeMultiMesh });
    }
}
