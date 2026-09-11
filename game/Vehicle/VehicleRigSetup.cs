using Godot;

namespace Cannonball.Game.Vehicle;

/// <summary>Physical geometry and presentation contract, independent of the gameplay speed policy.</summary>
[GlobalClass]
public partial class VehicleRigSetup : Resource
{
    [Export] public string AssetId { get; set; } = "hero-gt";
    [Export] public string WrapperPath { get; set; } = "res://game/Vehicle/Visuals/HeroGt.tscn";
    [Export] public string TextureBindingsPath { get; set; } = VehicleVisualRig.SourcedTexturesPath;
    [Export] public string PaintShaderPath { get; set; } = VehicleVisualRig.CarPaintShaderPath;
    [Export] public string[] CockpitExcludedMeshes { get; set; } = VehicleVisualRig.CockpitExcludedMeshes;
    [Export] public float MassKilograms { get; set; } = VehicleDynamicsProfile.VehicleMassKilograms;
    [Export] public float WheelbaseMeters { get; set; } = 2.84f;
    [Export] public float FrontTrackMeters { get; set; } = 1.64f;
    [Export] public float RearTrackMeters { get; set; } = 1.64f;
    [Export] public float TireRadiusMeters { get; set; } = VehicleDynamicsProfile.WheelRadiusMeters;
    [Export] public float ChassisOriginHeightMeters { get; set; } = CannonballVehicle.VisualRigMountHeightMeters;
    [Export] public float SpawnHeightMeters { get; set; } = 0.78f;
    [Export] public Vector3 CenterOfMassOffset { get; set; } = new(0, VehicleDynamicsProfile.CenterOfMassOffsetMeters, 0);
    [Export] public float SpringFreeLengthMeters { get; set; } = VehicleDynamicsProfile.SpringRestLengthMeters;
    [Export] public float StaticCompressionMeters { get; set; } =
        VehicleDynamicsProfile.VehicleMassKilograms * VehicleDynamicsProfile.GravityMetersPerSecondSquared /
        (4 * VehicleDynamicsProfile.SpringStrengthNewtonsPerMeter);
    [Export] public float FrontSpringRate { get; set; } = VehicleDynamicsProfile.SpringStrengthNewtonsPerMeter;
    [Export] public float RearSpringRate { get; set; } = VehicleDynamicsProfile.SpringStrengthNewtonsPerMeter;
    [Export] public float FrontSpringDamping { get; set; } = VehicleDynamicsProfile.SpringDampingNewtonsPerMeterPerSecond;
    [Export] public float RearSpringDamping { get; set; } = VehicleDynamicsProfile.SpringDampingNewtonsPerMeterPerSecond;
    [Export] public float SuspensionBottomOutThresholdMeters { get; set; } = VehicleDynamicsProfile.SuspensionBottomOutThresholdMeters;
    [Export] public float MaximumSteerRadians { get; set; } = VehicleDynamicsProfile.MaximumSteerAngleRadians;
    [Export] public float MaximumVisualCompressionMeters { get; set; } = 0.62f;
    [Export] public bool AuthoredAtStaticRide { get; set; }
    [Export] public bool SteerSuspensionParent { get; set; }
    [Export] public bool DistributedLodGeometry { get; set; }
    [Export] public float WheelRollingSign { get; set; } = -1;
    [Export] public bool ContactShadingEnabled { get; set; }
    [Export] public Vector3 CollisionBoxSize { get; set; } = new(1.86f, 0.64f, 4.45f);
    [Export] public Vector3 CollisionBoxCenter { get; set; }
    [Export] public Vector3 CabinCollisionBoxSize { get; set; }
    [Export] public Vector3 CabinCollisionBoxCenter { get; set; }
    [Export] public float EngineForceNewtons { get; set; } = VehicleDynamicsProfile.EngineForceNewtons;
    [Export] public float BrakeForceNewtons { get; set; } = VehicleDynamicsProfile.BrakeForceNewtons;
    [Export] public float GroundedDownforceCoefficient { get; set; } = VehicleDynamicsProfile.GroundedDownforceCoefficient;
    [Export] public float MaximumGroundedDownforceG { get; set; } = VehicleDynamicsProfile.MaximumGroundedDownforceG;

    public Vector3 SpringAnchor(int index) => new(
        (index % 2 == 0 ? -0.5f : 0.5f) * (index < 2 ? FrontTrackMeters : RearTrackMeters),
        TireRadiusMeters + SpringFreeLengthMeters - StaticCompressionMeters - ChassisOriginHeightMeters,
        (index < 2 ? -0.5f : 0.5f) * WheelbaseMeters);

