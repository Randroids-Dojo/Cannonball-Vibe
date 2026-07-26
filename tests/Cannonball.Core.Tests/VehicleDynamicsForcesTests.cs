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

    [Theory]
    [InlineData(0, 0, 0)]
    [InlineData(30, 0, 0)]
    [InlineData(30, 3, 5.7105931375)]
    [InlineData(-30, -3, 5.7105931375)]
    public void SlipAngleUsesVelocityRelativeToVehicleHeading(
        double forwardSpeed,
        double lateralSpeed,
        double expectedDegrees)
    {
        var actual = VehicleDynamicsForces.SlipAngleDegrees(
            forwardSpeed,
            lateralSpeed);

        Assert.Equal(expectedDegrees, actual, precision: 8);
    }

    [Theory]
    [InlineData(0.25, -2_437.5)]
    [InlineData(-0.25, 2_437.5)]
    [InlineData(5, -5_075)]
    [InlineData(-5, 5_075)]
    public void LateralTireForcePreservesDirectionAndCapsAcceleration(
        double lateralSpeed,
        double expectedForce)
    {
        var actual = VehicleDynamicsForces.LateralTireForceNewtons(
            lateralSpeed,
            gripNewtonsPerMeterPerSecond: 7_800,
            responseScale: 1.25,
            vehicleMassKilograms: 1_450,
            maximumLateralAccelerationMetersPerSecondSquared: 14,
            wheelCount: 4);

        Assert.Equal(expectedForce, actual, precision: 8);
    }
}
