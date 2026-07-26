using Cannonball.Core.Runs;

namespace Cannonball.Game.Vehicle;

public static class VehicleDynamicsProfile
{
    public const float VehicleMassKilograms = 1_450;
    public const float GravityMetersPerSecondSquared = 9.80665f;
    public const float SpringRestLengthMeters = 0.54f;
    public const float MaximumSuspensionTravelMeters = SpringRestLengthMeters;
    public const float SuspensionBottomOutThresholdMeters = 0.52f;
    public const int MaximumSuspensionBottomOutFrames = 36;
    public const float WheelRadiusMeters = 0.34f;
    public const float CenterOfMassOffsetMeters = -0.40f;
    public const float SpringStrengthNewtonsPerMeter = 42_000;
    public const float SpringDampingNewtonsPerMeterPerSecond = 5_500;
    public const float MaximumSuspensionLoadG = 6.5f;
    public const float EngineForceNewtons = 25_000;
    public const float BrakeForceNewtons = 36_000;
    public const float TireCorneringStiffnessNewtonsPerRadian = 80_000;
    public const float TireFrictionCoefficient = 1.15f;
    public const float MaximumLateralAccelerationMetersPerSecondSquared = 14;
    public const float AerodynamicDragCoefficient = 0.42f;
    public const float RollingResistanceCoefficient = 0.012f;
    public const float EngineBrakingBaseNewtons = 450;
    public const float EngineBrakingNewtonsPerMeterPerSecond = 8;
    public const float GroundedDownforceCoefficient = 9;
    public const float MaximumGroundedDownforceG = 3;
    public const float AirborneDownforceCoefficient = 8;
    public const float MaximumAirborneDownforceG = 1.1f;
    public const float MaximumSteerAngleRadians = 0.38f;
    public const float UprightTorqueNewtonMeters = 24_000;
    public const float TiltDampingNewtonMeterSeconds = 12_000;
    public const float YawDampingNewtonMeterSeconds = 2_000;
    public const float SlipYawStabilityTorqueNewtonMetersPerRadian = 30_000;

    // P0-019 owner handling follow-up. These bounds were recorded before the
    // wheel-contact, lift-off, and keyboard-response corrections were run.
    public static VehicleFeelAcceptanceBands VehicleFeelBands { get; } = new(
        MaximumKeyboardThrottleReleaseFrames: 3,
        CoastDownDurationSeconds: 5,
        MinimumCruiseCoastSpeedLossMetersPerSecond: 2,
        MaximumCruiseCoastSpeedLossMetersPerSecond: 6,
        MaximumPostReleaseSpeedGainMetersPerSecond: 0.25f,
        MaximumSlowTurnRecoverySeconds: 1.5f,
        MaximumModerateTurnRecoverySeconds: 2,
        MaximumSwerveRecoverySeconds: 3,
        MaximumRecoveredYawRateRadiansPerSecond: 0.12f,
        MaximumRecoveredRollDegrees: 3,
        MaximumRecoveredSlipAngleDegrees: 3.5f,
        MaximumSwerveRollDegrees: 12,
        MaximumSwerveYawRateRadiansPerSecond: 1,
        MinimumSwerveFinalSpeedRatio: 0.70f,
        MaximumCorrectedHeadingErrorDegrees: 8);

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
        VehicleDynamicsFixture.SlowTurn,
        VehicleDynamicsFixture.ModerateTurn,
        VehicleDynamicsFixture.CoastDown,
        VehicleDynamicsFixture.AlternatingSwerve,
    ];

    public static VehicleDynamicsSpeedBand GetSpeedBand(string id) =>
        SpeedBands.FirstOrDefault(candidate =>
            string.Equals(candidate.Id, id, StringComparison.OrdinalIgnoreCase))
        ?? throw new ArgumentException($"Unknown vehicle dynamics speed band '{id}'.", nameof(id));

    public static VehicleDynamicsAssistTuning For(AssistProfile profile) => profile switch
    {
        AssistProfile.Accessible => new(
            UprightTorqueScale: 1.15f,
            TiltDampingScale: 1.2f,
            YawDampingScale: 1.25f,
            LateralResponseScale: 1.05f,
            SlipYawStabilityScale: 1.15f,
            AirborneDownforceScale: 1.15f,
            ContactDriveResponseExponent: 1.3f),
        AssistProfile.Raw => new(
            UprightTorqueScale: 0.8f,
            TiltDampingScale: 0.75f,
            YawDampingScale: 0.7f,
            LateralResponseScale: 0.92f,
            SlipYawStabilityScale: 0.65f,
            AirborneDownforceScale: 0.95f,
            ContactDriveResponseExponent: 0.8f),
        _ => new(
            UprightTorqueScale: 1,
            TiltDampingScale: 1,
            YawDampingScale: 1,
            LateralResponseScale: 1,
            SlipYawStabilityScale: 1,
            AirborneDownforceScale: 1,
            ContactDriveResponseExponent: 1.1f),
    };
}

public readonly record struct VehicleDynamicsAssistTuning(
    float UprightTorqueScale,
    float TiltDampingScale,
    float YawDampingScale,
    float LateralResponseScale,
    float SlipYawStabilityScale,
    float AirborneDownforceScale,
    float ContactDriveResponseExponent);

public readonly record struct VehicleFeelAcceptanceBands(
    int MaximumKeyboardThrottleReleaseFrames,
    float CoastDownDurationSeconds,
    float MinimumCruiseCoastSpeedLossMetersPerSecond,
    float MaximumCruiseCoastSpeedLossMetersPerSecond,
    float MaximumPostReleaseSpeedGainMetersPerSecond,
    float MaximumSlowTurnRecoverySeconds,
    float MaximumModerateTurnRecoverySeconds,
    float MaximumSwerveRecoverySeconds,
    float MaximumRecoveredYawRateRadiansPerSecond,
    float MaximumRecoveredRollDegrees,
    float MaximumRecoveredSlipAngleDegrees,
    float MaximumSwerveRollDegrees,
    float MaximumSwerveYawRateRadiansPerSecond,
    float MinimumSwerveFinalSpeedRatio,
    float MaximumCorrectedHeadingErrorDegrees);

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
    SlowTurn,
    ModerateTurn,
    CoastDown,
    AlternatingSwerve,
}
