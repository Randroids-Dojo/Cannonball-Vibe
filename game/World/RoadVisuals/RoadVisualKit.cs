using System;
using Cannonball.Game.World.Environments;
using Godot;

namespace Cannonball.Game.World.RoadVisuals;

public enum RoadVisualProfile
{
    Production,
    Graybox,
}

public sealed class RoadVisualKit : IDisposable
{
    public const string Version = "colorado-freeway-v5";
    public const double TerrainMarginMeters = 120;
    private readonly IReadOnlyList<Material> _sharedMaterials;
    private readonly IReadOnlyList<Mesh> _sharedMeshes;
    private readonly IReadOnlyList<Material> _retroreflectiveMaterials;

    private RoadVisualKit(RoadVisualProfile profile)
    {
        Profile = profile;
        var graybox = profile == RoadVisualProfile.Graybox;
        // The road terrain margin shares the environment ground surface so the
        // two ribbons meet without a material seam; the flat colour remains the
        // graybox and rights-pending export fallback.
        var sharedGround = graybox ? null : EnvironmentVisualKit.TryBuildSharedGroundMaterial();
        Terrain = (Material?)sharedGround ?? Material(graybox ? "526052" : "344536", 1.0f);
        TerrainSource = sharedGround is null ? (graybox ? "graybox" : "fallback") : "sourced";
        Scenery = Material(graybox ? "777b80" : "6b665e", 0.98f);
        // Sourced pavement, shoulder and precast concrete; the flat colours stay
        // as the graybox and rights-pending export fallback.
        var pavementShader = graybox ? null : EnvironmentTextures.LoadShader("pavement");
        var furnitureShader = graybox ? null : EnvironmentTextures.LoadShader("furniture");
        var asphalt = graybox ? null : EnvironmentTextures.Load("clean_asphalt", "2k");
        var shoulderAsphalt = graybox ? null : EnvironmentTextures.Load("asphalt_04", "1k");
        var precast = graybox ? null : EnvironmentTextures.Load("concrete_wall_008", "1k");
        var surfacesSourced = pavementShader is not null && furnitureShader is not null &&
            asphalt is { Available: true } && shoulderAsphalt is { Available: true } && precast is { Available: true };
        SurfaceSource = graybox ? "graybox" : surfacesSourced ? "sourced" : "fallback";
        Pavement = surfacesSourced
            ? PavementMaterial(pavementShader!, asphalt!, tileMeters: 3.2f, macroMeters: 25.6f, tint: new Vector3(0.78f, 0.78f, 0.80f), roughnessBias: 0.02f, patch: 0.18f)
            : Material(graybox ? "33363b" : "171a20", 0.94f);
        Shoulder = surfacesSourced
            ? PavementMaterial(pavementShader!, shoulderAsphalt!, tileMeters: 2.56f, macroMeters: 20.48f, tint: new Vector3(0.86f, 0.85f, 0.83f), roughnessBias: 0.08f, patch: 0.05f)
            : Material(graybox ? "55585c" : "34363b", 0.97f);
        MarkingWhite = Retroreflective(graybox ? "e8e8e8" : "f5f1d8", 0.32f);
        MarkingYellow = Retroreflective(graybox ? "d7bf58" : "f2c230", 0.35f);
        Gore = Retroreflective(graybox ? "e8e8e8" : "f5f1d8", 0.4f);
        Concrete = surfacesSourced
            ? FurnitureMaterial(furnitureShader!, precast!, tileMeters: 4.096f, tint: new Vector3(0.96f, 0.95f, 0.93f))
            : Material(graybox ? "92969a" : "a7a9a3", 0.82f);
        GalvanizedSteel = new StandardMaterial3D
        {
            AlbedoColor = new Color(graybox ? "8b9099" : "b9bec2"),
            Roughness = graybox ? 0.42f : 0.46f,
            Metallic = graybox ? 0.72f : 0.88f,
            MetallicSpecular = 0.6f,
            CullMode = BaseMaterial3D.CullModeEnum.Disabled,
        };
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

        MedianBarrierMesh = graybox
            ? new BoxMesh { Size = new Vector3(0.38f, 0.82f, 1), Material = Concrete }
            : RoadFurnitureMeshes.BuildJerseyBarrier(Concrete);
        GuardrailMesh = graybox
            ? new BoxMesh { Size = new Vector3(0.18f, 0.34f, 1), Material = GalvanizedSteel }
            : RoadFurnitureMeshes.BuildWBeam(GalvanizedSteel);
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
        BridgeDeckMesh = new BoxMesh
        {
            Size = new Vector3(1, 0.32f, 1),
            Material = Concrete,
        };
        BridgeGirderMesh = new BoxMesh
        {
            Size = new Vector3(0.34f, 0.62f, 1),
            Material = GalvanizedSteel,
        };
        BridgePierMesh = new BoxMesh
        {
            Size = new Vector3(0.8f, 1, 0.8f),
            Material = Concrete,
        };
        BridgeAbutmentMesh = new BoxMesh
        {
            Size = new Vector3(1, 1, 0.8f),
            Material = Concrete,
        };
        SceneryMesh = ProceduralMeshes.BuildRock(20260902u, radialSegments: 12, rings: 7, Scenery);
        _sharedMaterials =
        [
            Terrain, Shoulder, Pavement, MarkingWhite, MarkingYellow, Gore,
            Concrete, GalvanizedSteel, Delineator, ReflectorWhite, ReflectorYellow,
            GuideGreen, ServiceBlue, ExitOnlyYellow, SignWhite, SignBlack,
            InterstateBlue, InterstateRed, Scenery,
        ];
        _sharedMeshes =
        [
            MedianBarrierMesh, GuardrailMesh, GuardrailPostMesh, ReflectorMesh,
            DelineatorMesh, BridgeDeckMesh, BridgeGirderMesh, BridgePierMesh,
            BridgeAbutmentMesh, SceneryMesh,
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
    /// <summary>"sourced" when the environment ground surface resolved, else "fallback" or "graybox".</summary>
    public string TerrainSource { get; }
    /// <summary>"sourced" when the pavement, shoulder and concrete sets resolved, else "fallback" or "graybox".</summary>
    public string SurfaceSource { get; }
    public Material Terrain { get; }
    public StandardMaterial3D Scenery { get; }
    public Material Shoulder { get; }
    public Material Pavement { get; }
    public StandardMaterial3D MarkingWhite { get; }
    public StandardMaterial3D MarkingYellow { get; }
    public StandardMaterial3D Gore { get; }
    public Material Concrete { get; }
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
    public Mesh BridgeDeckMesh { get; }
    public Mesh BridgeGirderMesh { get; }
    public Mesh BridgePierMesh { get; }
    public Mesh BridgeAbutmentMesh { get; }
    public Mesh SceneryMesh { get; }
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

    private static ShaderMaterial PavementMaterial(
        Shader shader,
        SourcedTextureSet set,
        float tileMeters,
        float macroMeters,
        Vector3 tint,
        float roughnessBias,
        float patch)
    {
        var material = new ShaderMaterial { Shader = shader };
        material.SetShaderParameter("albedo_map", set.Albedo!);
        material.SetShaderParameter("normal_map", set.Normal!);
        material.SetShaderParameter("arm_map", set.Arm!);
        material.SetShaderParameter("tile_meters", tileMeters);
        material.SetShaderParameter("macro_tile_meters", macroMeters);
        material.SetShaderParameter("tint", tint);
        material.SetShaderParameter("roughness_bias", roughnessBias);
        material.SetShaderParameter("patch_strength", patch);
        return material;
    }

    private static ShaderMaterial FurnitureMaterial(
        Shader shader,
        SourcedTextureSet set,
        float tileMeters,
        Vector3 tint)
    {
        var material = new ShaderMaterial { Shader = shader };
        material.SetShaderParameter("albedo_map", set.Albedo!);
        material.SetShaderParameter("normal_map", set.Normal!);
        material.SetShaderParameter("arm_map", set.Arm!);
        material.SetShaderParameter("tile_meters", tileMeters);
        material.SetShaderParameter("tint", tint);
        return material;
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

    /// <summary>Releases every Godot resource this kit holds.</summary>
    /// <remarks>
    /// A Godot resource is RefCounted, and its C# wrapper holds one of those
    /// references until it is disposed or finalised. These kits are plain C#
    /// objects rather than nodes, so nothing frees them when the tree tears down:
    /// their wrappers survive to finalisation, which can run after the engine has
    /// gone. That produces "Leaked unsafe reference to object" at shutdown and,
    /// intermittently, a segmentation fault in the Linux smoke.
    ///
    /// Discovering the properties by reflection rather than listing them keeps
    /// this correct when a resource is added to the kit. It runs once, at
    /// shutdown, so the cost does not matter.
    ///
    /// Disposing only releases this wrapper's reference. A node still using one of
    /// these materials holds its own, so the underlying resource outlives the call
    /// and nothing rendering is affected.
    /// </remarks>
    public void Dispose()
    {
        foreach (var property in GetType().GetProperties(
                     System.Reflection.BindingFlags.Public |
                     System.Reflection.BindingFlags.Instance))
        {
            if (!typeof(Resource).IsAssignableFrom(property.PropertyType))
            {
                continue;
            }
            (property.GetValue(this) as Resource)?.Dispose();
        }
    }
}
