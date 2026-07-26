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
    [InlineData(0.25, -458.3227242075)]
    [InlineData(-0.25, 458.3227242075)]
    [InlineData(5, -4_025)]
    [InlineData(-5, 4_025)]
    public void LateralTireForceUsesSlipAngleAndLoadSensitiveLimit(
        double lateralSpeed,
        double expectedForce)
    {
        var actual = VehicleDynamicsForces.LateralTireForceNewtons(
            lateralSpeed,
            longitudinalSpeedMetersPerSecond: 30,
            corneringStiffnessNewtonsPerRadian: 55_000,
            responseScale: 1,
            normalLoadNewtons: 3_500,
            frictionCoefficient: 1.15,
            vehicleMassKilograms: 1_450,
            maximumLateralAccelerationMetersPerSecondSquared: 14,
            wheelCount: 4);

        Assert.Equal(expectedForce, actual, precision: 8);
    }

    [Fact]
    public void UnloadedTireCannotGenerateLateralForce()
    {
        var actual = VehicleDynamicsForces.LateralTireForceNewtons(
            lateralSpeedMetersPerSecond: 4,
            longitudinalSpeedMetersPerSecond: 30,
            corneringStiffnessNewtonsPerRadian: 55_000,
            responseScale: 1,
            normalLoadNewtons: 0,
            frictionCoefficient: 1.15,
            vehicleMassKilograms: 1_450,
            maximumLateralAccelerationMetersPerSecondSquared: 14,
            wheelCount: 4);

        Assert.Equal(0, actual);
    }

    [Theory]
    [InlineData(0, 0)]
    [InlineData(0.5, 434.317855)]
    [InlineData(1, 868.63571)]
    public void CoastResistanceCombinesRollingAndLiftOffEngineBraking(
        double contactRatio,
        double expectedForce)
    {
        var actual = VehicleDynamicsForces.CoastResistanceForceNewtons(
            speedMetersPerSecond: 31,
            vehicleMassKilograms: 1_450,
            gravityMetersPerSecondSquared: 9.80665,
            rollingResistanceCoefficient: 0.012,
            engineBrakingBaseNewtons: 450,
            engineBrakingNewtonsPerMeterPerSecond: 8,
            propulsionInput: 0,
            contactRatio: contactRatio);

        Assert.Equal(expectedForce, actual, precision: 8);
    }

    [Fact]
    public void PropulsionRemovesEngineBrakingButKeepsRollingResistance()
    {
        var actual = VehicleDynamicsForces.CoastResistanceForceNewtons(
            speedMetersPerSecond: 31,
            vehicleMassKilograms: 1_450,
            gravityMetersPerSecondSquared: 9.80665,
            rollingResistanceCoefficient: 0.012,
            engineBrakingBaseNewtons: 450,
            engineBrakingNewtonsPerMeterPerSecond: 8,
            propulsionInput: 1,
            contactRatio: 1);

        Assert.Equal(170.63571, actual, precision: 8);
    }
}
