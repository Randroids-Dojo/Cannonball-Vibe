using System.Text.Json;
using Godot;

namespace Cannonball.Game.World.Environments;

public enum LightingPreset
{
    Dawn,
    Day,
    Overcast,
    Night,
}

/// <summary>
/// One complete lighting state: the sun or moon, the sky, the ambient and
/// reflection source, fog, and the tonemap exposure.
/// </summary>
/// <remarks>
/// <see cref="Background"/> and <see cref="Energy"/> are the two values every
/// visual scenario asserts after applying a preset, so they stay stable
/// contract fields even though the background is now a sky rather than a flat
/// colour. <see cref="PanoramaPath"/> is null when the sourced HDRI is absent
/// or the graybox profile is selected; the procedural sky then carries the same
/// colours so headless and export builds keep the same lighting semantics.
/// </remarks>
public sealed record LightingState(
    LightingPreset Preset,
    Color Light,
    float Energy,
    float PitchDegrees,
    float YawDegrees,
    Color Background,
    Color Ambient,
    float AmbientEnergy,
    string? PanoramaPath,
    float SkyEnergy,
    Color FogColor,
    float FogDensity,
    float FogAerialPerspective,
    Color SkyTop,
    Color SkyHorizon,
    Color GroundHorizon,
    float Exposure);

/// <summary>
/// Owns the single directional light and world environment for the runtime and
/// applies the four lighting presets the environment, road, vehicle and
/// reference-performance scenarios switch between.
/// </summary>
public static class SkyLighting
{
    /// <summary>Node names are unchanged from the original night-only rig so every scenario lookup still resolves.</summary>
    public const string LightNodeName = "MoonLight";
    public const string EnvironmentNodeName = "NightEnvironment";
    public const string PresetsPath = "res://assets/environments/sky-presets.json";
    public const string GrayboxArgument = "--graybox-environment-assets";
    private const float DefaultYawDegrees = -28;

    private static IReadOnlyDictionary<LightingPreset, LightingState>? _states;

    public static LightingState State(LightingPreset preset) => States()[preset];

    public static bool GrayboxRequested() =>
        OS.GetCmdlineUserArgs().Contains(GrayboxArgument, StringComparer.Ordinal);

    /// <summary>
    /// Creates the light and environment nodes under <paramref name="parent"/>
    /// and applies <paramref name="initial"/>.
    /// </summary>
    public static (DirectionalLight3D Light, WorldEnvironment Environment) Build(
        Node parent,
        LightingPreset initial)
    {
        ArgumentNullException.ThrowIfNull(parent);
        var light = new DirectionalLight3D
        {
            Name = LightNodeName,
            ShadowEnabled = true,
            DirectionalShadowMode = DirectionalLight3D.ShadowMode.Parallel4Splits,
            DirectionalShadowSplit1 = 0.04f,
            DirectionalShadowSplit2 = 0.12f,
            DirectionalShadowSplit3 = 0.35f,
            DirectionalShadowBlendSplits = true,
            DirectionalShadowMaxDistance = 420,
            DirectionalShadowFadeStart = 0.85f,
            ShadowBias = 0.04f,
            ShadowNormalBias = 1.8f,
            ShadowBlur = 1.2f,
            LightAngularDistance = 0.53f,
            LightIndirectEnergy = 1.0f,
        };
        parent.AddChild(light);

        // The environment and sky are handed to nodes that take their own
        // references; releasing these wrappers immediately avoids the shutdown
        // "Leaked unsafe reference" errors documented in the mono-resource audit.
        using var sky = new Sky
        {
            RadianceSize = Sky.RadianceSizeEnum.Size256,
            ProcessMode = Sky.ProcessModeEnum.Quality,
        };
        using var environment = new Godot.Environment
        {
            BackgroundMode = Godot.Environment.BGMode.Sky,
            Sky = sky,
            AmbientLightSource = Godot.Environment.AmbientSource.Sky,
            AmbientLightSkyContribution = 1.0f,
            ReflectedLightSource = Godot.Environment.ReflectionSource.Sky,
            TonemapMode = Godot.Environment.ToneMapper.Agx,
            TonemapExposure = 1.0f,
            SsaoEnabled = true,
            SsaoRadius = 1.6f,
            SsaoIntensity = 1.6f,
            SsaoPower = 1.6f,
            SsaoDetail = 0.4f,
            SsaoLightAffect = 0.1f,
            GlowEnabled = true,
            GlowIntensity = 0.32f,
            GlowBloom = 0.02f,
            GlowHdrThreshold = 1.15f,
            GlowBlendMode = Godot.Environment.GlowBlendModeEnum.Softlight,
            FogEnabled = true,
            FogMode = Godot.Environment.FogModeEnum.Exponential,
            FogSkyAffect = 0.12f,
            FogSunScatter = 0.08f,
            AdjustmentEnabled = true,
            AdjustmentContrast = 1.04f,
            AdjustmentSaturation = 1.06f,
        };
        var world = new WorldEnvironment
        {
            Name = EnvironmentNodeName,
            Environment = environment,
        };
        parent.AddChild(world);
        Apply(light, environment, initial);
        return (light, world);
    }

