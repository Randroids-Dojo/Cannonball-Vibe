using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Godot;

namespace Cannonball.Game.World;

public sealed partial class JunctionSeam : Node3D
{
    private StaticBody3D? _collisionBody;
    private ArrayMesh _collisionMesh = null!;

    public string FromChunkId { get; private init; } = string.Empty;
    public string ToChunkId { get; private init; } = string.Empty;
    public bool HasCollision => _collisionBody is not null;

    public static JunctionSeam Create(
        RouteChunkContent fromContent,
        RouteEdge fromEdge,
        RouteChunkContent toContent,
        RouteEdge toEdge,
        RouteFrame frame,
        RouteWorldPoint localOriginWorld)
    {
        var anchor = frame.ToWorld(fromContent.Samples[^1]);
        var fromCenter = anchor.RelativeTo(anchor);
        var toCenter = frame.ToWorld(toContent.Samples[0]).RelativeTo(anchor);
        var fromTangent = frame.DirectionToWorld(
            fromContent.Samples[^1].ProjectedTangentX,
            fromContent.Samples[^1].ProjectedTangentY);
        var toTangent = frame.DirectionToWorld(
            toContent.Samples[0].ProjectedTangentX,
            toContent.Samples[0].ProjectedTangentY);
        if (fromCenter.DistanceSquaredTo(toCenter) < 0.0025f)
        {
            const float bridgeHalfLengthMeters = 0.35f;
            fromCenter -= fromTangent * bridgeHalfLengthMeters;
            toCenter += toTangent * bridgeHalfLengthMeters;
        }
        var fromLayout = LaneGeometryProfile.Evaluate(fromEdge, fromEdge.LengthMeters);
        var toLayout = LaneGeometryProfile.Evaluate(toEdge, 0);
        var seam = new JunctionSeam
        {
            Name = $"JunctionSeam-{fromEdge.Id}-{toEdge.Id}",
            FromChunkId = fromContent.Id,
            ToChunkId = toContent.Id,
            Position = anchor.RelativeTo(localOriginWorld),
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
        seam.AddChild(new MeshInstance3D
        {
            Name = "JunctionPavedSurface",
            Mesh = seam._collisionMesh,
            MaterialOverride = new StandardMaterial3D
            {
                AlbedoColor = new Color("34363b"),
                Roughness = 0.97f,
                CullMode = BaseMaterial3D.CullModeEnum.Disabled,
            },
        });
        seam.AddChild(new MeshInstance3D
        {
            Name = "JunctionRoadSurface",
            Mesh = BuildQuad(
                fromCenter,
                fromTangent,
                fromLayout.LaneLeftMeters,
                fromLayout.LaneRightMeters,
                toCenter,
                toTangent,
                toLayout.LaneLeftMeters,
                toLayout.LaneRightMeters,
                0.02f),
            MaterialOverride = new StandardMaterial3D
            {
                AlbedoColor = new Color("151820"),
                Roughness = 0.94f,
                CullMode = BaseMaterial3D.CullModeEnum.Disabled,
            },
        });
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
        _collisionBody.AddChild(new CollisionShape3D
        {
            Shape = _collisionMesh.CreateTrimeshShape(),
        });
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
        var surface = new SurfaceTool();
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

}
