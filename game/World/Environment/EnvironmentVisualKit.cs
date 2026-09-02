using System;
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

/// <summary>
/// Shared materials and meshes for the regional environment layers.
/// </summary>
/// <remarks>
/// Production materials bind the checksum-locked Poly Haven sets recorded in
/// <c>data/assets/environments/sourced-assets.lock.json</c> to the project
/// shaders under <c>assets/environments/shaders</c>. When any set is absent, or
/// the graybox profile is selected, every material falls back to a flat
/// colour with identical semantics so headless verification, release exports
/// awaiting the rights review, and the graybox contract keep working. The
/// <see cref="TextureSource"/> value reports which path was taken.
/// </remarks>
public sealed class EnvironmentVisualKit : IDisposable
{
    public const string Version = "colorado-proof-corridor-v3";
    public const string ConiferDirectory = "res://assets/environments/trees/conifer/";
    public const string ConiferScenePath = ConiferDirectory + "conifer.generated.tscn";
    public const string ConiferNeedleAlbedoPath = ConiferDirectory + "conifer-needles-albedo.png";
    public const string ConiferNeedleNormalPath = ConiferDirectory + "conifer-needles-normal.png";
    public const string ConiferImpostorPath = ConiferDirectory + "conifer-impostor.png";

    private EnvironmentVisualKit(EnvironmentQuality quality)
    {
        Quality = quality;
        var graybox = quality == EnvironmentQuality.Graybox;

        var grass = graybox ? Missing("rocky_terrain_02") : EnvironmentTextures.Load("rocky_terrain_02", "1k");
        var dryGrass = graybox ? Missing("aerial_grass_rock") : EnvironmentTextures.Load("aerial_grass_rock", "1k");
        var dirt = graybox ? Missing("dry_ground_rocks") : EnvironmentTextures.Load("dry_ground_rocks", "1k");
        var rock = graybox ? Missing("rock_face_03") : EnvironmentTextures.Load("rock_face_03", "1k");
        var bark = graybox ? Missing("pine_bark") : EnvironmentTextures.Load("pine_bark", "1k");
        var groundShader = graybox ? null : EnvironmentTextures.LoadShader("ground");
        var mountainShader = graybox ? null : EnvironmentTextures.LoadShader("mountain");
        var needleShader = graybox ? null : EnvironmentTextures.LoadShader("conifer_needles");
        var needleAlbedo = graybox ? null : EnvironmentTextures.LoadOptional(ConiferNeedleAlbedoPath);
        var needleNormal = graybox ? null : EnvironmentTextures.LoadOptional(ConiferNeedleNormalPath);
        var impostor = graybox ? null : EnvironmentTextures.LoadOptional(ConiferImpostorPath);
        var sourced = grass.Available && dryGrass.Available && dirt.Available && rock.Available &&
            bark.Available && groundShader is not null && mountainShader is not null;
        TextureSource = graybox ? "graybox" : sourced ? "sourced" : "fallback";

        Ground = sourced
            ? BuildGroundMaterial(groundShader!, grass, dryGrass, dirt, rock)
            : Flat(graybox ? "526052" : "5f6652", 1.0f, cullDisabled: true);
        Mountain = sourced
            ? BuildMountainMaterial(mountainShader!, rock, grass, forestWeight: 1.0f, snowLine: 3520, baseAltitude: 2500)
            : Flat(graybox ? "77818b" : "566372", 0.96f);
        Hill = sourced
            ? BuildMountainMaterial(mountainShader!, rock, grass, forestWeight: 1.0f, snowLine: 9000, baseAltitude: 1700)
            : Flat(graybox ? "68725e" : "586348", 1.0f);
        Rock = sourced
            ? BuildMountainMaterial(mountainShader!, rock, grass, forestWeight: 0.0f, snowLine: 9000, baseAltitude: 0)
            : Flat(graybox ? "777b80" : "69655d", 0.98f);
        Bark = sourced && bark.Available
            ? EnvironmentTextures.Standard(bark, new Vector3(2.0f, 3.5f, 1), roughness: 1.0f)
            : Flat(graybox ? "5a4a3a" : "4a3a2c", 0.95f);
        Needles = sourced && needleShader is not null && needleAlbedo is not null
            ? BuildNeedleMaterial(needleShader, needleAlbedo, needleNormal)
            : Flat(graybox ? "4b6854" : "214d32", 0.95f, cullDisabled: true);
        Impostor = sourced && impostor is not null
            ? new StandardMaterial3D
            {
                AlbedoTexture = impostor,
                AlbedoColor = new Color(0.50f, 0.58f, 0.44f),
                Transparency = BaseMaterial3D.TransparencyEnum.AlphaScissor,
                AlphaScissorThreshold = 0.45f,
                CullMode = BaseMaterial3D.CullModeEnum.Disabled,
                Roughness = 0.9f,
                TextureFilter = BaseMaterial3D.TextureFilterEnum.LinearWithMipmapsAnisotropic,
            }
            : Flat(graybox ? "4b6854" : "1f4630", 0.95f, cullDisabled: true);
        Building = new StandardMaterial3D
        {
            AlbedoColor = new Color(graybox ? "777d84" : "8c8f8a"),
            Roughness = 0.82f,
            VertexColorUseAsAlbedo = true,
        };
        Window = Flat(graybox ? "92a1aa" : "9dc4d4", 0.35f, emission: !graybox);

        var conifer = LoadConiferMeshes();
        ConiferLod0 = conifer.Lod0;
        ConiferLod1 = conifer.Lod1;
        ConiferLod2 = conifer.Lod2;
        ConiferSource = conifer.Source;
        RockMesh = ProceduralMeshes.BuildRock(20260901u, radialSegments: 14, rings: 9, Rock);
        Massif0 = WithMaterial(HeightfieldMeshes.BuildMassif(101), Mountain);
        Massif1 = WithMaterial(HeightfieldMeshes.BuildMassif(202), Mountain);
        Massif2 = WithMaterial(HeightfieldMeshes.BuildMassif(303), Mountain);
        Hill0 = WithMaterial(HeightfieldMeshes.BuildHill(404), Hill);
        Hill1 = WithMaterial(HeightfieldMeshes.BuildHill(505), Hill);
        BuildingMesh = new BoxMesh { Size = Vector3.One, Material = Building };
        WindowMesh = new BoxMesh { Size = Vector3.One, Material = Window };

        (NearTreesPerHundredMeters, NearRocksPerHundredMeters, MidInstanceBudget, DistantInstanceBudget, TerrainSampleStride) =
            quality switch
            {
                EnvironmentQuality.High => (14f, 1.6f, 18, 10, 1),
                EnvironmentQuality.Balanced => (9f, 1.1f, 12, 7, 2),
                EnvironmentQuality.Low => (5f, 0.7f, 7, 4, 4),
                EnvironmentQuality.Graybox => (2f, 0.4f, 4, 3, 8),
                _ => throw new ArgumentOutOfRangeException(nameof(quality)),
            };
        (NearLod0Meters, NearLod1Meters, NearLod2Meters) = quality switch
        {
            EnvironmentQuality.High => (170f, 520f, 1_500f),
            EnvironmentQuality.Balanced => (130f, 400f, 1_100f),
            EnvironmentQuality.Low => (90f, 260f, 800f),
            EnvironmentQuality.Graybox => (60f, 200f, 600f),
            _ => throw new ArgumentOutOfRangeException(nameof(quality)),
        };
    }

