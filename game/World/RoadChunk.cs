using System.Diagnostics;
using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class RoadChunk : Node3D
{
    private const float RouteContextLabelRangeMeters = 250;
    private StaticBody3D? _collisionBody;
    private ArrayMesh _collisionMesh = null!;
    private List<string>? _routeContextAutomationIds;

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
    public int MileMarkerCount { get; private set; }
    public int ExitSignCount { get; private set; }
    public int HighwayTransferSignCount { get; private set; }
    public IReadOnlyList<string> RouteContextAutomationIds =>
        _routeContextAutomationIds ?? [];

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
        IRouteGraph graph,
        RouteSemanticContent? semantics,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld)
    {
        var hasRenderableRouteContext = semantics is not null &&
            !semantics.IsLegacySynthesis &&
            HasRenderableRouteContext(edge, semantics);
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
        if (hasRenderableRouteContext)
        {
            chunk.BuildRouteContext(content, edge, graph, semantics!, points, tangents, layouts);
        }
        chunk.BuildMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        return chunk;
    }

    private static bool HasRenderableRouteContext(
        RouteEdge edge,
        RouteSemanticContent semantics) =>
        semantics.RoadsideMarkers.Any(marker =>
            string.Equals(marker.Kind, "mile", StringComparison.OrdinalIgnoreCase) &&
            string.Equals(marker.EdgeId, edge.Id, StringComparison.Ordinal)) ||
        semantics.Exits.Any(routeExit =>
            string.Equals(routeExit.JunctionNodeId, edge.ToNodeId, StringComparison.Ordinal) &&
            edge.RouteIdentityIds.Contains(routeExit.RouteIdentityId, StringComparer.Ordinal));

    private void BuildRouteContext(
        RouteChunkContent content,
        RouteEdge edge,
        IRouteGraph graph,
        RouteSemanticContent semantics,
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var plan = RouteContextPlanner.BuildForEdge(graph, semantics, edge.Id);
        var placements = plan.ForChunk(
            content.StartMeters,
            content.EndMeters,
            includeEnd: Math.Abs(content.EndMeters - edge.LengthMeters) <= 1e-6);
        foreach (var placement in placements)
        {
            var (point, tangent, layout) = SamplePlacement(
                content,
                placement.DistanceMeters,
                points,
                tangents,
                layouts);
            var right = tangent.Cross(Vector3.Up).Normalized();
            var lateral = placement.Mount switch
            {
                RouteContextMount.LeftRoadside => (float)layout.PavedLeftMeters - 2.2f,
                RouteContextMount.RightRoadside => (float)layout.PavedRightMeters + 2.2f,
                RouteContextMount.Overhead => 0,
                _ => throw new ArgumentOutOfRangeException(nameof(placement.Mount)),
            };
            var root = new Node3D
            {
                Name = $"RouteContext-{placement.Id}",
                Position = point + right * lateral,
                Basis = Basis.LookingAt(-tangent, Vector3.Up),
            };
            var automationId = placement.Kind switch
            {
                RouteContextPlacementKind.MileMarker => $"route-context.marker.{placement.Id}",
                RouteContextPlacementKind.ExitSign => $"route-context.exit.{placement.Id}",
                RouteContextPlacementKind.HighwayTransferSign =>
                    $"route-context.transfer.{placement.Id}",
                _ => throw new ArgumentOutOfRangeException(nameof(placement.Kind)),
            };
            root.SetMeta("automation_id", automationId);
            root.SetMeta("edge_id", placement.EdgeId);
            root.SetMeta("edge_distance_meters", placement.DistanceMeters);
            root.SetMeta("route_identity_id", placement.RouteIdentityId);
            root.SetMeta("signed_direction", placement.SignedDirection);
            root.SetMeta("jurisdiction", placement.Jurisdiction);
            root.SetMeta("exact_route_reference", placement.ExactRouteReference);
            root.SetMeta("route_shields", string.Join(',', placement.RouteShields));
            root.SetMeta("lane_guidance", placement.LaneGuidance);
            root.SetMeta("lane_ids", string.Join(',', placement.LaneIds));
            root.SetMeta("services", string.Join(',', placement.Services));
            root.SetMeta("provenance_kind", placement.Provenance.Kind.ToString());
            root.SetMeta("provenance_source_id", placement.Provenance.SourceId);
            (_routeContextAutomationIds ??= []).Add(automationId);
            AddChild(root);

            if (placement.Kind == RouteContextPlacementKind.MileMarker)
            {
                BuildMileMarker(root, placement);
                MileMarkerCount++;
            }
            else
            {
                BuildGuideSign(root, placement, layout);
                if (placement.Kind == RouteContextPlacementKind.HighwayTransferSign)
                {
                    HighwayTransferSignCount++;
                }
                else
                {
                    ExitSignCount++;
                }
            }
        }
    }

    private void BuildMileMarker(Node3D root, RouteContextPlacement placement)
    {
        var boardMaterial = UnshadedMaterial(new Color("f4f5ef"));
        root.AddChild(new MeshInstance3D
        {
            Name = "MarkerBoard",
            Position = new Vector3(0, 2.05f, 0),
            Mesh = new BoxMesh { Size = new Vector3(1.8f, 2.5f, 0.12f) },
            MaterialOverride = boardMaterial,
        });
        root.AddChild(new MeshInstance3D
        {
            Name = "MarkerPost",
            Position = new Vector3(0, 0.8f, 0),
            Mesh = new CylinderMesh
            {
                TopRadius = 0.06f,
                BottomRadius = 0.06f,
                Height = 1.6f,
            },
            MaterialOverride = UnshadedMaterial(new Color("8b8e87")),
        });
        var direction = placement.SignedDirection.ToUpperInvariant();
        var routeText = placement.PrimaryText.EndsWith(
                $" {direction}",
                StringComparison.Ordinal)
            ? placement.PrimaryText[..^(direction.Length + 1)]
            : placement.PrimaryText;
        AddRouteContextLabel(
            root,
            "MarkerText",
            $"{routeText}\n{direction}\n{placement.SecondaryText}",
            new Vector3(0, 2.05f, -0.08f),
            36,
            0.008f,
            new Color("101820"));
    }

    private void BuildGuideSign(
        Node3D root,
        RouteContextPlacement placement,
        LaneGeometrySample layout)
    {
        var boardWidth = Math.Clamp((float)layout.PavedWidthMeters + 8, 18, 24);
        const float boardHeight = 9.2f;
        const float boardY = 10.8f;
        root.AddChild(new MeshInstance3D
        {
            Name = "GuideBoard",
            Position = new Vector3(0, boardY, 0),
            Mesh = new BoxMesh { Size = new Vector3(boardWidth, boardHeight, 0.18f) },
            MaterialOverride = UnshadedMaterial(
                placement.Kind == RouteContextPlacementKind.HighwayTransferSign
                    ? new Color("174a91")
                    : new Color("17613a")),
        });
        var postMaterial = UnshadedMaterial(new Color("a8adb0"));
        foreach (var x in new[] { -boardWidth / 2 + 0.5f, boardWidth / 2 - 0.5f })
        {
            root.AddChild(new MeshInstance3D
            {
                Name = "GuidePost",
                Position = new Vector3(x, boardY / 2, 0),
                Mesh = new CylinderMesh
                {
                    TopRadius = 0.12f,
                    BottomRadius = 0.16f,
                    Height = boardY,
                },
                MaterialOverride = postMaterial,
            });
        }
        var destinationText = placement.SecondaryText.Replace(" / ", "\n", StringComparison.Ordinal);
        var serviceText = placement.Services.Count == 0
            ? string.Empty
            : $"\nSERVICES: {string.Join("  ", placement.Services).ToUpperInvariant()}";
        var routeShieldText = string.Join(
            "  |  ",
            placement.RouteShields.Select(shield => $"[{shield}]"));
        AddRouteContextLabel(
            root,
            "GuideText",
            $"{placement.PrimaryText}\n{routeShieldText}\n{destinationText}" +
            $"\n{placement.LaneGuidance}{serviceText}",
            new Vector3(0, boardY, -0.11f),
            56,
            0.018f,
            Colors.White);
    }

    private void AddRouteContextLabel(
        Node3D root,
        string name,
        string text,
        Vector3 position,
        int fontSize,
        float pixelSize,
        Color color)
    {
        var label = new Label3D
        {
            Name = name,
            Text = text,
            Position = position,
            FontSize = fontSize,
            PixelSize = pixelSize,
            Modulate = color,
            OutlineSize = 4,
            NoDepthTest = false,
            DoubleSided = false,
            CastShadow = GeometryInstance3D.ShadowCastingSetting.Off,
            RotationDegrees = new Vector3(0, 180, 0),
            VisibilityRangeEnd = RouteContextLabelRangeMeters,
            VisibilityRangeEndMargin = 35,
            VisibilityRangeFadeMode = GeometryInstance3D.VisibilityRangeFadeModeEnum.Self,
        };
        label.SetMeta("automation_id", $"{root.GetMeta("automation_id")}.text");
        root.AddChild(label);
    }

    private static StandardMaterial3D UnshadedMaterial(Color color) => new()
    {
        AlbedoColor = color,
        ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
    };

    private static (
        Vector3 Point,
        Vector3 Tangent,
        LaneGeometrySample Layout) SamplePlacement(
        RouteChunkContent content,
        double distanceMeters,
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        for (var index = 0; index < content.Samples.Count - 1; index++)
        {
            var first = content.Samples[index].DistanceMeters;
            var second = content.Samples[index + 1].DistanceMeters;
            if (distanceMeters < first || distanceMeters > second)
            {
                continue;
            }
            var factor = second <= first ? 0 : (distanceMeters - first) / (second - first);
            return (
                points[index].Lerp(points[index + 1], (float)factor),
                tangents[index].Lerp(tangents[index + 1], (float)factor).Normalized(),
                factor < 0.5 ? layouts[index] : layouts[index + 1]);
        }

        throw new InvalidDataException(
            $"Route-context placement at {distanceMeters:F3} meters is outside chunk " +
            $"'{content.Id}'.");
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
