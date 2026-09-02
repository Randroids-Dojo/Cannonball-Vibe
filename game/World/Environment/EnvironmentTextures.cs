using Godot;

namespace Cannonball.Game.World.Environments;

/// <summary>
/// One sourced PBR set: albedo, OpenGL-convention normal, and the packed
/// ambient-occlusion / roughness / metallic map Poly Haven publishes as "arm".
/// </summary>
public sealed record SourcedTextureSet(
    string AssetId,
    Texture2D? Albedo,
    Texture2D? Normal,
    Texture2D? Arm)
{
    public bool Available => Albedo is not null && Normal is not null && Arm is not null;
}

/// <summary>
/// Resolves the checksum-locked Poly Haven sources recorded in
/// <c>data/assets/environments/sourced-assets.lock.json</c>. Every loader
/// returns null members rather than throwing when a file is absent, because the
/// sourced directory is excluded from release presets until the Q-023 rights
/// review approves it and the graybox contract requires the runtime to keep
/// working without it.
/// </summary>
public static class EnvironmentTextures
{
    public const string SourcedRoot = "res://assets/environments/sourced/polyhaven/";
    public const string ShaderRoot = "res://assets/environments/shaders/";

    public static SourcedTextureSet Load(string assetId, string resolution) => new(
        assetId,
        LoadOptional($"{SourcedRoot}{assetId}/{assetId}_diff_{resolution}.jpg"),
        LoadOptional($"{SourcedRoot}{assetId}/{assetId}_nor_gl_{resolution}.jpg"),
        LoadOptional($"{SourcedRoot}{assetId}/{assetId}_arm_{resolution}.jpg"));

    public static Texture2D? LoadOptional(string path) =>
        ResourceLoader.Exists(path) ? GD.Load<Texture2D>(path) : null;

    public static Shader? LoadShader(string name)
    {
        var path = $"{ShaderRoot}{name}.gdshader";
        return ResourceLoader.Exists(path) ? GD.Load<Shader>(path) : null;
    }

    /// <summary>Binds a set to the three uniforms named <c>{prefix}_albedo</c>, <c>{prefix}_normal</c>, <c>{prefix}_arm</c>.</summary>
    public static void Bind(ShaderMaterial material, string prefix, SourcedTextureSet set)
    {
        if (!set.Available)
        {
            throw new InvalidOperationException($"Sourced texture set '{set.AssetId}' is incomplete.");
        }
        material.SetShaderParameter($"{prefix}_albedo", set.Albedo!);
        material.SetShaderParameter($"{prefix}_normal", set.Normal!);
        material.SetShaderParameter($"{prefix}_arm", set.Arm!);
    }

    /// <summary>
    /// A physically based material from one sourced set for meshes that need no
    /// custom shader, such as bark, rock and concrete.
    /// </summary>
    public static StandardMaterial3D Standard(
        SourcedTextureSet set,
        Vector3 uvScale,
        float roughness = 1.0f,
        bool cullDisabled = false) => new()
    {
        AlbedoTexture = set.Albedo,
        NormalEnabled = true,
        NormalTexture = set.Normal,
        NormalScale = 1.0f,
        AOEnabled = true,
        AOTexture = set.Arm,
        AOTextureChannel = BaseMaterial3D.TextureChannel.Red,
        AOLightAffect = 0.3f,
        RoughnessTexture = set.Arm,
        RoughnessTextureChannel = BaseMaterial3D.TextureChannel.Green,
        Roughness = roughness,
        MetallicTexture = set.Arm,
        MetallicTextureChannel = BaseMaterial3D.TextureChannel.Blue,
        Metallic = 1.0f,
        Uv1Scale = uvScale,
        TextureFilter = BaseMaterial3D.TextureFilterEnum.LinearWithMipmapsAnisotropic,
        CullMode = cullDisabled ? BaseMaterial3D.CullModeEnum.Disabled : BaseMaterial3D.CullModeEnum.Back,
    };
}
