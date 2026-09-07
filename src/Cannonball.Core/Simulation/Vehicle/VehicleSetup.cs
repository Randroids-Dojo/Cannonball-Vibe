namespace Cannonball.Core.Simulation.Vehicle;

/// <summary>Vehicle performance configuration, separate from driver assists.</summary>
public sealed class VehicleSetup
{
    public const double MetersPerSecondPerMph = 0.44704;

    // Initial stock tuning; full-run balance and upgrade progression remain open.
    public static VehicleSetup Starter { get; } = new("starter", 125);

    // Preserve the existing 200 mph dynamics/streaming corpus. This is a test
    // fixture, not a purchasable upgrade or an alternate starting vehicle.
    public static VehicleSetup HighSpeedValidation { get; } = new("high-speed-validation", 250);

    public VehicleSetup(string id, double forwardTopSpeedMph)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(id);
        if (!double.IsFinite(forwardTopSpeedMph) || forwardTopSpeedMph <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(forwardTopSpeedMph));
        }
        Id = id;
        ForwardTopSpeedMph = forwardTopSpeedMph;
    }

    public string Id { get; }
    public double ForwardTopSpeedMph { get; }
    public double ForwardTopSpeedMetersPerSecond => ForwardTopSpeedMph * MetersPerSecondPerMph;

    /// <summary>Taper positive engine drive through the final 1 mph.</summary>
    public double ForwardDriveScale(double signedForwardSpeedMetersPerSecond)
    {
        RequireFiniteSpeed(signedForwardSpeedMetersPerSecond);
        var taper = Math.Min(MetersPerSecondPerMph, ForwardTopSpeedMetersPerSecond);
        return Math.Clamp(
            (ForwardTopSpeedMetersPerSecond - signedForwardSpeedMetersPerSecond) / taper,
            0, 1);
    }

    /// <summary>Forward excess only; reverse speed is unaffected.</summary>
    public double ForwardOverspeedMetersPerSecond(double signedForwardSpeedMetersPerSecond)
    {
        RequireFiniteSpeed(signedForwardSpeedMetersPerSecond);
        return Math.Max(0, signedForwardSpeedMetersPerSecond - ForwardTopSpeedMetersPerSecond);
    }

    private static void RequireFiniteSpeed(double speed)
    {
        if (!double.IsFinite(speed))
        {
            throw new ArgumentOutOfRangeException(nameof(speed));
        }
    }
}