    /// <summary>Applies a preset to the light and environment in place.</summary>
    public static void Apply(
        DirectionalLight3D light,
        Godot.Environment environment,
        LightingPreset preset)
    {
        ArgumentNullException.ThrowIfNull(light);
        ArgumentNullException.ThrowIfNull(environment);
        var values = State(preset);
        var name = preset.ToString().ToLowerInvariant();
        // Scenarios re-apply their preset every frame; swapping the panorama
        // rebuilds the radiance map, so an unchanged preset is a no-op.
        if (environment.GetMeta("lighting_preset", "").AsString() == name &&
            light.GetMeta("lighting_preset", "").AsString() == name &&
            environment.BackgroundColor.IsEqualApprox(values.Background) &&
            Mathf.IsEqualApprox(light.LightEnergy, values.Energy))
        {
            return;
        }
        light.LightColor = values.Light;
        light.LightEnergy = values.Energy;
        light.RotationDegrees = new Vector3(values.PitchDegrees, values.YawDegrees, 0);
        light.SetMeta("lighting_preset", name);
        environment.BackgroundColor = values.Background;
        environment.AmbientLightColor = values.Ambient;
        environment.AmbientLightEnergy = values.AmbientEnergy;
        environment.FogLightColor = values.FogColor;
        environment.FogDensity = values.FogDensity;
        environment.FogAerialPerspective = values.FogAerialPerspective;
        environment.TonemapExposure = values.Exposure;
        environment.SetMeta("lighting_preset", name);
        ApplySky(environment, values);
    }

    /// <summary>The two fields every visual scenario asserts after applying a preset.</summary>
    public static bool Matches(
        DirectionalLight3D light,
        Godot.Environment environment,
        LightingPreset preset)
    {
        var expected = State(preset);
        return environment.BackgroundColor.IsEqualApprox(expected.Background) &&
            Mathf.IsEqualApprox(light.LightEnergy, expected.Energy);
    }

    private static void ApplySky(Godot.Environment environment, LightingState values)
    {
        var sky = environment.Sky;
        if (sky is null)
        {
            return;
        }
        var panoramaPath = values.PanoramaPath;
        // Assigning a material transfers ownership to the sky, so the creating
        // wrapper is released inside its own scope; the sky is then asked for a
        // fresh wrapper before any property is set, because the disposed one
        // cannot be touched again.
        if (panoramaPath is not null && !GrayboxRequested() && ResourceLoader.Exists(panoramaPath))
        {
            if (sky.SkyMaterial is not PanoramaSkyMaterial)
            {
                using var created = new PanoramaSkyMaterial { Filter = true };
                sky.SkyMaterial = created;
            }
            var panorama = (PanoramaSkyMaterial)sky.SkyMaterial;
            panorama.Panorama = GD.Load<Texture2D>(panoramaPath);
            panorama.EnergyMultiplier = values.SkyEnergy;
            environment.SetMeta("sky_source", "sourced-hdri");
            return;
        }
        if (sky.SkyMaterial is not ProceduralSkyMaterial)
        {
            using var created = new ProceduralSkyMaterial
            {
                SunAngleMax = 22,
                SunCurve = 0.18f,
                UseDebanding = true,
            };
            sky.SkyMaterial = created;
        }
        var procedural = (ProceduralSkyMaterial)sky.SkyMaterial;
        procedural.SkyTopColor = values.SkyTop;
        procedural.SkyHorizonColor = values.SkyHorizon;
        procedural.GroundHorizonColor = values.GroundHorizon;
        procedural.GroundBottomColor = values.GroundHorizon.Darkened(0.35f);
        procedural.SkyEnergyMultiplier = values.SkyEnergy;
        procedural.GroundEnergyMultiplier = values.SkyEnergy * 0.6f;
        environment.SetMeta("sky_source", "procedural");
    }

