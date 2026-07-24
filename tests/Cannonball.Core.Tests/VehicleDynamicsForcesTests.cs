using Cannonball.Core.Simulation.Vehicle;

namespace Cannonball.Core.Tests;

public sealed class VehicleDynamicsForcesTests
{
    [Fact]
    public void SuspensionForceCapsHardLandingLoad()
    {
        var force = VehicleDynamicsForces.SuspensionForceNewtons(
            compressionMeters: 0.62,
            springStrengthNewtonsPerMeter: 42_000,
            velocityAlongSupportNormalMetersPerSecond: -18,
            dampingNewtonsPerMeterPerSecond: 5_500,
            vehicleMassKilograms: 1_450,
            gravityMetersPerSecondSquared: 9.80665,
            maximumLoadG: 6.5,
            wheelCount: 4);

        Assert.Equal(23_106.9190625, force, precision: 6);
    }

    [Fact]
    public void SuspensionForceDoesNotPullAnExtendedWheelTowardRoad()
    {
        var force = VehicleDynamicsForces.SuspensionForceNewtons(
            compressionMeters: 0,
            springStrengthNewtonsPerMeter: 42_000,
            velocityAlongSupportNormalMetersPerSecond: 4,
            dampingNewtonsPerMeterPerSecond: 5_500,
            vehicleMassKilograms: 1_450,
            gravityMetersPerSecondSquared: 9.80665,
            maximumLoadG: 6.5,
            wheelCount: 4);

        Assert.Equal(0, force);
    }

    [Theory]
    [InlineData(0, 0)]
    [InlineData(1, 0.2176376408)]
    [InlineData(2, 0.4665164958)]
    [InlineData(4, 1)]
    public void PartialContactProgressivelyRestoresDriveAuthority(
        int supportedWheels,
        double expected)
    {
        var authority = VehicleDynamicsForces.ContactDriveAuthority(
            supportedWheels,
            wheelCount: 4,
            responseExponent: 1.1);

        Assert.Equal(expected, authority, precision: 8);
    }

    [Fact]
    public void AirborneAerodynamicLoadIsBounded()
    {
        var load = VehicleDynamicsForces.AerodynamicLoadNewtons(
            speedMetersPerSecond: 90,
            coefficient: 2.75,
            vehicleMassKilograms: 1_450,
            gravityMetersPerSecondSquared: 9.80665,
            maximumLoadG: 1.1);

        Assert.Equal(15_641.60675, load, precision: 5);
    }
}
