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
        double longitudinalSpeedMetersPerSecond,
        double corneringStiffnessNewtonsPerRadian,
        double responseScale,
        double normalLoadNewtons,
        double frictionCoefficient,
        double vehicleMassKilograms,
        double maximumLateralAccelerationMetersPerSecondSquared,
        int wheelCount)
    {
        RequireFinite(lateralSpeedMetersPerSecond, nameof(lateralSpeedMetersPerSecond));
        RequireFinite(longitudinalSpeedMetersPerSecond,
            nameof(longitudinalSpeedMetersPerSecond));
        RequireFiniteNonNegative(
            corneringStiffnessNewtonsPerRadian,
            nameof(corneringStiffnessNewtonsPerRadian));
        RequireFiniteNonNegative(responseScale, nameof(responseScale));
        RequireFiniteNonNegative(normalLoadNewtons, nameof(normalLoadNewtons));
        RequireFiniteNonNegative(frictionCoefficient, nameof(frictionCoefficient));
        RequireFinitePositive(vehicleMassKilograms, nameof(vehicleMassKilograms));
        RequireFinitePositive(
            maximumLateralAccelerationMetersPerSecondSquared,
            nameof(maximumLateralAccelerationMetersPerSecondSquared));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(wheelCount);

        var referenceLongitudinalSpeed = Math.Max(Math.Abs(longitudinalSpeedMetersPerSecond), 0.5);
        var slipAngleRadians = Math.Atan2(
            lateralSpeedMetersPerSecond,
            referenceLongitudinalSpeed);
        var requested = -slipAngleRadians *
            corneringStiffnessNewtonsPerRadian * responseScale;
        var chassisMaximum = vehicleMassKilograms *
            maximumLateralAccelerationMetersPerSecondSquared / wheelCount;
        var loadMaximum = normalLoadNewtons * frictionCoefficient;
        var maximum = Math.Min(chassisMaximum, loadMaximum);
        return Math.Clamp(requested, -maximum, maximum);
    }

    public static double CoastResistanceForceNewtons(
        double speedMetersPerSecond,
        double vehicleMassKilograms,
        double gravityMetersPerSecondSquared,
        double rollingResistanceCoefficient,
        double engineBrakingBaseNewtons,
        double engineBrakingNewtonsPerMeterPerSecond,
        double propulsionInput,
        double contactRatio)
    {
        RequireFiniteNonNegative(speedMetersPerSecond, nameof(speedMetersPerSecond));
        RequireFinitePositive(vehicleMassKilograms, nameof(vehicleMassKilograms));
        RequireFinitePositive(gravityMetersPerSecondSquared,
            nameof(gravityMetersPerSecondSquared));
        RequireFiniteNonNegative(rollingResistanceCoefficient,
            nameof(rollingResistanceCoefficient));
        RequireFiniteNonNegative(engineBrakingBaseNewtons,
            nameof(engineBrakingBaseNewtons));
        RequireFiniteNonNegative(engineBrakingNewtonsPerMeterPerSecond,
            nameof(engineBrakingNewtonsPerMeterPerSecond));
        RequireFiniteNonNegative(propulsionInput, nameof(propulsionInput));
        RequireFiniteNonNegative(contactRatio, nameof(contactRatio));

        if (speedMetersPerSecond < 0.05 || contactRatio <= 0)
        {
            return 0;
        }

        var boundedContact = Math.Clamp(contactRatio, 0, 1);
        var rolling = vehicleMassKilograms * gravityMetersPerSecondSquared *
            rollingResistanceCoefficient;
        var engineBraking = (engineBrakingBaseNewtons +
                speedMetersPerSecond * engineBrakingNewtonsPerMeterPerSecond) *
            (1 - Math.Clamp(propulsionInput, 0, 1));
        return (rolling + engineBraking) * boundedContact;
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
