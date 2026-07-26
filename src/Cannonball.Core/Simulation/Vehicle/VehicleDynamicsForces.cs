namespace Cannonball.Core.Simulation.Vehicle;

public static class VehicleDynamicsForces
{
    public static double SuspensionForceNewtons(
        double compressionMeters,
        double springStrengthNewtonsPerMeter,
        double velocityAlongSupportNormalMetersPerSecond,
        double dampingNewtonsPerMeterPerSecond,
        double vehicleMassKilograms,
        double gravityMetersPerSecondSquared,
        double maximumLoadG,
        int wheelCount)
    {
        RequireFiniteNonNegative(compressionMeters, nameof(compressionMeters));
        RequireFinitePositive(springStrengthNewtonsPerMeter, nameof(springStrengthNewtonsPerMeter));
        RequireFinite(velocityAlongSupportNormalMetersPerSecond,
            nameof(velocityAlongSupportNormalMetersPerSecond));
        RequireFiniteNonNegative(dampingNewtonsPerMeterPerSecond,
            nameof(dampingNewtonsPerMeterPerSecond));
        RequireFinitePositive(vehicleMassKilograms, nameof(vehicleMassKilograms));
        RequireFinitePositive(gravityMetersPerSecondSquared,
            nameof(gravityMetersPerSecondSquared));
        RequireFinitePositive(maximumLoadG, nameof(maximumLoadG));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(wheelCount);

        var requested = compressionMeters * springStrengthNewtonsPerMeter -
            velocityAlongSupportNormalMetersPerSecond * dampingNewtonsPerMeterPerSecond;
        var maximum = vehicleMassKilograms * gravityMetersPerSecondSquared *
            maximumLoadG / wheelCount;
        return Math.Clamp(requested, 0, maximum);
    }

    public static double ContactDriveAuthority(
        int supportedWheelCount,
        int wheelCount,
        double responseExponent)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(supportedWheelCount);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(wheelCount);
        if (supportedWheelCount > wheelCount)
        {
            throw new ArgumentOutOfRangeException(nameof(supportedWheelCount));
        }
        RequireFinitePositive(responseExponent, nameof(responseExponent));
        return Math.Pow((double)supportedWheelCount / wheelCount, responseExponent);
    }

    public static double AerodynamicLoadNewtons(
        double speedMetersPerSecond,
        double coefficient,
        double vehicleMassKilograms,
        double gravityMetersPerSecondSquared,
        double maximumLoadG,
        double assistScale = 1)
    {
        RequireFiniteNonNegative(speedMetersPerSecond, nameof(speedMetersPerSecond));
        RequireFiniteNonNegative(coefficient, nameof(coefficient));
        RequireFinitePositive(vehicleMassKilograms, nameof(vehicleMassKilograms));
        RequireFinitePositive(gravityMetersPerSecondSquared,
            nameof(gravityMetersPerSecondSquared));
        RequireFiniteNonNegative(maximumLoadG, nameof(maximumLoadG));
        RequireFiniteNonNegative(assistScale, nameof(assistScale));

        var requested = speedMetersPerSecond * speedMetersPerSecond * coefficient *
            assistScale;
        var maximum = vehicleMassKilograms * gravityMetersPerSecondSquared *
            maximumLoadG * assistScale;
        return Math.Min(requested, maximum);
    }

    public static double SlipAngleDegrees(
        double forwardSpeedMetersPerSecond,
        double lateralSpeedMetersPerSecond)
    {
        RequireFinite(forwardSpeedMetersPerSecond, nameof(forwardSpeedMetersPerSecond));
        RequireFinite(lateralSpeedMetersPerSecond, nameof(lateralSpeedMetersPerSecond));
        if (Math.Abs(forwardSpeedMetersPerSecond) < 0.01 &&
            Math.Abs(lateralSpeedMetersPerSecond) < 0.01)
        {
            return 0;
        }
        return Math.Abs(Math.Atan2(
            lateralSpeedMetersPerSecond,
            Math.Abs(forwardSpeedMetersPerSecond))) * 180 / Math.PI;
    }

    public static double LateralTireForceNewtons(
        double lateralSpeedMetersPerSecond,
        double gripNewtonsPerMeterPerSecond,
        double responseScale,
        double vehicleMassKilograms,
        double maximumLateralAccelerationMetersPerSecondSquared,
        int wheelCount)
    {
        RequireFinite(lateralSpeedMetersPerSecond, nameof(lateralSpeedMetersPerSecond));
        RequireFiniteNonNegative(
            gripNewtonsPerMeterPerSecond,
            nameof(gripNewtonsPerMeterPerSecond));
        RequireFiniteNonNegative(responseScale, nameof(responseScale));
        RequireFinitePositive(vehicleMassKilograms, nameof(vehicleMassKilograms));
        RequireFinitePositive(
            maximumLateralAccelerationMetersPerSecondSquared,
            nameof(maximumLateralAccelerationMetersPerSecondSquared));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(wheelCount);

        var requested = -lateralSpeedMetersPerSecond *
            gripNewtonsPerMeterPerSecond * responseScale;
        var maximum = vehicleMassKilograms *
            maximumLateralAccelerationMetersPerSecondSquared / wheelCount;
        return Math.Clamp(requested, -maximum, maximum);
    }

    private static void RequireFinite(double value, string parameterName)
    {
        if (!double.IsFinite(value))
        {
            throw new ArgumentOutOfRangeException(parameterName);
        }
    }

    private static void RequireFinitePositive(double value, string parameterName)
    {
        if (!double.IsFinite(value) || value <= 0)
        {
            throw new ArgumentOutOfRangeException(parameterName);
        }
    }

    private static void RequireFiniteNonNegative(double value, string parameterName)
    {
        if (!double.IsFinite(value) || value < 0)
        {
            throw new ArgumentOutOfRangeException(parameterName);
        }
    }
}