    public EnvironmentQuality Quality { get; }
    public string ProfileId => Quality.ToString().ToLowerInvariant();
    /// <summary>"sourced", "fallback", or "graybox".</summary>
    public string TextureSource { get; }
    /// <summary>"generated-scene" when the Blender conifer resolved, otherwise "procedural".</summary>
    public string ConiferSource { get; }
    public float NearTreesPerHundredMeters { get; }
    public float NearRocksPerHundredMeters { get; }
    public int MidInstanceBudget { get; }
    public int DistantInstanceBudget { get; }
    public int TerrainSampleStride { get; }
    public float NearLod0Meters { get; }
    public float NearLod1Meters { get; }
    public float NearLod2Meters { get; }

    public Material Ground { get; }
    public Material Mountain { get; }
    public Material Hill { get; }
    public Material Rock { get; }
    public Material Bark { get; }
    public Material Needles { get; }
    public Material Impostor { get; }
    public StandardMaterial3D Building { get; }
    public StandardMaterial3D Window { get; }
    public Mesh ConiferLod0 { get; }
    public Mesh ConiferLod1 { get; }
    public Mesh ConiferLod2 { get; }
    public Mesh RockMesh { get; }
    public Mesh Massif0 { get; }
    public Mesh Massif1 { get; }
    public Mesh Massif2 { get; }
    public Mesh Hill0 { get; }
    public Mesh Hill1 { get; }
    public Mesh BuildingMesh { get; }
    public Mesh WindowMesh { get; }
    public int SharedMaterialCount => 9;
    public int SharedMeshCount => 11;

