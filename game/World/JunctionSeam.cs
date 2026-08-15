using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Game.World.RoadVisuals;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class JunctionSeam : Node3D
{
    private StaticBody3D? _collisionBody;
    private ArrayMesh _collisionMesh = null!;

    public string FromChunkId { get; private init; } = string.Empty;
    public string ToChunkId { get; private init; } = string.Empty;
    public bool HasCollision => _collisionBody is not null;
    public bool HasTerrainSurface =>
        GetNodeOrNull<MeshInstance3D>("JunctionTerrainSurface") is
            { Mesh: not null, Visible: true };
    public double ConnectionGapMeters { get; private init; }

    public static JunctionSeam Create(
        RouteChunkContent fromContent,
        RouteEdge fromEdge,
        RouteChunkContent toContent,
        RouteEdge toEdge,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld,
        RoadVisualKit visualKit)
    {
        ArgumentNullException.ThrowIfNull(visualKit);
        var anchor = frame.ToWorld(fromContent.Samples[^1]);
        var fromCenter = anchor.RelativeTo(anchor);
        var toCenter = frame.ToWorld(toContent.Samples[0]).RelativeTo(anchor);
        var fromTangent = frame.DirectionToWorld(
            fromContent.Samples[^1].ProjectedTangentX,
            fromContent.Samples[^1].ProjectedTangentY);
        var toTangent = frame.DirectionToWorld(
            toContent.Samples[0].ProjectedTangentX,
            toContent.Samples[0].ProjectedTangentY);
        var connectionGapMeters = fromCenter.DistanceTo(toCenter);
        if (connectionGapMeters < 0.05f)
        {
            const float bridgeHalfLengthMeters = 0.35f;
            fromCenter -= fromTangent * bridgeHalfLengthMeters;
            toCenter += toTangent * bridgeHalfLengthMeters;
        }
        var fromLayout = LaneGeometryProfile.Evaluate(fromEdge, fromContent.EndMeters);
        var toLayout = LaneGeometryProfile.Evaluate(toEdge, toContent.StartMeters);
        var semanticId = $"{fromContent.Id}.{toContent.Id}";
        var seam = new JunctionSeam
        {
            Name = $"JunctionSeam-{semanticId}",
            FromChunkId = fromContent.Id,
            ToChunkId = toContent.Id,
            Position = anchor.RelativeTo(localOriginWorld),
            ConnectionGapMeters = connectionGapMeters,
        };
        seam._collisionMesh = BuildQuad(
            fromCenter,
            fromTangent,
            fromLayout.PavedLeftMeters,
            fromLayout.PavedRightMeters,
            toCenter,
            toTangent,
            toLayout.PavedLeftMeters,
            toLayout.PavedRightMeters,
            -0.035f);
        var terrain = new MeshInstance3D
        {
            Name = "JunctionTerrainSurface",
            Mesh = seam.Owned(BuildQuad(
                fromCenter,
                fromTangent,
                fromLayout.PavedLeftMeters - RoadVisualKit.TerrainMarginMeters,
                fromLayout.PavedRightMeters + RoadVisualKit.TerrainMarginMeters,
                toCenter,
                toTangent,
                toLayout.PavedLeftMeters - RoadVisualKit.TerrainMarginMeters,
                toLayout.PavedRightMeters + RoadVisualKit.TerrainMarginMeters,
                -0.16f)),
            MaterialOverride = visualKit.Terrain,
            CastShadow = GeometryInstance3D.ShadowCastingSetting.Off,
        };
        RoadVisualKit.MarkSemantic(
            terrain,
            $"road.visual.junction.{semanticId}.terrain");
        seam.AddChild(terrain);
        var paved = new MeshInstance3D
        {
            Name = "JunctionPavedSurface",
            Mesh = seam._collisionMesh,
            MaterialOverride = visualKit.Shoulder,
        };
        RoadVisualKit.MarkSemantic(
            paved,
            $"road.visual.junction.{semanticId}.paved");
        seam.AddChild(paved);
        var road = new MeshInstance3D
        {
            Name = "JunctionRoadSurface",
            Mesh = seam.Owned(BuildQuad(
                fromCenter,
                fromTangent,
                fromLayout.LaneLeftMeters,
                fromLayout.LaneRightMeters,
                toCenter,
                toTangent,
                toLayout.LaneLeftMeters,
                toLayout.LaneRightMeters,
                0.02f)),
            MaterialOverride = visualKit.Pavement,
        };
        RoadVisualKit.MarkSemantic(
            road,
            $"road.visual.junction.{semanticId}.road");
        seam.AddChild(road);
        return seam;
    }

    public void SetCollisionActive(bool active)
    {
        if (active == HasCollision)
        {
            return;
        }
        if (!active)
        {
            var body = _collisionBody!;
            body.CollisionLayer = 0;
            RemoveChild(body);
            body.Free();
            _collisionBody = null;
            return;
        }
        _collisionBody = new StaticBody3D
        {
            Name = "JunctionCollision",
            CollisionLayer = 1,
            CollisionMask = 2,
        };
        // The shape is owned by the CollisionShape3D once assigned; releasing the
        // local wrapper keeps no stray reference alive past engine shutdown.
        using (var trimesh = _collisionMesh.CreateTrimeshShape())
        {
            _collisionBody.AddChild(new CollisionShape3D { Shape = trimesh });
        }
        AddChild(_collisionBody);
    }

    public void ShiftForOriginRebase(Vector3 shift) => Position -= shift;

    private static ArrayMesh BuildQuad(
        Vector3 fromCenter,
        Vector3 fromTangent,
        double fromLeft,
        double fromRight,
        Vector3 toCenter,
        Vector3 toTangent,
        double toLeft,
        double toRight,
        float verticalOffset)
    {
        var fromDirection = fromTangent.Cross(Vector3.Up).Normalized();
        var toDirection = toTangent.Cross(Vector3.Up).Normalized();
        var vertical = Vector3.Up * verticalOffset;
        var fromLeftPoint = fromCenter + fromDirection * (float)fromLeft + vertical;
        var fromRightPoint = fromCenter + fromDirection * (float)fromRight + vertical;
        var toLeftPoint = toCenter + toDirection * (float)toLeft + vertical;
        var toRightPoint = toCenter + toDirection * (float)toRight + vertical;
        using var surface = new SurfaceTool();
        surface.Begin(Mesh.PrimitiveType.Triangles);
        surface.AddVertex(fromLeftPoint);
        surface.AddVertex(toRightPoint);
        surface.AddVertex(fromRightPoint);
        surface.AddVertex(fromLeftPoint);
        surface.AddVertex(toLeftPoint);
        surface.AddVertex(toRightPoint);
        surface.GenerateNormals();
        return surface.Commit();
    }


    // Godot resources are RefCounted, and a C# wrapper holds one of those
    // references until it is disposed or finalised. A chunk that is QueueFree'd
    // frees its node immediately, but any resource wrapper still held in a field
    // survives to finalisation, which can run after the engine has torn down.
    // That is what produces "Leaked unsafe reference to object" at shutdown and,
    // intermittently, a segmentation fault in the Linux smoke.
    //
    // Predelete fires only on actual destruction, unlike _ExitTree which also
    // fires on reparenting, so releasing here cannot strand a live node.
    public override void _Notification(int what)
    {
        if (what == NotificationPredelete)
        {
            _collisionMesh?.Dispose();
            _collisionMesh = null!;
            ReleaseOwnedResources();
        }
    }


    // Godot resources are RefCounted and their C# wrappers hold one of those
    // references. A wrapper built inline in a node initializer is dropped as soon
    // as the initializer completes, so nothing disposes it and it survives to
    // finalisation, which can run after the engine has torn down. That is what
    // produces "Leaked unsafe reference to object" at shutdown and, intermittently,
    // a segmentation fault in the Linux smoke.
    //
    // Wrapping a construction in Owned() records it so the wrapper is released with
    // this node. The node it was assigned to holds its own reference, so releasing
    // ours never affects anything rendering.
    private readonly List<Resource> _ownedResources = [];

    private T Owned<T>(T resource) where T : Resource
    {
        _ownedResources.Add(resource);
        return resource;
    }

    private void ReleaseOwnedResources()
    {
        foreach (var resource in _ownedResources)
        {
            resource.Dispose();
        }
        _ownedResources.Clear();
    }
}