    private static IReadOnlyDictionary<LightingPreset, LightingState> States()
    {
        if (_states is not null)
        {
            return _states;
        }
        var defaults = new Dictionary<LightingPreset, LightingState>
        {
            [LightingPreset.Dawn] = new(
                LightingPreset.Dawn,
                new Color("f6b982"), 1.15f, -9, DefaultYawDegrees,
                new Color("8b6d78"), new Color("b58a8b"), 0.62f,
                null, 1.0f,
                new Color("d9a58a"), 0.00045f, 0.55f,
                new Color("5d6f9c"), new Color("f2b98e"), new Color("8a6f66"), 1.0f),
            [LightingPreset.Day] = new(
                LightingPreset.Day,
                new Color("fff2d6"), 1.8f, -48, DefaultYawDegrees,
                new Color("78a7d8"), new Color("dbe8f6"), 0.8f,
                null, 1.0f,
                new Color("c9d8ea"), 0.00012f, 0.5f,
                new Color("3f78c9"), new Color("c4d8ee"), new Color("8b9a8a"), 1.0f),
            [LightingPreset.Overcast] = new(
                LightingPreset.Overcast,
                new Color("d8e0e5"), 0.72f, -54, DefaultYawDegrees,
                new Color("687683"), new Color("a7b2b9"), 0.92f,
                null, 1.0f,
                new Color("b9c2c9"), 0.00060f, 0.7f,
                new Color("8c98a3"), new Color("c6cdd3"), new Color("7f8985"), 1.0f),
            [LightingPreset.Night] = new(
                LightingPreset.Night,
                new Color("a9c4ff"), 1.3f, -24, DefaultYawDegrees,
                new Color("060912"), new Color("425072"), 0.45f,
                null, 1.0f,
                new Color("0d1322"), 0.00030f, 0.3f,
                new Color("04070f"), new Color("101a2e"), new Color("06090f"), 1.0f),
        };
        _states = OverlayPresets(defaults);
        return _states;
    }

    /// <summary>
    /// Overlays the sourced sky presets when the runtime file exists. The file
    /// is generated by <c>tools/environments/analyze_skies.py</c> from the locked
    /// HDRIs and records each panorama path plus its measured sun azimuth and
    /// elevation, so shadows fall away from the sun that is visible in the sky.
    /// </summary>
    private static IReadOnlyDictionary<LightingPreset, LightingState> OverlayPresets(
        Dictionary<LightingPreset, LightingState> defaults)
    {
        if (!Godot.FileAccess.FileExists(PresetsPath))
        {
            return defaults;
        }
        using var file = Godot.FileAccess.Open(PresetsPath, Godot.FileAccess.ModeFlags.Read);
        using var document = JsonDocument.Parse(file.GetAsText());
        if (!document.RootElement.TryGetProperty("presets", out var presets))
        {
            return defaults;
        }
        foreach (var entry in presets.EnumerateObject())
        {
            if (!Enum.TryParse<LightingPreset>(entry.Name, ignoreCase: true, out var preset))
            {
                continue;
            }
            var current = defaults[preset];
            var panorama = entry.Value.TryGetProperty("panorama", out var panoramaValue)
                ? panoramaValue.GetString()
                : null;
            var yaw = entry.Value.TryGetProperty("light_yaw_degrees", out var yawValue)
                ? (float)yawValue.GetDouble()
                : current.YawDegrees;
            var pitch = entry.Value.TryGetProperty("light_pitch_degrees", out var pitchValue)
                ? (float)pitchValue.GetDouble()
                : current.PitchDegrees;
            var skyEnergy = entry.Value.TryGetProperty("sky_energy", out var energyValue)
                ? (float)energyValue.GetDouble()
                : current.SkyEnergy;
            defaults[preset] = current with
            {
                PanoramaPath = panorama,
                YawDegrees = yaw,
                PitchDegrees = pitch,
                SkyEnergy = skyEnergy,
            };
        }
        return defaults;
    }
}
