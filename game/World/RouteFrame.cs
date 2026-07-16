using Cannonball.Core.Content;
using Godot;

namespace Cannonball.Game.World;

public readonly record struct RouteWorldPoint(double X, double Y, double Z)
{
    public Vector3 RelativeTo(RouteWorldPoint origin) => new(
        (float)(X - origin.X),
        (float)(Y - origin.Y),
        (float)(Z - origin.Z));

    public RouteWorldPoint Add(Vector3 delta) => new(
        X + delta.X,
        Y + delta.Y,
        Z + delta.Z);

    public RouteWorldPoint Lerp(RouteWorldPoint other, double factor) => new(
        X + (other.X - X) * factor,
        Y + (other.Y - Y) * factor,
        Z + (other.Z - Z) * factor);
}

public sealed class RouteFrame
{
    private readonly double _originX;
    private readonly double _originY;
    private readonly double _originElevation;
    private readonly double _forwardX;
    private readonly double _forwardY;
    private readonly double _rightX;
    private readonly double _rightY;

    public RouteFrame(IReadOnlyList<RouteChunkSample> initialSamples)
    {
        ArgumentNullException.ThrowIfNull(initialSamples);
        if (initialSamples.Count < 2)
        {
            throw new InvalidDataException("The initial route chunk needs at least two samples.");
        }

        var first = initialSamples[0];
        _originX = first.ProjectedXMeters;
        _originY = first.ProjectedYMeters;
        _originElevation = first.ElevationMeters;
        _forwardX = first.ProjectedTangentX;
        _forwardY = first.ProjectedTangentY;
        _rightX = _forwardY;
        _rightY = -_forwardX;
        InitialForward = DirectionToWorld(first.ProjectedTangentX, first.ProjectedTangentY);
    }

    public Vector3 InitialForward { get; }

    public RouteWorldPoint ToWorld(RouteChunkSample sample) => ToWorld(
        sample.ProjectedXMeters,
        sample.ProjectedYMeters,
        sample.ElevationMeters);

    public RouteWorldPoint ToWorld(double projectedX, double projectedY, double elevationMeters)
    {
        var deltaX = projectedX - _originX;
        var deltaY = projectedY - _originY;
        return new RouteWorldPoint(
            deltaX * _rightX + deltaY * _rightY,
            elevationMeters - _originElevation,
            -(deltaX * _forwardX + deltaY * _forwardY));
    }

    public Vector3 DirectionToWorld(double projectedX, double projectedY) => new Vector3(
        (float)(projectedX * _rightX + projectedY * _rightY),
        0,
        (float)-(projectedX * _forwardX + projectedY * _forwardY)).Normalized();
}
