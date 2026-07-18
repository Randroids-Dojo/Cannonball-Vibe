using System.Diagnostics;
using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class RoadChunk : Node3D
{
    private StaticBody3D? _collisionBody;
    private ArrayMesh _collisionMesh = null!;

    public string ChunkId { get; private init; } = string.Empty;
    public string EdgeId { get; private init; } = string.Empty;
    public double StartMeters { get; private init; }
    public double EndMeters { get; private init; }
    public double BuildMilliseconds { get; private set; }
    public bool HasCollision => _collisionBody is not null;
    public int MinimumLaneCount { get; private init; }
    public int MaximumLaneCount { get; private init; }
    public int TransitionCount { get; private init; }
    public double MaximumPavedWidthMeters { get; private init; }
    public bool HasGoreGeometry { get; private set; }

    public bool HasReviewGeometry()
    {
        var road = GetNodeOrNull<MeshInstance3D>("RoadSurface");
        var terrain = GetNodeOrNull<MeshInstance3D>("TerrainShoulders");
        var scenery = GetNodeOrNull<MultiMeshInstance3D>("TerrainScenery");
        var barriers = GetNodeOrNull<MultiMeshInstance3D>("RoadBarriers");
        return road is { Visible: true, Mesh: not null } &&
            road.Mesh.GetAabb().Size.LengthSquared() > 0 &&
            terrain is { Visible: true, Mesh: not null } &&
            terrain.Mesh.GetAabb().Size.LengthSquared() > 0 &&
            scenery is { Visible: true, Multimesh: not null } &&
            scenery.Multimesh.InstanceCount > 0 &&
            barriers is { Visible: true, Multimesh: not null } &&
            barriers.Multimesh.InstanceCount > 0;
    }

    public static RoadChunk Create(
        RouteChunkContent content,
        RouteEdge edge,
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
        var layouts = content.Samples
            .Select(sample => LaneGeometryProfile.Evaluate(edge, sample.DistanceMeters))
            .ToArray();
        var chunk = new RoadChunk
        {
            Name = $"RoadChunk-{content.Id}",
            ChunkId = content.Id,
            EdgeId = content.EdgeId,
            StartMeters = content.StartMeters,
            EndMeters = content.EndMeters,
            Position = anchor.RelativeTo(localOriginWorld),
            MinimumLaneCount = layouts.Min(layout =>
                layout.Lanes.Count(lane => lane.WidthMeters > 0.05)),
            MaximumLaneCount = layouts.Max(layout =>
                layout.Lanes.Count(lane => lane.WidthMeters > 0.05)),
            TransitionCount = edge.GetEffectiveLaneSections().Count(section =>
                section.StartMeters > content.StartMeters &&
                section.StartMeters <= content.EndMeters),
            MaximumPavedWidthMeters = layouts.Max(layout => layout.PavedWidthMeters),
        };
        chunk.BuildTerrain(points, tangents, content.Samples, layouts);
        chunk.BuildRoad(points, tangents, content.Samples, layouts);
        chunk.BuildLaneMarkings(points, tangents, content.Samples, layouts);
        chunk.BuildGoreAreas(points, tangents, layouts);
        chunk.BuildBarriers(points, tangents, layouts);
        chunk.BuildScenery(points, tangents, layouts);
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
        _collisionBody.AddChild(new CollisionShape3D
        {
            Shape = _collisionMesh.CreateTrimeshShape(),
        });
        AddChild(_collisionBody);
        return Stopwatch.GetElapsedTime(started).TotalMilliseconds;
    }

    public void ShiftForOriginRebase(Vector3 shift) => Position -= shift;

    private void BuildRoad(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<RouteChunkSample> samples,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        _collisionMesh = BuildRibbonMesh(
            points,
            tangents,
            samples,
            layouts,
            layout => layout.PavedLeftMeters,
            layout => layout.PavedRightMeters,
            -0.035f);
        var shoulderMaterial = new StandardMaterial3D
        {
            AlbedoColor = new Color("34363b"),
            Roughness = 0.97f,
        };
        AddChild(new MeshInstance3D
        {
            Name = "PavedShoulders",
            Mesh = _collisionMesh,
            MaterialOverride = shoulderMaterial,
        });
        var laneMesh = BuildRibbonMesh(
            points,
            tangents,
            samples,
            layouts,
            layout => layout.LaneLeftMeters,
            layout => layout.LaneRightMeters,
            0);
        var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("151820"),
            Roughness = 0.94f,
        };
        AddChild(new MeshInstance3D
        {
            Name = "RoadSurface",
            Mesh = laneMesh,
            MaterialOverride = material,
        });
    }

    private static ArrayMesh BuildRibbonMesh(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<RouteChunkSample> samples,
        IReadOnlyList<LaneGeometrySample> layouts,
        Func<LaneGeometrySample, double> leftOffset,
        Func<LaneGeometrySample, double> rightOffset,
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
            var left0 = center0 + right0Direction * (float)leftOffset(layouts[index]);
            var right0 = center0 + right0Direction * (float)rightOffset(layouts[index]);
            var left1 = center1 + right1Direction * (float)leftOffset(layouts[index + 1]);
            var right1 = center1 + right1Direction * (float)rightOffset(layouts[index + 1]);
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
        IReadOnlyList<RouteChunkSample> samples,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("344536"),
            Roughness = 1.0f,
        };
        AddChild(new MeshInstance3D
        {
            Name = "TerrainShoulders",
            Mesh = BuildRibbonMesh(
                points,
                tangents,
                samples,
                layouts,
                layout => layout.PavedLeftMeters - 40,
                layout => layout.PavedRightMeters + 40,
                -0.18f),
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
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<RouteChunkSample> samples,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        for (var index = 0; index < points.Count - 1; index++)
        {
            var segment = points[index + 1] - points[index];
            if (segment.LengthSquared() < 0.001f)
            {
                continue;
            }
            var firstMarkings = GetMarkingOffsets(layouts[index]);
            var secondMarkings = GetMarkingOffsets(layouts[index + 1]);
            foreach (var id in firstMarkings.Keys.Intersect(
                         secondMarkings.Keys,
                         StringComparer.Ordinal))
            {
                AddDashedMarkingQuads(
                    surface,
                    points[index],
                    points[index + 1],
                    tangents[index],
                    tangents[index + 1],
                    firstMarkings[id],
                    secondMarkings[id],
                    samples[index].DistanceMeters,
                    samples[index + 1].DistanceMeters);
            }
            AddMarkingQuad(
                surface,
                points[index],
                points[index + 1],
                tangents[index],
                tangents[index + 1],
                layouts[index].LaneLeftMeters,
                layouts[index + 1].LaneLeftMeters,
                0.10f);
            AddMarkingQuad(
                surface,
                points[index],
                points[index + 1],
                tangents[index],
                tangents[index + 1],
                layouts[index].LaneRightMeters,
                layouts[index + 1].LaneRightMeters,
                0.10f);
        }
        var markings = surface.Commit();
        var material = new StandardMaterial3D
        {
            AlbedoColor = new Color("d8d5bc"),
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
        };
        AddChild(new MeshInstance3D
        {
            Name = "LaneMarkings",
            Mesh = markings,
            MaterialOverride = material,
        });
    }

    private static void AddDashedMarkingQuads(
        SurfaceTool surface,
        Vector3 first,
        Vector3 second,
        Vector3 firstTangent,
        Vector3 secondTangent,
        double firstOffset,
        double secondOffset,
        double startMeters,
        double endMeters)
    {
        const double dashMeters = 5;
        const double periodMeters = 13;
        if (endMeters <= startMeters)
        {
            return;
        }
        var dashStart = Math.Floor(startMeters / periodMeters) * periodMeters;
        for (; dashStart < endMeters; dashStart += periodMeters)
        {
            var visibleStart = Math.Max(startMeters, dashStart);
            var visibleEnd = Math.Min(endMeters, dashStart + dashMeters);
            if (visibleEnd <= visibleStart)
            {
                continue;
            }
            var firstFactor = (float)((visibleStart - startMeters) / (endMeters - startMeters));
            var secondFactor = (float)((visibleEnd - startMeters) / (endMeters - startMeters));
            AddMarkingQuad(
                surface,
                first.Lerp(second, firstFactor),
                first.Lerp(second, secondFactor),
                firstTangent.Lerp(secondTangent, firstFactor).Normalized(),
                firstTangent.Lerp(secondTangent, secondFactor).Normalized(),
                firstOffset + (secondOffset - firstOffset) * firstFactor,
                firstOffset + (secondOffset - firstOffset) * secondFactor,
                0.07f);
        }
    }

    private static Dictionary<string, double> GetMarkingOffsets(LaneGeometrySample layout)
    {
        var lanes = layout.Lanes
            .Where(lane => lane.WidthMeters > 0.05)
            .OrderBy(lane => lane.CenterMeters)
            .ToArray();
        var result = new Dictionary<string, double>(StringComparer.Ordinal);
        for (var index = 0; index < lanes.Length - 1; index++)
        {
            var left = lanes[index];
            var right = lanes[index + 1];
            result[$"{left.Id}|{right.Id}"] =
                (left.CenterMeters + left.WidthMeters / 2 +
                    right.CenterMeters - right.WidthMeters / 2) / 2;
        }
        return result;
    }

    private static void AddMarkingQuad(
        SurfaceTool surface,
        Vector3 first,
        Vector3 second,
        Vector3 firstTangent,
        Vector3 secondTangent,
        double firstOffset,
        double secondOffset,
        float halfWidth)
    {
        var firstRight = firstTangent.Cross(Vector3.Up).Normalized();
        var secondRight = secondTangent.Cross(Vector3.Up).Normalized();
        var firstCenter = first + firstRight * (float)firstOffset + Vector3.Up * 0.026f;
        var secondCenter = second + secondRight * (float)secondOffset + Vector3.Up * 0.026f;
        var firstLeft = firstCenter - firstRight * halfWidth;
        var firstRightPoint = firstCenter + firstRight * halfWidth;
        var secondLeft = secondCenter - secondRight * halfWidth;
        var secondRightPoint = secondCenter + secondRight * halfWidth;
        AddTriangle(
            surface,
            firstLeft,
            secondRightPoint,
            firstRightPoint,
            Vector2.Zero,
            Vector2.One,
            Vector2.Right);
        AddTriangle(
            surface,
            firstLeft,
            secondLeft,
            secondRightPoint,
            Vector2.Zero,
            Vector2.Up,
            Vector2.One);
    }

    private void BuildGoreAreas(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var transforms = new List<Transform3D>();
        for (var index = 0; index < layouts.Count; index++)
        {
            foreach (var lane in layouts[index].Lanes.Where(lane =>
                         (lane.Role is LaneRole.ExitOnly or LaneRole.EntranceOnly) &&
                         lane.WidthMeters is > 0.2 and < 3.5))
            {
                var right = tangents[index].Cross(Vector3.Up).Normalized();
                var basis = Basis.LookingAt(tangents[index], Vector3.Up);
                transforms.Add(new Transform3D(
                    basis,
                    points[index] + right * (float)lane.CenterMeters + Vector3.Up * 0.04f));
            }
        }
        if (transforms.Count == 0)
        {
            return;
        }
        var mesh = new BoxMesh { Size = new Vector3(0.18f, 0.025f, 2.5f) };
        mesh.Material = new StandardMaterial3D
        {
            AlbedoColor = new Color("e0b14b"),
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
        };
        var multiMesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = mesh,
            InstanceCount = transforms.Count,
        };
        for (var index = 0; index < transforms.Count; index++)
        {
            multiMesh.SetInstanceTransform(index, transforms[index]);
        }
        AddChild(new MultiMeshInstance3D { Name = "GoreAreas", Multimesh = multiMesh });
        HasGoreGeometry = true;
    }

    private void BuildBarriers(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var transforms = new List<Transform3D>();
        for (var index = 0; index < points.Count - 1; index++)
        {
            var length = points[index].DistanceTo(points[index + 1]);
            if (length < 0.01f)
            {
                continue;
            }
            var tangent = (tangents[index] + tangents[index + 1]).Normalized();
            var right = tangent.Cross(Vector3.Up).Normalized();
            var basis = Basis.LookingAt(tangent, Vector3.Up);
            basis.Z *= length;
            var midpoint = points[index].Lerp(points[index + 1], 0.5f) + Vector3.Up * 0.3f;
            var leftOffset = (layouts[index].PavedLeftMeters +
                layouts[index + 1].PavedLeftMeters) / 2 - 0.45;
            var rightOffset = (layouts[index].PavedRightMeters +
                layouts[index + 1].PavedRightMeters) / 2 + 0.45;
            transforms.Add(new Transform3D(basis, midpoint + right * (float)leftOffset));
            transforms.Add(new Transform3D(basis, midpoint + right * (float)rightOffset));
        }
        var mesh = new BoxMesh
        {
            Size = new Vector3(0.18f, 0.6f, 1),
            Material = new StandardMaterial3D
            {
                AlbedoColor = new Color("8b9099"),
                Metallic = 0.7f,
                Roughness = 0.45f,
            },
        };
        var multiMesh = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            Mesh = mesh,
            InstanceCount = transforms.Count,
        };
        for (var index = 0; index < transforms.Count; index++)
        {
            multiMesh.SetInstanceTransform(index, transforms[index]);
        }
        AddChild(new MultiMeshInstance3D { Name = "RoadBarriers", Multimesh = multiMesh });
    }

    private void BuildScenery(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var transforms = new List<Transform3D>();
        for (var index = 0; index < points.Count - 1; index++)
        {
            var tangent = tangents[index];
            var right = tangent.Cross(Vector3.Up).Normalized();
            transforms.Add(new Transform3D(
                Basis.Identity,
                points[index] + right * (float)(layouts[index].PavedLeftMeters - 1.5) +
                    Vector3.Up * 0.55f));
            transforms.Add(new Transform3D(
                Basis.Identity,
                points[index] + right * (float)(layouts[index].PavedRightMeters + 1.5) +
                    Vector3.Up * 0.55f));
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
            var distance = (float)Math.Max(
                Math.Abs(layouts[index].PavedLeftMeters),
                Math.Abs(layouts[index].PavedRightMeters)) + 12 + index % 3 * 2;
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
