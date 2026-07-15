namespace Cannonball.Game.World;

public static class RoadMath
{
    public const double RouteLengthMeters = 40_233.6;

    public static float CenterX(double distanceMeters) =>
        (float)(Math.Sin(distanceMeters / 850.0) * 24.0 + Math.Sin(distanceMeters / 2_900.0) * 42.0);

    public static float Elevation(double distanceMeters) =>
        (float)(Math.Sin(distanceMeters / 1_800.0) * 2.5);
}
