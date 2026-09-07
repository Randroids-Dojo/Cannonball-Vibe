using Cannonball.Core.Simulation.Vehicle;

namespace Cannonball.Core.Tests;

public sealed class VehicleSetupTests
{
    [Fact]
    public void StarterTapersOnlyTheLastMphAndCutsPowerAtItsCap()
    {
        var setup = VehicleSetup.Starter;
        Assert.Equal(55.88, setup.ForwardTopSpeedMetersPerSecond, 8);
        Assert.Equal(1, setup.ForwardDriveScale(100 * VehicleSetup.MetersPerSecondPerMph));
        Assert.Equal(0.5, setup.ForwardDriveScale(124.5 * VehicleSetup.MetersPerSecondPerMph), 8);
        Assert.Equal(0, setup.ForwardDriveScale(55.88), 8);
        Assert.Equal(0, setup.ForwardDriveScale(90));
        Assert.Equal(1, setup.ForwardDriveScale(-90));
    }

    [Fact]
    public void OverspeedRemovalDoesNotLimitReverseOrAddSpeed()
    {
        var setup = VehicleSetup.Starter;
        Assert.Equal(0, setup.ForwardOverspeedMetersPerSecond(-90));
        Assert.Equal(0, setup.ForwardOverspeedMetersPerSecond(30));
        Assert.Equal(0, setup.ForwardOverspeedMetersPerSecond(55.88), 8);
        Assert.Equal(4.12, setup.ForwardOverspeedMetersPerSecond(60), 8);
    }

    [Fact]
    public void DifferentSetupChangesTheCapWithoutChangingTheStarter()
    {
        var configured = new VehicleSetup("tuning-fixture", 150);
        Assert.Equal(67.056, configured.ForwardTopSpeedMetersPerSecond, 8);
        Assert.Equal(1, configured.ForwardDriveScale(60));
        Assert.Equal(0, configured.ForwardOverspeedMetersPerSecond(60));
        Assert.Equal(125, VehicleSetup.Starter.ForwardTopSpeedMph);
        Assert.Equal(1, VehicleSetup.HighSpeedValidation.ForwardDriveScale(200 * 0.44704));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(double.NegativeInfinity)]
    public void InvalidCapIsRejected(double cap) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new VehicleSetup("invalid", cap));

    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(double.NegativeInfinity)]
    public void InvalidSpeedIsRejected(double speed)
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => VehicleSetup.Starter.ForwardDriveScale(speed));
        Assert.Throws<ArgumentOutOfRangeException>(() => VehicleSetup.Starter.ForwardOverspeedMetersPerSecond(speed));
    }
}
