using System.Diagnostics;
using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Game.World.RoadVisuals;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class RoadChunk : Node3D
{
    private const float RouteContextLabelRangeMeters = 250;
    private StaticBody3D? _collisionBody;
    private ArrayMesh _collisionMesh = null!;
    private List<string>? _routeContextAutomationIds;
    private List<Label3D>? _routeContextLabels;
    private RoadVisualKit _visualKit = null!;

    public string ChunkId { get; private set; } = string.Empty;
    public string EdgeId { get; private set; } = string.Empty;
    public double StartMeters { get; private set; }
    public double EndMeters { get; private set; }
    public double BuildMilliseconds { get; private set; }
    public bool HasCollision => _collisionBody is not null;
    public int MinimumLaneCount { get; private set; }
    public int MaximumLaneCount { get; private set; }
    public int TransitionCount { get; private set; }
    public double MaximumPavedWidthMeters { get; private set; }
    public bool HasGoreGeometry { get; private set; }
    public int MileMarkerCount { get; private set; }
    public int ExitSignCount { get; private set; }
    public int HighwayTransferSignCount { get; private set; }
    public int RouteShieldCount { get; private set; }
    public int ServiceIconCount { get; private set; }
    public int ReflectorCount { get; private set; }
    public int BarrierSegmentCount { get; private set; }
    public int GuardrailSegmentCount { get; private set; }
    public string RoadVisualProfileId => _visualKit.ProfileId;
    public IReadOnlyList<string> RouteContextAutomationIds =>
        _routeContextAutomationIds ?? [];

    public RoadChunkVisualSnapshot CaptureRoadVisualSnapshot()
    {
        var requiredNodes = new[]
        {
            "TerrainShoulders", "PavedShoulders", "RoadSurface", "LaneMarkings",
            "MedianReflectors", "LaneReflectors", "RoadBarriers", "Guardrails",
            "GuardrailPosts", "RoadsidePosts", "TerrainScenery",
        };
        var resolved = requiredNodes
            .Select(name => GetNodeOrNull<Node>(name))
            .Where(node => node is not null)
            .Cast<Node>()
            .ToArray();
        var automationIds = resolved
            .Where(node => node.HasMeta("automation_id"))
            .Select(node => node.GetMeta("automation_id").AsString())
            .ToArray();
        var expectedPrefix = $"road.visual.chunk.{ChunkId}.";
        var semanticMetadataComplete = resolved.All(node =>
            node.HasMeta("automation_id") &&
            node.HasMeta("road_visual_kit") &&
            node.GetMeta("road_visual_kit").AsString() == RoadVisualKit.Version) &&
            automationIds.Length == resolved.Length &&
            automationIds.Distinct(StringComparer.Ordinal).Count() == resolved.Length &&
            automationIds.All(id => id.StartsWith(expectedPrefix, StringComparison.Ordinal));
        return new RoadChunkVisualSnapshot(
            ChunkId,
            _visualKit.ProfileId,
            resolved.Length == requiredNodes.Length && semanticMetadataComplete,
            resolved.Length,
            _visualKit.SharedMaterialCount,
            _visualKit.SharedMeshCount,
            _visualKit.RetroreflectiveMaterialCount,
            ReflectorCount,
            BarrierSegmentCount,
            GuardrailSegmentCount,
            RouteShieldCount,
            ServiceIconCount,
            HasGoreGeometry);
    }

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
            scenery.CastShadow == GeometryInstance3D.ShadowCastingSetting.Off &&
            barriers is { Visible: true, Multimesh: not null } &&
            barriers.Multimesh.InstanceCount > 0;
    }

    public static RoadChunk Create(
        RouteChunkContent content,
        RouteEdge edge,
        RouteContextPlan? routeContextPlan,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld,
        RoadVisualKit visualKit)
    {
        ArgumentNullException.ThrowIfNull(visualKit);
        var chunk = new RoadChunk();
        chunk._visualKit = visualKit;
        var started = Stopwatch.GetTimestamp();
        var anchor = frame.ToWorld(content.Samples[0]);
        var renderSamples = AddLaneTransitionSamples(content.Samples, edge);
        var points = renderSamples
            .Select(sample => frame.ToWorld(sample).RelativeTo(anchor))
            .ToArray();
        var tangents = renderSamples
            .Select(sample => frame.DirectionToWorld(
                sample.ProjectedTangentX,
                sample.ProjectedTangentY))
            .ToArray();
        var layouts = renderSamples
            .Select(sample => LaneGeometryProfile.Evaluate(edge, sample.DistanceMeters))
            .ToArray();
        chunk.Name = $"RoadChunk-{content.Id}";
        RoadVisualKit.MarkSemantic(chunk, $"road.visual.chunk.{content.Id}");
        chunk.SetMeta("road_visual_profile", visualKit.ProfileId);
        chunk.ChunkId = content.Id;
        chunk.EdgeId = content.EdgeId;
        chunk.StartMeters = content.StartMeters;
        chunk.EndMeters = content.EndMeters;
        chunk.Position = anchor.RelativeTo(localOriginWorld);
        chunk.MinimumLaneCount = layouts.Min(layout =>
            layout.Lanes.Count(lane => lane.WidthMeters > 0.05));
        chunk.MaximumLaneCount = layouts.Max(layout =>
            layout.Lanes.Count(lane => lane.WidthMeters > 0.05));
        chunk.TransitionCount = edge.GetEffectiveLaneSections().Count(section =>
            section.StartMeters > content.StartMeters &&
            section.StartMeters <= content.EndMeters);
        chunk.MaximumPavedWidthMeters = layouts.Max(layout => layout.PavedWidthMeters);
        chunk.BuildTerrain(points, tangents, renderSamples, layouts);
        chunk.BuildRoad(points, tangents, renderSamples, layouts);
        chunk.BuildLaneMarkings(points, tangents, renderSamples, layouts);
        chunk.BuildReflectors(points, tangents, layouts);
        chunk.BuildGoreAreas(points, tangents, layouts);
        chunk.BuildBarriers(points, tangents, layouts);
        chunk.BuildScenery(points, tangents, layouts);
        if (routeContextPlan is { Placements.Count: > 0 })
        {
            chunk.BuildRouteContext(content, edge, routeContextPlan, points, tangents, layouts);
        }
        chunk.BuildMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        return chunk;
    }

    private static IReadOnlyList<RouteChunkSample> AddLaneTransitionSamples(
        IReadOnlyList<RouteChunkSample> samples,
        RouteEdge edge)
    {
        var result = samples.ToList();
        var minimum = samples[0].DistanceMeters;
        var maximum = samples[^1].DistanceMeters;
        var criticalDistances = LaneGeometryProfile.GetTransitions(edge)
            .SelectMany(transition => new[]
            {
                transition.StartMeters,
                transition.BoundaryMeters,
                transition.EndMeters,
            })
            .Where(distance => distance > minimum + 1e-9 && distance < maximum - 1e-9)
            .Where(distance => result.All(sample =>
                Math.Abs(sample.DistanceMeters - distance) > 1e-9))
            .Distinct()
            .OrderBy(distance => distance)
            .ToArray();
        foreach (var distance in criticalDistances)
        {
            var afterIndex = result.FindIndex(sample => sample.DistanceMeters > distance);
            var before = result[afterIndex - 1];
            var after = result[afterIndex];
            var factor = (distance - before.DistanceMeters) /
                (after.DistanceMeters - before.DistanceMeters);
            var tangentX = Lerp(before.ProjectedTangentX, after.ProjectedTangentX, factor);
            var tangentY = Lerp(before.ProjectedTangentY, after.ProjectedTangentY, factor);
            var tangentLength = Math.Sqrt(tangentX * tangentX + tangentY * tangentY);
            result.Insert(afterIndex, new RouteChunkSample(
                distance,
                (float)Lerp(before.LateralMeters, after.LateralMeters, factor),
                (float)Lerp(before.ElevationMeters, after.ElevationMeters, factor),
                (float)Lerp(before.Curvature, after.Curvature, factor),
                (float)Lerp(before.Grade, after.Grade, factor),
                Lerp(before.ProjectedXMeters, after.ProjectedXMeters, factor),
                Lerp(before.ProjectedYMeters, after.ProjectedYMeters, factor),
                tangentX / tangentLength,
                tangentY / tangentLength));
        }
        return result;
    }

    private static double Lerp(double from, double to, double factor) =>
        from + (to - from) * factor;

    public IReadOnlyList<RouteContextLabelDiagnostic> GetRouteContextLabelDiagnostics(
        Camera3D camera)
    {
        ArgumentNullException.ThrowIfNull(camera);
        if (_routeContextLabels is null)
        {
            return [];
        }
        var cameraForward = -camera.GlobalBasis.Z;
        return _routeContextLabels.Select(label =>
        {
            var cameraToLabel = label.GlobalPosition - camera.GlobalPosition;
            var cameraDistance = cameraToLabel.Length();
            return new RouteContextLabelDiagnostic(
                label.GetParent().GetMeta("automation_id").AsString(),
                label.Visible && label.IsVisibleInTree(),
                camera.IsPositionInFrustum(label.GlobalPosition),
                cameraDistance,
                cameraToLabel.Dot(cameraForward),
                cameraDistance <= label.VisibilityRangeEnd + 1e-3f);
        }).ToArray();
    }

    private void BuildRouteContext(
        RouteChunkContent content,
        RouteEdge edge,
        RouteContextPlan plan,
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
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
            RoadVisualKit.MarkSemantic(root, automationId);
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
        var board = new MeshInstance3D
        {
            Name = "MarkerBoard",
            Position = new Vector3(0, 1.65f, 0),
            Mesh = new BoxMesh { Size = new Vector3(1.05f, 1.65f, 0.1f) },
            MaterialOverride = _visualKit.SignWhite,
        };
        RoadVisualKit.MarkSemantic(
            board,
            $"{root.GetMeta("automation_id")}.board");
        root.AddChild(board);
        var post = new MeshInstance3D
        {
            Name = "MarkerPost",
            Position = new Vector3(0, 0.72f, 0),
            Mesh = new CylinderMesh
            {
                TopRadius = 0.045f,
                BottomRadius = 0.045f,
                Height = 1.44f,
            },
            MaterialOverride = _visualKit.GalvanizedSteel,
        };
        RoadVisualKit.MarkSemantic(
            post,
            $"{root.GetMeta("automation_id")}.post");
        root.AddChild(post);
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
            new Vector3(0, 1.65f, -0.07f),
            40,
            0.0055f,
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
        var rootId = root.GetMeta("automation_id").AsString();
        var border = new MeshInstance3D
        {
            Name = "GuideBorder",
            Position = new Vector3(0, boardY, 0),
            Mesh = new BoxMesh { Size = new Vector3(boardWidth, boardHeight, 0.14f) },
            MaterialOverride = _visualKit.SignWhite,
        };
        RoadVisualKit.MarkSemantic(border, $"{rootId}.border");
        root.AddChild(border);
        var board = new MeshInstance3D
        {
            Name = "GuideBoard",
            Position = new Vector3(0, boardY, -0.03f),
            Mesh = new BoxMesh
            {
                Size = new Vector3(boardWidth - 0.3f, boardHeight - 0.3f, 0.16f),
            },
            MaterialOverride = _visualKit.GuideGreen,
        };
        RoadVisualKit.MarkSemantic(board, $"{rootId}.board");
        root.AddChild(board);
        var postIndex = 0;
        foreach (var x in new[] { -boardWidth / 2 + 0.7f, boardWidth / 2 - 0.7f })
        {
            var post = new MeshInstance3D
            {
                Name = postIndex == 0 ? "GuidePostLeft" : "GuidePostRight",
                Position = new Vector3(x, boardY / 2, 0),
                Mesh = new CylinderMesh
                {
                    TopRadius = 0.12f,
                    BottomRadius = 0.16f,
                    Height = boardY,
                },
                MaterialOverride = _visualKit.GalvanizedSteel,
            };
            RoadVisualKit.MarkSemantic(post, $"{rootId}.post.{postIndex}");
            root.AddChild(post);
            postIndex++;
        }

        AddSemanticLabel(
            root,
            "ExitNumber",
            placement.PrimaryText.Replace(" // ", "   ", StringComparison.Ordinal),
            new Vector3(0, boardY + 3.45f, -0.13f),
            52,
            0.014f,
            Colors.White,
            "exit-number",
            trackDiagnostic: false);
        var shieldSpacing = 4.4f;
        var shieldStart = -(placement.RouteShields.Count - 1) * shieldSpacing / 2;
        for (var index = 0; index < placement.RouteShields.Count; index++)
        {
            BuildRouteShield(
                root,
                placement.RouteShields[index],
                index,
                shieldStart + index * shieldSpacing,
                boardY + 1.55f);
        }

        var destinationText = placement.SecondaryText.Replace(
            " / ",
            "\n",
            StringComparison.Ordinal);
        AddRouteContextLabel(
            root,
            "GuideText",
            destinationText,
            new Vector3(0, boardY - 0.45f, -0.13f),
            64,
            0.016f,
            Colors.White);

        var exitOnly = layout.Lanes.Any(lane =>
            placement.LaneIds.Contains(lane.Id, StringComparer.Ordinal) &&
            lane.Role == LaneRole.ExitOnly);
        var laneText = placement.LaneGuidance +
            (placement.LaneGuidance.StartsWith("RIGHT", StringComparison.Ordinal)
                ? "   ↘"
                : placement.LaneGuidance.StartsWith("LEFT", StringComparison.Ordinal)
                    ? "   ↙"
                    : "   ↓");
        if (exitOnly)
        {
            var panel = new MeshInstance3D
            {
                Name = "ExitOnlyPanel",
                Position = new Vector3(0, boardY - 3.45f, -0.13f),
                Mesh = new BoxMesh
                {
                    Size = new Vector3(Math.Min(boardWidth - 0.8f, 10), 1.45f, 0.08f),
                },
                MaterialOverride = _visualKit.ExitOnlyYellow,
            };
            RoadVisualKit.MarkSemantic(panel, $"{rootId}.exit-only-panel");
            root.AddChild(panel);
            AddSemanticLabel(
                root,
                "LaneArrow",
                $"EXIT ONLY   {laneText}",
                new Vector3(0, boardY - 3.45f, -0.19f),
                48,
                0.012f,
                new Color("111418"),
                "lane-arrow",
                trackDiagnostic: false);
        }
        else
        {
            AddSemanticLabel(
                root,
                "LaneArrow",
                laneText,
                new Vector3(0, boardY - 2.75f, -0.13f),
                48,
                0.012f,
                Colors.White,
                "lane-arrow",
                trackDiagnostic: false);
        }
        BuildServiceIcons(root, placement.Services, boardWidth, boardY);
    }

    private void BuildRouteShield(
        Node3D guideRoot,
        string shieldText,
        int index,
        float x,
        float y)
    {
        var normalized = shieldText.StartsWith("TO ", StringComparison.Ordinal)
            ? shieldText[3..]
            : shieldText;
        var parts = normalized.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var interstate = parts.Length > 0 &&
            (string.Equals(parts[0], "I", StringComparison.Ordinal) ||
                parts[0].StartsWith("I-", StringComparison.Ordinal));
        var number = parts.Length == 0
            ? normalized
            : parts[0].StartsWith("I-", StringComparison.Ordinal)
                ? parts[0][2..]
                : parts.Length > 1
                    ? parts[1]
                    : parts[0];
        var direction = parts.LastOrDefault(value => value is
            "NORTH" or "SOUTH" or "EAST" or "WEST") ?? string.Empty;
        var guideId = guideRoot.GetMeta("automation_id").AsString();
        var shield = new Node3D
        {
            Name = $"RouteShield{index}",
            Position = new Vector3(x, y, -0.14f),
        };
        RoadVisualKit.MarkSemantic(shield, $"{guideId}.shield.{index}");
        guideRoot.AddChild(shield);
        var backing = new MeshInstance3D
        {
            Name = "ShieldSilhouette",
            Mesh = BuildShieldFaceMesh(interstate),
            MaterialOverride = interstate
                ? _visualKit.InterstateBlue
                : _visualKit.SignWhite,
        };
        RoadVisualKit.MarkSemantic(backing, $"{guideId}.shield.{index}.silhouette");
        shield.AddChild(backing);
        if (interstate)
        {
            var header = new MeshInstance3D
            {
                Name = "InterstateHeader",
                Position = new Vector3(0, 0.92f, -0.025f),
                Mesh = new BoxMesh { Size = new Vector3(2.55f, 0.48f, 0.035f) },
                MaterialOverride = _visualKit.InterstateRed,
            };
            RoadVisualKit.MarkSemantic(header, $"{guideId}.shield.{index}.header");
            shield.AddChild(header);
        }
        AddSemanticLabel(
            shield,
            "ShieldSystem",
            interstate ? "INTERSTATE" : "US",
            new Vector3(0, 0.86f, -0.045f),
            interstate ? 24 : 30,
            0.007f,
            interstate ? Colors.White : new Color("111418"),
            "system",
            trackDiagnostic: false);
        AddSemanticLabel(
            shield,
            "ShieldNumber",
            number,
            new Vector3(0, -0.02f, -0.045f),
            64,
            0.013f,
            interstate ? Colors.White : new Color("111418"),
            "number",
            trackDiagnostic: false);
        if (!string.IsNullOrEmpty(direction))
        {
            AddSemanticLabel(
                shield,
                "ShieldDirection",
                direction,
                new Vector3(0, 1.72f, -0.045f),
                34,
                0.009f,
                Colors.White,
                "direction",
                trackDiagnostic: false);
        }
        RouteShieldCount++;
    }

    private static ArrayMesh BuildShieldFaceMesh(bool interstate)
    {
        var points = interstate
            ? new[]
            {
                new Vector3(-1.45f, 1.2f, 0), new Vector3(1.45f, 1.2f, 0),
                new Vector3(1.28f, 0.45f, 0), new Vector3(0.92f, -0.85f, 0),
                new Vector3(0, -1.38f, 0), new Vector3(-0.92f, -0.85f, 0),
                new Vector3(-1.28f, 0.45f, 0),
            }
            : new[]
            {
                new Vector3(-1.35f, 1.28f, 0), new Vector3(1.35f, 1.28f, 0),
                new Vector3(1.16f, 0.55f, 0), new Vector3(0.95f, -0.75f, 0),
                new Vector3(0, -1.32f, 0), new Vector3(-0.95f, -0.75f, 0),
                new Vector3(-1.16f, 0.55f, 0),
            };
        var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        for (var index = 1; index < points.Length - 1; index++)
        {
            AddTriangle(
                surface,
                points[0],
                points[index],
                points[index + 1],
                Vector2.Zero,
                Vector2.Right,
                Vector2.One);
        }
        surface.GenerateNormals();
        return surface.Commit();
    }

    private void BuildServiceIcons(
        Node3D root,
        IReadOnlyList<string> services,
        float boardWidth,
        float boardY)
    {
        var shown = services.Take(4).ToArray();
        var spacing = Math.Min(2.8f, (boardWidth - 1) / Math.Max(shown.Length, 1));
        var start = -(shown.Length - 1) * spacing / 2;
        var rootId = root.GetMeta("automation_id").AsString();
        for (var index = 0; index < shown.Length; index++)
        {
            var panel = new MeshInstance3D
            {
                Name = $"ServicePanel{index}",
                Position = new Vector3(start + index * spacing, boardY - 5.35f, -0.06f),
                Mesh = new BoxMesh { Size = new Vector3(2.45f, 1.25f, 0.12f) },
                MaterialOverride = _visualKit.ServiceBlue,
            };
            RoadVisualKit.MarkSemantic(panel, $"{rootId}.service.{index}.panel");
            root.AddChild(panel);
            AddSemanticLabel(
                root,
                $"ServiceIcon{index}",
                shown[index].ToUpperInvariant(),
                new Vector3(start + index * spacing, boardY - 5.35f, -0.14f),
                32,
                0.009f,
                Colors.White,
                $"service.{index}.text",
                trackDiagnostic: false);
            ServiceIconCount++;
        }
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
        AddSemanticLabel(
            root,
            name,
            text,
            position,
            fontSize,
            pixelSize,
            color,
            "text",
            trackDiagnostic: true);
    }

    private void AddSemanticLabel(
        Node3D root,
        string name,
        string text,
        Vector3 position,
        int fontSize,
        float pixelSize,
        Color color,
        string automationSuffix,
        bool trackDiagnostic)
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
        RoadVisualKit.MarkSemantic(
            label,
            $"{root.GetMeta("automation_id")}.{automationSuffix}");
        if (trackDiagnostic)
        {
            (_routeContextLabels ??= []).Add(label);
        }
        root.AddChild(label);
    }

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
        var shoulders = new MeshInstance3D
        {
            Name = "PavedShoulders",
            Mesh = _collisionMesh,
            MaterialOverride = _visualKit.Shoulder,
        };
        MarkRoadSemantic(shoulders, "paved-shoulders");
        AddChild(shoulders);
        var laneMesh = BuildRibbonMesh(
            points,
            tangents,
            samples,
            layouts,
            layout => layout.LaneLeftMeters,
            layout => layout.LaneRightMeters,
            0);
        var surface = new MeshInstance3D
        {
            Name = "RoadSurface",
            Mesh = laneMesh,
            MaterialOverride = _visualKit.Pavement,
        };
        MarkRoadSemantic(surface, "pavement");
        AddChild(surface);
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
        var terrain = new MeshInstance3D
        {
            Name = "TerrainShoulders",
            Mesh = BuildRibbonMesh(
                points,
                tangents,
                samples,
                layouts,
                layout => layout.PavedLeftMeters - RoadVisualKit.TerrainMarginMeters,
                layout => layout.PavedRightMeters + RoadVisualKit.TerrainMarginMeters,
                -0.18f),
            MaterialOverride = _visualKit.Terrain,
            CastShadow = GeometryInstance3D.ShadowCastingSetting.Off,
        };
        MarkRoadSemantic(terrain, "terrain-shoulders");
        AddChild(terrain);
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
        var laneMarkings = new MeshInstance3D
        {
            Name = "LaneMarkings",
            Mesh = markings,
            MaterialOverride = _visualKit.MarkingWhite,
        };
        MarkRoadSemantic(laneMarkings, "lane-markings");
        AddChild(laneMarkings);
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
            .Where(lane => lane.WidthMeters > 0.05 && !lane.IsTransitioning)
            .OrderBy(lane => lane.CenterMeters)
            .ThenBy(lane => lane.Index)
            .ThenBy(lane => lane.Id, StringComparer.Ordinal)
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

    private void BuildReflectors(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var yellow = new List<Transform3D>();
        var white = new List<Transform3D>();
        for (var index = 0; index < points.Count; index++)
        {
            var tangent = tangents[index].Normalized();
            var right = tangent.Cross(Vector3.Up).Normalized();
            var basis = Basis.LookingAt(tangent, Vector3.Up);
            var layout = layouts[index];
            yellow.Add(new Transform3D(
                basis,
                points[index] + right * (float)layout.LaneLeftMeters + Vector3.Up * 0.045f));
            white.Add(new Transform3D(
                basis,
                points[index] + right * (float)layout.LaneRightMeters + Vector3.Up * 0.045f));
            foreach (var offset in GetMarkingOffsets(layout).Values)
            {
                white.Add(new Transform3D(
                    basis,
                    points[index] + right * (float)offset + Vector3.Up * 0.045f));
            }
        }
        AddMultiMesh(
            "MedianReflectors",
            "reflectors.median",
            _visualKit.ReflectorMesh,
            yellow,
            _visualKit.ReflectorYellow);
        AddMultiMesh(
            "LaneReflectors",
            "reflectors.lane-and-shoulder",
            _visualKit.ReflectorMesh,
            white,
            _visualKit.ReflectorWhite);
        ReflectorCount = yellow.Count + white.Count;
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

    private void AddMultiMesh(
        string name,
        string automationSuffix,
        Mesh mesh,
        IReadOnlyList<Transform3D> transforms,
        Material? materialOverride = null,
        GeometryInstance3D.ShadowCastingSetting castShadow =
            GeometryInstance3D.ShadowCastingSetting.On)
    {
        if (transforms.Count == 0)
        {
            return;
        }
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
        var instance = new MultiMeshInstance3D
        {
            Name = name,
            Multimesh = multiMesh,
            MaterialOverride = materialOverride,
            CastShadow = castShadow,
        };
        MarkRoadSemantic(instance, automationSuffix);
        AddChild(instance);
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
        var mesh = new BoxMesh
        {
            Size = new Vector3(0.18f, 0.025f, 2.5f),
        };
        AddMultiMesh("GoreAreas", "gore-markings", mesh, transforms, _visualKit.Gore);
        HasGoreGeometry = true;
    }

    private void BuildBarriers(
        IReadOnlyList<Vector3> points,
        IReadOnlyList<Vector3> tangents,
        IReadOnlyList<LaneGeometrySample> layouts)
    {
        var barrierTransforms = new List<Transform3D>();
        var guardrailTransforms = new List<Transform3D>();
        var guardrailPostTransforms = new List<Transform3D>();
        for (var index = 0; index < points.Count - 1; index++)
        {
            var length = points[index].DistanceTo(points[index + 1]);
            if (length < 0.01f)
            {
                continue;
            }
            var tangent = (tangents[index] + tangents[index + 1]).Normalized();
            var right = tangent.Cross(Vector3.Up).Normalized();
            var segmentBasis = Basis.LookingAt(tangent, Vector3.Up);
            var stretchedBasis = segmentBasis;
            stretchedBasis.Z *= length;
            var midpoint = points[index].Lerp(points[index + 1], 0.5f);
            var leftOffset = (layouts[index].PavedLeftMeters +
                layouts[index + 1].PavedLeftMeters) / 2 - 0.45;
            var rightOffset = (layouts[index].PavedRightMeters +
                layouts[index + 1].PavedRightMeters) / 2 + 0.45;
            barrierTransforms.Add(new Transform3D(
                stretchedBasis,
                midpoint + right * (float)leftOffset + Vector3.Up * 0.41f));
            guardrailTransforms.Add(new Transform3D(
                stretchedBasis,
                midpoint + right * (float)rightOffset + Vector3.Up * 0.72f));
            guardrailPostTransforms.Add(new Transform3D(
                segmentBasis,
                points[index] + right * (float)rightOffset + Vector3.Up * 0.4f));
        }
        AddMultiMesh(
            "RoadBarriers",
            "median-barriers",
            _visualKit.MedianBarrierMesh,
            barrierTransforms);
        AddMultiMesh(
            "Guardrails",
            "guardrails",
            _visualKit.GuardrailMesh,
            guardrailTransforms);
        AddMultiMesh(
            "GuardrailPosts",
            "guardrail-posts",
            _visualKit.GuardrailPostMesh,
            guardrailPostTransforms);
        BarrierSegmentCount = barrierTransforms.Count;
        GuardrailSegmentCount = guardrailTransforms.Count;
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

        AddMultiMesh(
            "RoadsidePosts",
            "delineator-posts",
            _visualKit.DelineatorMesh,
            transforms);

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
            Material = _visualKit.Terrain,
        };
        AddMultiMesh(
            "TerrainScenery",
            "placeholder-scenery",
            treeMesh,
            treeTransforms,
            castShadow: GeometryInstance3D.ShadowCastingSetting.Off);
    }

    private void MarkRoadSemantic(Node node, string suffix) =>
        RoadVisualKit.MarkSemantic(node, $"road.visual.chunk.{ChunkId}.{suffix}");
}

public sealed record RouteContextLabelDiagnostic(
    string AutomationId,
    bool VisibleInTree,
    bool InCameraFrustum,
    float CameraDistanceMeters,
    float ForwardDistanceMeters,
    bool WithinDeclaredRange);

public sealed record RoadChunkVisualSnapshot(
    string ChunkId,
    string ProfileId,
    bool ContractResolved,
    int SemanticNodeCount,
    int SharedMaterialCount,
    int SharedMeshCount,
    int RetroreflectiveMaterialCount,
    int ReflectorCount,
    int BarrierSegmentCount,
    int GuardrailSegmentCount,
    int RouteShieldCount,
    int ServiceIconCount,
    bool HasGoreGeometry);
