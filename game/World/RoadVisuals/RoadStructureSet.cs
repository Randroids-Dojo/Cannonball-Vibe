using Godot;

namespace Cannonball.Game.World.RoadVisuals;

public enum RoadStructureKind
{
    Bridge,
    Overpass,
}

public sealed record RoadStructurePlacement(
    string Id,
    RoadStructureKind Kind,
    string UpperEdgeId,
    string LowerEdgeId,
    double ProjectedXMeters,
    double ProjectedYMeters,
    double ElevationMeters,
    double ProjectedTangentX,
    double ProjectedTangentY,
    double UpperEdgeDistanceMeters,
    double DeckLengthMeters,
    double DeckWidthMeters,
    double VerticalClearanceMeters);

public sealed partial class RoadStructureSet : Node3D
{
    private readonly IReadOnlyList<RoadStructurePlacement> _placements;
    private readonly RoadVisualKit _kit;

    private RoadStructureSet(
        IReadOnlyList<RoadStructurePlacement> placements,
        RoadVisualKit kit)
    {
        _placements = placements;
        _kit = kit;
    }

    public static RoadStructureSet Create(
        IReadOnlyList<RoadStructurePlacement> placements,
        RoadVisualKit kit,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld)
    {
        ArgumentNullException.ThrowIfNull(placements);
        ArgumentNullException.ThrowIfNull(kit);
        var set = new RoadStructureSet(placements, kit)
        {
            Name = "RoadStructures",
        };
        RoadVisualKit.MarkSemantic(set, "road.visual.structures");
        foreach (var placement in placements.OrderBy(item => item.Id, StringComparer.Ordinal))
        {
            set.AddStructure(placement, frame, localOriginWorld);
        }
        return set;
    }

    public void ShiftForOriginRebase(Vector3 shift) => Position -= shift;

    public RoadStructurePlacement? ReviewPlacement => _placements
        .OrderBy(item => item.Id, StringComparer.Ordinal)
        .FirstOrDefault();

    public bool ConfigureReviewCamera(Camera3D camera)
    {
        var root = GetChildren().OfType<Node3D>()
            .OrderBy(node => node.Name.ToString(), StringComparer.Ordinal)
            .FirstOrDefault();
        if (root is null)
        {
            return false;
        }
        var target = root.GlobalPosition + Vector3.Down * 3.0f;
        var side = root.GlobalBasis.X.Normalized();
        var along = root.GlobalBasis.Z.Normalized();
        camera.GlobalPosition = target + side * 28 + along * 14 + Vector3.Up * 2.5f;
        camera.LookAt(target, Vector3.Up);
        camera.Fov = 58;
        camera.Current = true;
        return true;
    }

    public RoadStructureSnapshot CaptureSnapshot()
    {
        var roots = GetChildren().OfType<Node3D>().ToArray();
        var semanticNodes = roots
            .SelectMany(root => root.FindChildren("*", owned: false).Append(root))
            .ToArray();
        var contractResolved = roots.Length == _placements.Count &&
            semanticNodes.All(node =>
                node.HasMeta("automation_id") &&
                node.HasMeta("road_visual_kit") &&
                node.GetMeta("road_visual_kit").AsString() == RoadVisualKit.Version) &&
            semanticNodes.Select(node => node.GetMeta("automation_id").AsString())
                .Distinct(StringComparer.Ordinal).Count() == semanticNodes.Length &&
            !semanticNodes.OfType<CollisionObject3D>().Any();
        return new RoadStructureSnapshot(
            roots.Length,
            roots.Length,
            roots.Length,
            semanticNodes.Length,
            contractResolved);
    }

    private void AddStructure(
        RoadStructurePlacement placement,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld)
    {
        var worldPoint = frame.ToWorld(
            placement.ProjectedXMeters,
            placement.ProjectedYMeters,
            placement.ElevationMeters);
        var forward = frame.DirectionToWorld(
            placement.ProjectedTangentX,
            placement.ProjectedTangentY);
        var root = new Node3D
        {
            Name = $"RoadStructure-{placement.Id}",
            Position = worldPoint.RelativeTo(localOriginWorld),
            Basis = Basis.LookingAt(forward, Vector3.Up),
        };
        var prefix = $"road.visual.structure.{placement.Id}";
        RoadVisualKit.MarkSemantic(root, prefix);
        root.SetMeta("structure_kind", placement.Kind.ToString().ToLowerInvariant());
        root.SetMeta("upper_edge_id", placement.UpperEdgeId);
        root.SetMeta("lower_edge_id", placement.LowerEdgeId);
        root.SetMeta("vertical_clearance_m", placement.VerticalClearanceMeters);

        AddPart(root, "Deck", $"{prefix}.deck", _kit.BridgeDeckMesh,
            new Vector3((float)placement.DeckWidthMeters, 1, (float)placement.DeckLengthMeters),
            new Vector3(0, -0.2f, 0));

        var girderOffset = (float)placement.DeckWidthMeters * 0.32f;
        foreach (var (suffix, offset) in new[]
                 {
                     ("left", -girderOffset), ("center", 0f), ("right", girderOffset),
                 })
        {
            AddPart(root, $"Girder-{suffix}", $"{prefix}.girder.{suffix}",
                _kit.BridgeGirderMesh,
                new Vector3(1, 1, (float)placement.DeckLengthMeters),
                new Vector3(offset, -0.66f, 0));
        }

        var supportHeight = (float)Math.Max(2.5, placement.VerticalClearanceMeters - 0.5);
        var supportY = -0.48f - supportHeight / 2;
        var supportZ = (float)placement.DeckLengthMeters * 0.42f;
        foreach (var (suffix, offset) in new[] { ("near", -supportZ), ("far", supportZ) })
        {
            AddPart(root, $"Abutment-{suffix}", $"{prefix}.abutment.{suffix}",
                _kit.BridgeAbutmentMesh,
                new Vector3((float)placement.DeckWidthMeters + 1.5f, supportHeight, 1),
                new Vector3(0, supportY, offset));
        }
        var pierZ = (float)placement.DeckLengthMeters * 0.29f;
        foreach (var (suffix, offset) in new[] { ("near", -pierZ), ("far", pierZ) })
        {
            AddPart(root, $"Pier-{suffix}", $"{prefix}.pier.{suffix}",
                _kit.BridgePierMesh,
                new Vector3(1, supportHeight, 1),
                new Vector3(0, supportY, offset));
        }

        var barrierOffset = (float)placement.DeckWidthMeters / 2 - 0.2f;
        foreach (var (suffix, offset) in new[] { ("left", -barrierOffset), ("right", barrierOffset) })
        {
            AddPart(root, $"DeckBarrier-{suffix}", $"{prefix}.barrier.{suffix}",
                _kit.MedianBarrierMesh,
                new Vector3(1, 1, (float)placement.DeckLengthMeters),
                new Vector3(offset, 0.25f, 0));
        }
        AddChild(root);
    }

    private static void AddPart(
        Node3D root,
        string name,
        string automationId,
        Mesh mesh,
        Vector3 scale,
        Vector3 position)
    {
        var part = new MeshInstance3D
        {
            Name = name,
            Mesh = mesh,
            Scale = scale,
            Position = position,
        };
        RoadVisualKit.MarkSemantic(part, automationId);
        root.AddChild(part);
    }
}

public sealed record RoadStructureSnapshot(
    int BridgeDeckCount,
    int OverpassOpeningCount,
    int StructureCount,
    int SemanticNodeCount,
    bool ContractResolved);
