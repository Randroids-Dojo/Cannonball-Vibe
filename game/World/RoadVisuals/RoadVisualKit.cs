using Godot;

namespace Cannonball.Game.World.RoadVisuals;

public enum RoadVisualProfile
{
    Production,
    Graybox,
}

public sealed class RoadVisualKit
{
    public const string Version = "colorado-freeway-v1";
    private readonly IReadOnlyList<Material> _sharedMaterials;
    private readonly IReadOnlyList<Mesh> _sharedMeshes;
    private readonly IReadOnlyList<Material> _retroreflectiveMaterials;

    private RoadVisualKit(RoadVisualProfile profile)
    {
        Profile = profile;
        var graybox = profile == RoadVisualProfile.Graybox;
        Terrain = Material(graybox ? "526052" : "344536", 1.0f);
        Shoulder = Material(graybox ? "55585c" : "34363b", 0.97f);
        Pavement = Material(graybox ? "33363b" : "171a20", 0.94f);
        MarkingWhite = Retroreflective(graybox ? "e8e8e8" : "f5f1d8", 0.32f);
        MarkingYellow = Retroreflective(graybox ? "d7bf58" : "f2c230", 0.35f);
        Gore = Retroreflective(graybox ? "d7bf58" : "f2c230", 0.4f);
        Concrete = Material(graybox ? "92969a" : "a7a9a3", 0.82f);
        GalvanizedSteel = Material(graybox ? "8b9099" : "aeb4b8", 0.42f, 0.72f);
        Delineator = Material(graybox ? "d6d0ad" : "e7e5dc", 0.78f);
        ReflectorWhite = Retroreflective("fff8db", 0.9f);
        ReflectorYellow = Retroreflective("ffc92f", 0.9f);
        GuideGreen = Retroreflective(graybox ? "2e6a4a" : "146b3a", 0.22f);
        ServiceBlue = Retroreflective(graybox ? "315d86" : "075a9c", 0.24f);
        ExitOnlyYellow = Retroreflective("f4c430", 0.3f);
        SignWhite = Retroreflective("f4f5ef", 0.5f);
        SignBlack = Material("111418", 0.9f);
        InterstateBlue = Retroreflective("174a91", 0.25f);
        InterstateRed = Retroreflective("b3262d", 0.25f);

        MedianBarrierMesh = new BoxMesh
        {
            Size = new Vector3(0.38f, 0.82f, 1),
            Material = Concrete,
        };
        GuardrailMesh = new BoxMesh
        {
            Size = new Vector3(0.18f, 0.34f, 1),
            Material = GalvanizedSteel,
        };
        GuardrailPostMesh = new BoxMesh
        {
            Size = new Vector3(0.14f, 0.8f, 0.14f),
            Material = GalvanizedSteel,
        };
        ReflectorMesh = new BoxMesh
        {
            Size = new Vector3(0.12f, 0.045f, 0.2f),
            Material = ReflectorWhite,
        };
        DelineatorMesh = new CylinderMesh
        {
            TopRadius = 0.07f,
            BottomRadius = 0.09f,
            Height = 1.1f,
            Material = Delineator,
        };
        _sharedMaterials =
        [
            Terrain, Shoulder, Pavement, MarkingWhite, MarkingYellow, Gore,
            Concrete, GalvanizedSteel, Delineator, ReflectorWhite, ReflectorYellow,
            GuideGreen, ServiceBlue, ExitOnlyYellow, SignWhite, SignBlack,
            InterstateBlue, InterstateRed,
        ];
        _sharedMeshes =
        [
            MedianBarrierMesh, GuardrailMesh, GuardrailPostMesh, ReflectorMesh,
            DelineatorMesh,
        ];
        _retroreflectiveMaterials =
        [
            MarkingWhite, MarkingYellow, Gore, ReflectorWhite, ReflectorYellow,
            GuideGreen, ServiceBlue, ExitOnlyYellow, SignWhite, InterstateBlue,
            InterstateRed,
        ];
    }

    public RoadVisualProfile Profile { get; }
    public string ProfileId => Profile == RoadVisualProfile.Production
        ? "production"
        : "graybox";
    public StandardMaterial3D Terrain { get; }
    public StandardMaterial3D Shoulder { get; }
    public StandardMaterial3D Pavement { get; }
    public StandardMaterial3D MarkingWhite { get; }
    public StandardMaterial3D MarkingYellow { get; }
    public StandardMaterial3D Gore { get; }
    public StandardMaterial3D Concrete { get; }
    public StandardMaterial3D GalvanizedSteel { get; }
    public StandardMaterial3D Delineator { get; }
    public StandardMaterial3D ReflectorWhite { get; }
    public StandardMaterial3D ReflectorYellow { get; }
    public StandardMaterial3D GuideGreen { get; }
    public StandardMaterial3D ServiceBlue { get; }
    public StandardMaterial3D ExitOnlyYellow { get; }
    public StandardMaterial3D SignWhite { get; }
    public StandardMaterial3D SignBlack { get; }
    public StandardMaterial3D InterstateBlue { get; }
    public StandardMaterial3D InterstateRed { get; }
    public Mesh MedianBarrierMesh { get; }
    public Mesh GuardrailMesh { get; }
    public Mesh GuardrailPostMesh { get; }
    public Mesh ReflectorMesh { get; }
    public Mesh DelineatorMesh { get; }
    public int SharedMaterialCount => _sharedMaterials.Count;
    public int SharedMeshCount => _sharedMeshes.Count;
    public int RetroreflectiveMaterialCount => _retroreflectiveMaterials.Count;

    public static RoadVisualKit FromCommandLine() => new(
        OS.GetCmdlineUserArgs().Contains("--graybox-road-assets", StringComparer.Ordinal)
            ? RoadVisualProfile.Graybox
            : RoadVisualProfile.Production);

    public static void MarkSemantic(Node node, string automationId)
    {
        node.SetMeta("automation_id", automationId);
        node.SetMeta("road_visual_kit", Version);
    }

    private static StandardMaterial3D Material(
        string color,
        float roughness,
        float metallic = 0) => new()
    {
        AlbedoColor = new Color(color),
        Roughness = roughness,
        Metallic = metallic,
        CullMode = BaseMaterial3D.CullModeEnum.Disabled,
    };

    private static StandardMaterial3D Retroreflective(string color, float energy)
    {
        var value = new Color(color);
        return new StandardMaterial3D
        {
            AlbedoColor = value,
            Roughness = 0.72f,
            EmissionEnabled = true,
            Emission = value,
            EmissionEnergyMultiplier = energy,
            CullMode = BaseMaterial3D.CullModeEnum.Disabled,
        };
    }
}
