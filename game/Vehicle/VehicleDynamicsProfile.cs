using Cannonball.Core.Runs;

namespace Cannonball.Game.Vehicle;

public static class VehicleDynamicsProfile
{
    public const float VehicleMassKilograms = 1_450;
    public const float GravityMetersPerSecondSquared = 9.80665f;
    public const float SpringRestLengthMeters = 0.62f;
    public const float WheelRadiusMeters = 0.34f;
    public const float SpringStrengthNewtonsPerMeter = 42_000;
    public const float SpringDampingNewtonsPerMeterPerSecond = 5_500;
    public const float MaximumSuspensionLoadG = 6.5f;
    public const float EngineForceNewtons = 25_000;
    public const float BrakeForceNewtons = 36_000;
    public const float LateralGripNewtonsPerMeterPerSecond = 7_800;
    public const float AerodynamicDragCoefficient = 0.42f;
    public const float GroundedDownforceCoefficient = 9;
    public const float MaximumGroundedDownforceG = 3;
    public const float AirborneDownforceCoefficient = 2.75f;
    public const float MaximumAirborneDownforceG = 1.1f;
    public const float MaximumSteerAngleRadians = 0.38f;

    // P0-019 owner-reported incline regression. These bands were fixed before force tuning.
    public static VehicleDynamicsAcceptanceBands HighSpeedInclineBands { get; } = new(
        EntrySpeedMetersPerSecond: 70,
        GradeRise: 0.08f,
        MaximumUnsupportedSeconds: 0.75f,
        MaximumChassisTiltDegrees: 55,
        MaximumAngularSpeedRadiansPerSecond: 4,
        MaximumLandingRecoverySeconds: 1.5f);

    public static VehicleDynamicsAssistTuning For(AssistProfile profile) => profile switch
    {
        AssistProfile.Accessible => new(
            UprightTorqueScale: 1.3f,
            AngularDampingScale: 1.35f,
            AirborneDownforceScale: 1.15f,
            ContactDriveResponseExponent: 1.3f),
        AssistProfile.Raw => new(
            UprightTorqueScale: 0.35f,
            AngularDampingScale: 0.45f,
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