    public float SpringRate(int index) => index < 2 ? FrontSpringRate : RearSpringRate;
    public float SpringDamping(int index) => index < 2 ? FrontSpringDamping : RearSpringDamping;

    public void Validate()
    {
        var scalars = new[] { MassKilograms, TireRadiusMeters, WheelbaseMeters, FrontTrackMeters, RearTrackMeters,
            ChassisOriginHeightMeters, SpawnHeightMeters, SpringFreeLengthMeters, StaticCompressionMeters,
            FrontSpringRate, RearSpringRate, FrontSpringDamping, RearSpringDamping, SuspensionBottomOutThresholdMeters,
            MaximumSteerRadians, MaximumVisualCompressionMeters, WheelRollingSign, EngineForceNewtons, BrakeForceNewtons,
            GroundedDownforceCoefficient, MaximumGroundedDownforceG };
        if (scalars.Any(value => !float.IsFinite(value)) || !CenterOfMassOffset.IsFinite() ||
            !CollisionBoxSize.IsFinite() || !CollisionBoxCenter.IsFinite() ||
            !CabinCollisionBoxSize.IsFinite() || !CabinCollisionBoxCenter.IsFinite())
            throw new InvalidOperationException($"Vehicle setup '{AssetId}' contains a nonfinite parameter.");
        if (MassKilograms <= 0 || TireRadiusMeters <= 0 || WheelbaseMeters <= 0 ||
            FrontTrackMeters <= 0 || RearTrackMeters <= 0 ||
            StaticCompressionMeters <= 0 || StaticCompressionMeters >= SpringFreeLengthMeters ||
            FrontSpringRate <= 0 || RearSpringRate <= 0 || FrontSpringDamping <= 0 || RearSpringDamping <= 0 ||
            ChassisOriginHeightMeters <= 0 || SpawnHeightMeters <= 0 ||
            CollisionBoxSize.X <= 0 || CollisionBoxSize.Y <= 0 || CollisionBoxSize.Z <= 0 ||
            Math.Abs(WheelRollingSign) != 1 || MaximumSteerRadians <= 0 || MaximumSteerRadians >= Mathf.Pi / 2 ||
            MaximumVisualCompressionMeters < SpringFreeLengthMeters || EngineForceNewtons <= 0 || BrakeForceNewtons <= 0 ||
            GroundedDownforceCoefficient < 0 || MaximumGroundedDownforceG < 0 ||
            CabinCollisionBoxSize != Vector3.Zero && (CabinCollisionBoxSize.X <= 0 || CabinCollisionBoxSize.Y <= 0 || CabinCollisionBoxSize.Z <= 0))
        {
            throw new InvalidOperationException($"Vehicle setup '{AssetId}' has invalid dimensions or suspension constants.");
        }
        if (AuthoredAtStaticRide)
        {
            var frontFraction = 0.5f - CenterOfMassOffset.Z / WheelbaseMeters;
            var frontCompression = MassKilograms * VehicleDynamicsProfile.GravityMetersPerSecondSquared * frontFraction /
                (2 * FrontSpringRate);
            var rearCompression = MassKilograms * VehicleDynamicsProfile.GravityMetersPerSecondSquared * (1 - frontFraction) /
                (2 * RearSpringRate);
            if (Math.Abs(frontCompression - StaticCompressionMeters) > 0.0001f ||
                Math.Abs(rearCompression - StaticCompressionMeters) > 0.0001f)
            {
                throw new InvalidOperationException($"Vehicle setup '{AssetId}' does not support its declared static ride height/load distribution.");
            }
        }
    }

    public static VehicleRigSetup Load(string assetId)
    {
        var path = assetId switch
        {
            "hero-gt" or "graybox" => "res://game/Vehicle/Setups/HeroGt.tres",
            "endurance-sedan" => "res://game/Vehicle/Setups/EnduranceSedan.tres",
            _ => throw new ArgumentException($"Unknown vehicle '{assetId}'. Choose hero-gt, endurance-sedan or graybox."),
        };
        var setup = ResourceLoader.Load<VehicleRigSetup>(path, cacheMode: ResourceLoader.CacheMode.Ignore) ??
            throw new InvalidOperationException($"Vehicle setup resource is missing: {path}");
        setup.Validate();
        return setup;
    }
}