    public Mesh MassifMesh(int index) => (index % 3) switch { 0 => Massif0, 1 => Massif1, _ => Massif2 };
    public Mesh HillMesh(int index) => index % 2 == 0 ? Hill0 : Hill1;

    public static EnvironmentVisualKit FromCommandLine()
    {
        var arguments = OS.GetCmdlineUserArgs();
        if (arguments.Contains(SkyLighting.GrayboxArgument, StringComparer.Ordinal))
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

    /// <summary>
    /// Builds a ground material for another kit that shares the same sourced
    /// sets, so the road terrain margin and the environment ribbon blend with
    /// one surface. Returns null when the sources are unavailable.
    /// </summary>
    public static ShaderMaterial? TryBuildSharedGroundMaterial()
    {
        var shader = EnvironmentTextures.LoadShader("ground");
        var grass = EnvironmentTextures.Load("rocky_terrain_02", "1k");
        var dryGrass = EnvironmentTextures.Load("aerial_grass_rock", "1k");
        var dirt = EnvironmentTextures.Load("dry_ground_rocks", "1k");
        var rock = EnvironmentTextures.Load("rock_face_03", "1k");
        if (shader is null || !grass.Available || !dryGrass.Available || !dirt.Available || !rock.Available)
        {
            return null;
        }
        return BuildGroundMaterial(shader, grass, dryGrass, dirt, rock);
    }

    private static ShaderMaterial BuildGroundMaterial(
        Shader shader,
        SourcedTextureSet grass,
        SourcedTextureSet dryGrass,
        SourcedTextureSet dirt,
        SourcedTextureSet rock)
    {
        var material = new ShaderMaterial { Shader = shader };
        EnvironmentTextures.Bind(material, "grass", grass);
        EnvironmentTextures.Bind(material, "dry", dryGrass);
        EnvironmentTextures.Bind(material, "dirt", dirt);
        EnvironmentTextures.Bind(material, "rock", rock);
<<<<<<< HEAD
        // Both divide the 4096 m UV wrap period, so the wrap never shows.
        material.SetShaderParameter("tile_meters", 8.0f);
        material.SetShaderParameter("macro_tile_meters", 51.2f);
=======
        material.SetShaderParameter("tile_meters", 7.0f);
        material.SetShaderParameter("macro_tile_meters", 53.0f);
>>>>>>> origin/main
        return material;
    }

    private static ShaderMaterial BuildMountainMaterial(
        Shader shader,
        SourcedTextureSet rock,
        SourcedTextureSet grass,
        float forestWeight,
        float snowLine,
        float baseAltitude)
    {
        var material = new ShaderMaterial { Shader = shader };
        EnvironmentTextures.Bind(material, "rock", rock);
        material.SetShaderParameter("grass_albedo", grass.Albedo!);
        material.SetShaderParameter("grass_normal", grass.Normal!);
        material.SetShaderParameter("forest_weight", forestWeight);
        material.SetShaderParameter("snow_line_meters", snowLine);
        material.SetShaderParameter("base_altitude_meters", baseAltitude);
        return material;
    }

    private static ShaderMaterial BuildNeedleMaterial(Shader shader, Texture2D albedo, Texture2D? normal)
    {
        var material = new ShaderMaterial { Shader = shader };
        material.SetShaderParameter("needle_albedo", albedo);
        material.SetShaderParameter("tint", new Vector3(0.62f, 0.72f, 0.55f));
        if (normal is not null)
        {
            material.SetShaderParameter("needle_normal", normal);
        }
        return material;
    }

    private static SourcedTextureSet Missing(string assetId) => new(assetId, null, null, null);

    private static StandardMaterial3D Flat(
        string color,
        float roughness,
        bool emission = false,
        bool cullDisabled = false)
    {
        var value = new Color(color);
        return new StandardMaterial3D
        {
            AlbedoColor = value,
            Roughness = roughness,
            EmissionEnabled = emission,
            Emission = value,
            EmissionEnergyMultiplier = emission ? 0.22f : 0,
            CullMode = cullDisabled ? BaseMaterial3D.CullModeEnum.Disabled : BaseMaterial3D.CullModeEnum.Back,
        };
    }

    private static ArrayMesh WithMaterial(ArrayMesh mesh, Material material)
    {
        for (var surface = 0; surface < mesh.GetSurfaceCount(); surface++)
        {
            mesh.SurfaceSetMaterial(surface, material);
        }
        return mesh;
    }

    /// <summary>
    /// Resolves the three conifer LOD meshes from the Blender-generated,
    /// importer-normalised scene, assigning the kit's bark, needle and impostor
    /// materials by surface name. Falls back to a procedural conifer that keeps
    /// the same LOD semantics when the scene is absent.
    /// </summary>
    private (Mesh Lod0, Mesh Lod1, Mesh Lod2, string Source) LoadConiferMeshes()
    {
        if (TextureSource == "sourced" && ResourceLoader.Exists(ConiferScenePath))
        {
            var packed = GD.Load<PackedScene>(ConiferScenePath);
            var instance = packed.Instantiate();
            try
            {
                var lod0 = ExtractMesh(instance, "Visual_LOD0");
                var lod1 = ExtractMesh(instance, "Visual_LOD1");
                var lod2 = ExtractMesh(instance, "Visual_LOD2");
                if (lod0 is not null && lod1 is not null && lod2 is not null)
                {
                    return (lod0, lod1, lod2, "generated-scene");
                }
            }
            finally
            {
                instance.Free();
            }
        }
        return (
            ProceduralMeshes.BuildConifer(Bark, Needles, tiers: 5, segments: 8),
            ProceduralMeshes.BuildConifer(Bark, Needles, tiers: 3, segments: 6),
            ProceduralMeshes.BuildConifer(Bark, Needles, tiers: 2, segments: 5),
            "procedural");
    }

    private ArrayMesh? ExtractMesh(Node root, string lodName)
    {
        var lod = root.FindChild(lodName, recursive: true, owned: false);
        if (lod is null)
        {
            return null;
        }
        var merged = new ArrayMesh();
        var parts = lod.FindChildren("*", "MeshInstance3D", recursive: true, owned: false)
            .OfType<MeshInstance3D>()
            .OrderBy(node => node.Name.ToString(), StringComparer.Ordinal);
        foreach (var meshInstance in parts)
        {
            if (meshInstance.Mesh is not ArrayMesh source)
            {
                continue;
            }
            var name = meshInstance.Name.ToString();
            var material = name.Contains("Needles", StringComparison.Ordinal)
                ? Needles
                : name.Contains("Impostor", StringComparison.Ordinal)
                    ? Impostor
                    : Bark;
            for (var surface = 0; surface < source.GetSurfaceCount(); surface++)
            {
                merged.AddSurfaceFromArrays(
                    source.SurfaceGetPrimitiveType(surface),
                    source.SurfaceGetArrays(surface));
                merged.SurfaceSetMaterial(merged.GetSurfaceCount() - 1, material);
            }
        }
        return merged.GetSurfaceCount() == 0 ? null : merged;
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
