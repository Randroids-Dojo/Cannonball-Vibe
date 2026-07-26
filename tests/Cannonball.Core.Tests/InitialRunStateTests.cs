using Cannonball.Core.Runs;

namespace Cannonball.Core.Tests;

public sealed class InitialRunStateTests
{
    [Fact]
    public void CreateRestoresDeterministicNewRunValuesWithoutReusingMutableProgress()
    {
        var initial = InitialRunState.Create(42, AssistProfile.Raw);
        var changedVehicle = initial.Vehicle with { FuelLiters = 3, Damage = 0.8 };
        var changedEnforcement = initial.Enforcement with
        {
            Awareness = 0.9,
            PursuitState = "active",
        };

        var restarted = InitialRunState.Create(initial.Seed, initial.AssistProfile);

        Assert.Equal((ulong)42, restarted.Seed);
        Assert.Equal(25_000, restarted.Cash);
        Assert.Equal(new VehicleCondition(82, 1, 1, 1, 0), restarted.Vehicle);
        Assert.Equal(new EnforcementState(0, 0, "clear", 0), restarted.Enforcement);
        Assert.Equal(AssistProfile.Raw, restarted.AssistProfile);
        Assert.NotEqual(changedVehicle, restarted.Vehicle);
        Assert.NotEqual(changedEnforcement, restarted.Enforcement);
    }
}
