using Cannonball.Core.Routes;

namespace Cannonball.Core.Runs;

public enum AssistProfile
{
    Accessible,
    Balanced,
    Raw,
}
public sealed record VehicleCondition(
    double FuelLiters,
    double TireCondition,
    double BrakeCondition,
    double CoolingCondition,
    double Damage);

public sealed record EnforcementState(
    double Visibility,
    double Awareness,
    string PursuitState,
    double CooldownSeconds);

public sealed record BranchStreamSnapshot(
    string DecisionEdgeId,
    IReadOnlyList<string> PrewarmedChunkIds,
    IReadOnlyList<string> SelectedChunkIds)
{
    public static BranchStreamSnapshot Empty { get; } = new(string.Empty, [], []);
}

public sealed record RouteNavigationState(
    string SelectedPlanId,
    string ActiveConnectorId,
    BranchStreamSnapshot BranchStream)
{
    public static RouteNavigationState Empty { get; } =
        new(string.Empty, string.Empty, BranchStreamSnapshot.Empty);
}

public sealed record RunState(
    ulong Seed,
    RoutePosition Position,
    IReadOnlyList<string> RoutePlan,
    double ElapsedSeconds,
    double Cash,
    VehicleCondition Vehicle,
    EnforcementState Enforcement,
    AssistProfile AssistProfile)
{
    public RouteNavigationState Navigation { get; init; } = RouteNavigationState.Empty;
}

public sealed class RunDirector
{
    public RunState Advance(RunState state, double deltaSeconds, double distanceMeters, double fuelUsedLiters)
    {
        if (deltaSeconds < 0 || distanceMeters < 0 || fuelUsedLiters < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(deltaSeconds));
        }

        var position = state.Position with { DistanceMeters = state.Position.DistanceMeters + distanceMeters };
        var vehicle = state.Vehicle with { FuelLiters = Math.Max(0, state.Vehicle.FuelLiters - fuelUsedLiters) };
        return state with
        {
            Position = position,
            Vehicle = vehicle,
            ElapsedSeconds = state.ElapsedSeconds + deltaSeconds,
        };
    }
}
