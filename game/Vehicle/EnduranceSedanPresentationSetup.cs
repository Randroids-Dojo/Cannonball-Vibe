using Godot;

namespace Cannonball.Game.Vehicle;

/// <summary>Portable authored mechanism and display data; not a powertrain simulator.</summary>
[GlobalClass]
public partial class EnduranceSedanPresentationSetup : Resource
{
    [Export] public float[] OpeningAnglesDegrees { get; set; } = [-62, 62, -58, 58, 68, -72];
    [Export] public float OpeningDurationSeconds { get; set; } = 0.85f;
    [Export] public float SteeringRatio { get; set; } = 14.5f;
    [Export] public float AcceleratorAngleDegrees { get; set; } = -18;
    [Export] public float BrakeAngleDegrees { get; set; } = -12;
    [Export] public Vector3 WiperParentAxis { get; set; } = new(0, 0.816f, -0.578f);
    [Export] public float[] WiperSweepDegrees { get; set; } = [-78, -74];
    [Export] public float WiperPeriodSeconds { get; set; } = 1.35f;
    [Export] public float FuelCapacityLiters { get; set; } = 175;
    [Export] public float[] ForwardGearRatios { get; set; } = [3.60f, 2.19f, 1.52f, 1.15f, 0.90f, 0.72f, 0.59f];
    [Export] public float ReverseGearRatio { get; set; } = 3.40f;
    [Export] public float FinalDriveRatio { get; set; } = 3.76f;
    [Export] public float IdleRpm { get; set; } = 750;
    [Export] public float RedlineRpm { get; set; } = 6500;
    [Export] public Vector2I SideMirrorResolution { get; set; } = new(256, 128);
    [Export] public Vector2I RearMirrorResolution { get; set; } = new(384, 128);
    [Export] public float MirrorRefreshHz { get; set; } = 15;
    [Export] public float Lod1DistanceMeters { get; set; } = 28;
    [Export] public float Lod2DistanceMeters { get; set; } = 65;

    public void Validate()
    {
        if (OpeningAnglesDegrees.Length != 6 || WiperSweepDegrees.Length != 2 || ForwardGearRatios.Length != 7 ||
            OpeningAnglesDegrees.Concat(WiperSweepDegrees).Concat(ForwardGearRatios).Any(value => !float.IsFinite(value)) ||
            ForwardGearRatios.Any(value => value <= 0) || !WiperParentAxis.IsFinite() || WiperParentAxis.IsZeroApprox() ||
            new[] { OpeningDurationSeconds, SteeringRatio, WiperPeriodSeconds, FuelCapacityLiters, ReverseGearRatio,
                FinalDriveRatio, IdleRpm, RedlineRpm, MirrorRefreshHz, Lod1DistanceMeters, Lod2DistanceMeters }
                .Any(value => !float.IsFinite(value) || value <= 0) || RedlineRpm <= IdleRpm || Lod2DistanceMeters <= Lod1DistanceMeters ||
            SideMirrorResolution.X <= 0 || SideMirrorResolution.Y <= 0 || RearMirrorResolution.X <= 0 || RearMirrorResolution.Y <= 0)
            throw new InvalidOperationException("Sedan presentation setup has invalid mechanism, display or mirror parameters.");
    }
}
