using Cannonball.Core.Runs;

namespace Cannonball.Game.Vehicle;

public static class VehicleDynamicsProfile
{
    public const float VehicleMassKilograms = 1_450;
    public const float GravityMetersPerSecondSquared = 9.80665f;
    public const float SpringRestLengthMeters = 0.62f;
    public const float MaximumSuspensionTravelMeters = SpringRestLengthMeters;
    public const float SuspensionBottomOutThresholdMeters = 0.60f;
    public const int MaximumSuspensionBottomOutFrames = 36;
    public const float WheelRadiusMeters = 0.34f;
    public const float CenterOfMassOffsetMeters = -0.30f;
    public const float SpringStrengthNewtonsPerMeter = 42_000;
    public const float SpringDampingNewtonsPerMeterPerSecond = 5_500;
    public const float MaximumSuspensionLoadG = 6.5f;
    public const float EngineForceNewtons = 25_000;
    public const float BrakeForceNewtons = 36_000;
    public const float LateralGripNewtonsPerMeterPerSecond = 7_800;
    public const float MaximumLateralAccelerationMetersPerSecondSquared = 14;
    public const float AerodynamicDragCoefficient = 0.42f;
    public const float GroundedDownforceCoefficient = 9;
    public const float MaximumGroundedDownforceG = 3;
    public const float AirborneDownforceCoefficient = 8;
    public const float MaximumAirborneDownforceG = 1.1f;
    public const float MaximumSteerAngleRadians = 0.38f;
    public const float UprightTorqueNewtonMeters = 36_000;
    public const float TiltDampingNewtonMeterSeconds = 3_000;
    public const float YawDampingNewtonMeterSeconds = 850;

    // P0-019 owner-reported incline regression. These bands were fixed before force tuning.
    public static VehicleDynamicsAcceptanceBands HighSpeedInclineBands { get; } = new(
        EntrySpeedMetersPerSecond: 70,
        GradeRise: 0.08f,
        MaximumUnsupportedSeconds: 0.75f,
        MaximumChassisTiltDegrees: 55,
        MaximumAngularSpeedRadiansPerSecond: 4,
        MaximumLandingRecoverySeconds: 1.5f);

    // P0-019 speed-band limits. These are intentionally recorded before the
    // complete dynamics corpus is run so failures tune the model, not the gate.
    public static IReadOnlyList<VehicleDynamicsSpeedBand> SpeedBands { get; } =
    [
        new(
            Id: "cruise",
            SpeedMetersPerSecond: 31,
            MaximumStraightSpeedLossMetersPerSecond: 5,
            MaximumStoppingDistanceMeters: 75,
            MaximumStoppingSeconds: 5,
            SteeringInput: 0.24f,
            MaximumRollDegrees: 24,
            MaximumYawRateRadiansPerSecond: 1.5f,
            MaximumSlipAngleDegrees: 18,
            MaximumLateralAccelerationMetersPerSecondSquared: 16,
            MaximumInclineUnsupportedSeconds: 0.60f),
        new(
            Id: "push",
            SpeedMetersPerSecond: 60,
            MaximumStraightSpeedLossMetersPerSecond: 9,
            MaximumStoppingDistanceMeters: 180,
            MaximumStoppingSeconds: 7,
            SteeringInput: 0.16f,
            MaximumRollDegrees: 30,
            MaximumYawRateRadiansPerSecond: 1.35f,
            MaximumSlipAngleDegrees: 16,
            MaximumLateralAccelerationMetersPerSecondSquared: 17,
            MaximumInclineUnsupportedSeconds: 0.75f),
        new(
            Id: "redline",
            SpeedMetersPerSecond: 89.408f,
            MaximumStraightSpeedLossMetersPerSecond: 13,
            MaximumStoppingDistanceMeters: 330,
            MaximumStoppingSeconds: 10,
            SteeringInput: 0.10f,
            MaximumRollDegrees: 35,
            MaximumYawRateRadiansPerSecond: 1.2f,
            MaximumSlipAngleDegrees: 14,
            MaximumLateralAccelerationMetersPerSecondSquared: 18,
            MaximumInclineUnsupportedSeconds: 0.90f),
    ];

    public static IReadOnlyList<VehicleDynamicsFixture> Fixtures { get; } =
    [
        VehicleDynamicsFixture.Straight,
        VehicleDynamicsFixture.Braking,
        VehicleDynamicsFixture.LaneChange,
        VehicleDynamicsFixture.Departure,
        VehicleDynamicsFixture.Barrier,
        VehicleDynamicsFixture.Incline,
        VehicleDynamicsFixture.Recovery,
        VehicleDynamicsFixture.Reset,
    ];

    public static VehicleDynamicsSpeedBand GetSpeedBand(string id) =>
        SpeedBands.FirstOrDefault(candidate =>
            string.Equals(candidate.Id, id, StringComparison.OrdinalIgnoreCase))
        ?? throw new ArgumentException($"Unknown vehicle dynamics speed band '{id}'.", nameof(id));

    public static VehicleDynamicsAssistTuning For(AssistProfile profile) => profile switch
    {
        AssistProfile.Accessible => new(
            UprightTorqueScale: 1.3f,
            AngularDampingScale: 1.35f,
            AirborneDownforceScale: 1.15f,
            ContactDriveResponseExponent: 1.3f),
        AssistProfile.Raw => new(
            UprightTorqueScale: 1,
            AngularDampingScale: 0.85f,
            AirborneDownforceScale: 0.9f,
            ContactDriveResponseExponent: 0.8f),
        _ => new(
            UprightTorqueScale: 1,
            AngularDampingScale: 1,
            AirborneDownforceScale: 1,
            ContactDriveResponseExponent: 1.1f),
    };
}

public readonly record struct VehicleDynamicsAssistTuning(
    float UprightTorqueScale,
    float AngularDampingScale,
    float AirborneDownforceScale,
    float ContactDriveResponseExponent);

public readonly record struct VehicleDynamicsAcceptanceBands(
    float EntrySpeedMetersPerSecond,
    float GradeRise,
    float MaximumUnsupportedSeconds,
    float MaximumChassisTiltDegrees,
    float MaximumAngularSpeedRadiansPerSecond,
    float MaximumLandingRecoverySeconds);

public sealed record VehicleDynamicsSpeedBand(
    string Id,
    float SpeedMetersPerSecond,
    float MaximumStraightSpeedLossMetersPerSecond,
    float MaximumStoppingDistanceMeters,
    float MaximumStoppingSeconds,
    float SteeringInput,
    float MaximumRollDegrees,
    float MaximumYawRateRadiansPerSecond,
    float MaximumSlipAngleDegrees,
    float MaximumLateralAccelerationMetersPerSecondSquared,
    float MaximumInclineUnsupportedSeconds);

public enum VehicleDynamicsFixture
{
    Straight,
    Braking,
    LaneChange,
    Departure,
    Barrier,
    Incline,
    Recovery,
    Reset,
}
