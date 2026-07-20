using Cannonball.Core.Runs;
using Cannonball.Core.Simulation.Vehicle;

namespace Cannonball.Core.Tests;

public sealed class DrivingInputConditionerTests
{
    [Fact]
    public void KeyboardSteeringRampsInsteadOfSnappingToFullLock()
    {
        var conditioner = new DrivingInputConditioner();

        var first = conditioner.Step(
            new RawDrivingInput(0, 0, 0, 0, 1, DrivingInputDevice.Keyboard),
            0,
            1.0 / 120,
            AssistProfile.Balanced);

        Assert.InRange(first.Steering, 0.02, 0.04);
        Assert.Equal(1, first.RawSteering);
        Assert.False(first.SteeringSaturated);
    }

    [Fact]
    public void KeyboardSteeringReturnsAndChangesDirectionWithoutSnapping()
    {
        var conditioner = new DrivingInputConditioner();
        for (var frame = 0; frame < 20; frame++)
        {
            conditioner.Step(
                new RawDrivingInput(0, 0, 0, 0, 1, DrivingInputDevice.Keyboard),
                10,
                1.0 / 120,
                AssistProfile.Balanced);
        }
        var positive = conditioner.Current.Steering;

        var reversing = conditioner.Step(
            new RawDrivingInput(0, 0, 0, 0, -1, DrivingInputDevice.Keyboard),
            10,
            1.0 / 120,
            AssistProfile.Balanced);

        Assert.True(positive > 0.4);
        Assert.True(reversing.Steering > 0);
        Assert.True(reversing.Steering < positive);
    }

    [Theory]
    [InlineData(AssistProfile.Accessible, 0.15)]
    [InlineData(AssistProfile.Balanced, 0.11)]
    [InlineData(AssistProfile.Raw, 0.07)]
    public void ControllerDeadzoneRejectsSmallDrift(AssistProfile profile, double drift)
    {
        var conditioner = new DrivingInputConditioner();

        var result = conditioner.Step(
            new RawDrivingInput(0, 0, 0, 0, drift, DrivingInputDevice.Controller),
            0,
            1.0 / 60,
            profile);

        Assert.Equal(0, result.Steering);
        Assert.Equal(0, result.SteeringTarget);
    }

    [Fact]
    public void ControllerCurvePreservesDirectionAndReducesMidStickAuthority()
    {
        var conditioner = new DrivingInputConditioner();

        var result = conditioner.Step(
            new RawDrivingInput(0, 0, 0, 0, -0.5, DrivingInputDevice.Controller),
            0,
            1,
            AssistProfile.Balanced);

        Assert.InRange(result.SteeringTarget, -0.5, -0.2);
        Assert.True(result.Steering < 0);
    }

    [Theory]
    [InlineData(AssistProfile.Accessible, 0.26)]
    [InlineData(AssistProfile.Balanced, 0.31)]
    [InlineData(AssistProfile.Raw, 0.40)]
    public void HighSpeedSteeringUsesDeclaredProfileAuthority(
        AssistProfile profile,
        double expectedAuthority)
    {
        var conditioner = new DrivingInputConditioner();

        var result = conditioner.Step(
            new RawDrivingInput(0, 0, 0, 0, 1, DrivingInputDevice.Keyboard),
            100,
            1,
            profile);

        Assert.Equal(expectedAuthority, result.SteeringAuthority, 6);
        Assert.Equal(expectedAuthority, result.SteeringTarget, 6);
    }

    [Fact]
    public void BrakingWinsOverContradictoryPropulsion()
    {
        var conditioner = new DrivingInputConditioner();

        var result = conditioner.Step(
            new RawDrivingInput(1, 0.7, 0.8, 0, 0, DrivingInputDevice.Keyboard),
            20,
            1,
            AssistProfile.Balanced);

        Assert.Equal(0, result.Throttle);
        Assert.Equal(0, result.Reverse);
        Assert.Equal(0.7, result.ServiceBrake, 6);
    }

    [Fact]
    public void BrakingCancelsExistingPropulsionInTheSameFrame()
    {
        var conditioner = new DrivingInputConditioner();
        conditioner.Step(
            new RawDrivingInput(1, 0, 0, 0, 0, DrivingInputDevice.Controller),
            10,
            0.1,
            AssistProfile.Balanced);

        var braking = conditioner.Step(
            new RawDrivingInput(1, 1, 0, 0, 0, DrivingInputDevice.Controller),
            10,
            1.0 / 120,
            AssistProfile.Balanced);

        Assert.Equal(0, braking.Throttle);
        Assert.Equal(0, braking.Reverse);
        Assert.True(braking.ServiceBrake > 0);
    }

    [Fact]
    public void StationaryHoldReleasesForIntentionalThrottleOrReverse()
    {
        var conditioner = new DrivingInputConditioner();
        var holding = conditioner.Step(
            new RawDrivingInput(0, 0, 0, 0, 0, DrivingInputDevice.Keyboard),
            0.1,
            1.0 / 60,
            AssistProfile.Balanced);
        var accelerating = conditioner.Step(
            new RawDrivingInput(1, 0, 0, 0, 0, DrivingInputDevice.Keyboard),
            0.1,
            1,
            AssistProfile.Balanced);
        conditioner.Reset();
        var reversing = conditioner.Step(
            new RawDrivingInput(0, 0, 1, 0, 0, DrivingInputDevice.Keyboard),
            0.1,
            1,
            AssistProfile.Balanced);

        Assert.True(holding.StationaryHold);
        Assert.False(accelerating.StationaryHold);
        Assert.False(reversing.StationaryHold);
    }

    [Fact]
    public void DisabledInputClearsEveryConditionedChannel()
    {
        var conditioner = new DrivingInputConditioner();
        conditioner.Step(
            new RawDrivingInput(1, 0, 0, 0, 1, DrivingInputDevice.Controller),
            10,
            0.1,
            AssistProfile.Raw);

        var cleared = conditioner.Step(
            new RawDrivingInput(1, 0, 0, 0, 1, DrivingInputDevice.Controller),
            10,
            0.1,
            AssistProfile.Raw,
            inputEnabled: false);

        Assert.Equal(0, cleared.Throttle);
        Assert.Equal(0, cleared.Steering);
        Assert.Equal(DrivingInputDevice.None, cleared.Device);
    }
}
