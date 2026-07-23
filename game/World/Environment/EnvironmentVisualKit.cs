using Godot;

namespace Cannonball.Game.World.Environments;

public enum EnvironmentQuality
{
    High,
    Balanced,
    Low,
    Graybox,
}

public enum EnvironmentRegion
{
    Mountain,
    Foothill,
    Plains,
    UrbanEdge,
}

public sealed class EnvironmentVisualKit
{
    public const string Version = "colorado-proof-corridor-v2";

    private EnvironmentVisualKit(EnvironmentQuality quality)
    {
        Quality = quality;
        var graybox = quality == EnvironmentQuality.Graybox;
        Pine = Material(graybox ? "4b6854" : "214d32", 0.95f);
        Rock = Material(graybox ? "777b80" : "69655d", 0.98f);
        Foothill = Material(graybox ? "68725e" : "586348", 1.0f);
        Mountain = Material(graybox ? "77818b" : "566372", 0.96f);
        Snow = Material(graybox ? "d2d5d8" : "d9e2e8", 0.9f);
        Building = Material(graybox ? "777d84" : "6a7581", 0.84f);
        Window = Material(graybox ? "92a1aa" : "9dc4d4", 0.35f, emission: !graybox);
        TerrainBlend = new StandardMaterial3D
        {
            AlbedoColor = new Color("b8bdb8"),
            Roughness = 1.0f,
            VertexColorUseAsAlbedo = true,
            CullMode = BaseMaterial3D.CullModeEnum.Disabled,
        };

        PineMesh = new CylinderMesh
        {
            TopRadius = 0,
            BottomRadius = 1,
            Height = 2,
            RadialSegments = 6,
            Rings = 1,
            Material = Pine,
        };
        RockMesh = new SphereMesh
        {
            Radius = 1,
            Height = 1.45f,
            RadialSegments = 8,
            Rings = 4,
            Material = Rock,
        };
        FoothillMesh = new SphereMesh
        {
            Radius = 1,
            Height = 1.15f,
            RadialSegments = 12,
            Rings = 6,
            Material = Foothill,
        };
        MountainMesh = new CylinderMesh
        {
            TopRadius = 0,
            BottomRadius = 1,
            Height = 2,
            RadialSegments = 8,
            Rings = 1,
            Material = Mountain,
        };
        BuildingMesh = new BoxMesh
        {
            Size = Vector3.One,
            Material = Building,
        };
        WindowMesh = new BoxMesh
        {
            Size = Vector3.One,
            Material = Window,
        };

        (NearInstanceBudget, MidInstanceBudget, DistantInstanceBudget, TerrainSampleStride) =
            quality switch
        {
            EnvironmentQuality.High => (48, 18, 10, 1),
            EnvironmentQuality.Balanced => (30, 12, 7, 2),
            EnvironmentQuality.Low => (16, 7, 4, 4),
            EnvironmentQuality.Graybox => (6, 4, 3, 8),
            _ => throw new ArgumentOutOfRangeException(nameof(quality)),
        };
    }

    public EnvironmentQuality Quality { get; }
    public string ProfileId => Quality.ToString().ToLowerInvariant();
    public int NearInstanceBudget { get; }
    public int MidInstanceBudget { get; }
    public int DistantInstanceBudget { get; }
    public int TerrainSampleStride { get; }
    public StandardMaterial3D Pine { get; }
    public StandardMaterial3D Rock { get; }
    public StandardMaterial3D Foothill { get; }
    public StandardMaterial3D Mountain { get; }
    public StandardMaterial3D Snow { get; }
    public StandardMaterial3D Building { get; }
    public StandardMaterial3D Window { get; }
    public StandardMaterial3D TerrainBlend { get; }
    public Mesh PineMesh { get; }
    public Mesh RockMesh { get; }
    public Mesh FoothillMesh { get; }
    public Mesh MountainMesh { get; }
    public Mesh BuildingMesh { get; }
    public Mesh WindowMesh { get; }
    public int SharedMaterialCount => 8;
    public int SharedMeshCount => 6;

    public static EnvironmentVisualKit FromCommandLine()
    {
        var arguments = OS.GetCmdlineUserArgs();
        if (arguments.Contains("--graybox-environment-assets", StringComparer.Ordinal))
        {
            return new EnvironmentVisualKit(EnvironmentQuality.Graybox);
        }
        var qualityArgument = arguments.FirstOrDefault(value =>
            value.StartsWith("--environment-quality=", StringComparison.Ordinal));
        var value = qualityArgument?["--environment-quality=".Length..] ?? "balanced";
        if (!Enum.TryParse<EnvironmentQuality>(value, ignoreCase: true, out var quality))
        {
            throw new InvalidDataException(
                $"Unknown environment quality '{value}'. Use high, balanced, low, or graybox.");
        }
        return new EnvironmentVisualKit(quality);
    }

    public static void MarkSemantic(Node node, string automationId, string layer)
    {
        node.SetMeta("automation_id", automationId);
        node.SetMeta("environment_visual_kit", Version);
        node.SetMeta("environment_layer", layer);
        node.SetMeta("collision_free", true);
    }

    private static StandardMaterial3D Material(
        string color,
        float roughness,
        bool emission = false)
    {
        var value = new Color(color);
        return new StandardMaterial3D
        {
            AlbedoColor = value,
            Roughness = roughness,
            EmissionEnabled = emission,
            Emission = value,
            EmissionEnergyMultiplier = emission ? 0.22f : 0,
        };
    }
}
