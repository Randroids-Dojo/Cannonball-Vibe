using System;
using System.Linq;
using Godot;

namespace Cannonball.Game.World.Environments;

/// <summary>
/// Applies the renderer-wide quality tier that <c>project.godot</c> cannot
/// express per profile: MSAA, the directional shadow atlas, soft shadow
/// filtering and SSAO quality.
/// </summary>
/// <remarks>
/// The project defaults are the Balanced tier so that headless gates and the
/// software-rendered CI runners never pay for the reference PC. The High tier
/// is the ADR-0023 target (2560x1440 at 60 FPS on an RTX 3080 Ti) and is
/// selected with <c>--environment-quality=high</c>, the same argument that
/// scales the environment layers. Low and Graybox share the Balanced renderer
/// settings; their savings come from the environment kit, not the renderer.
/// </remarks>
public static class RenderQuality
{
    public static readonly string[] AutomationKeys = ["render_quality", "msaa_3d", "directional_shadow_size"];

    public static void Apply(Viewport viewport, EnvironmentQuality quality)
    {
        ArgumentNullException.ThrowIfNull(viewport);
        var high = quality == EnvironmentQuality.High;
        var msaa = high ? Viewport.Msaa.Msaa4X : Viewport.Msaa.Msaa2X;
        var shadowSize = high ? 8192 : 4096;
        var shadowQuality = high
            ? RenderingServer.ShadowQuality.SoftMedium
            : RenderingServer.ShadowQuality.SoftLow;
        var ssaoQuality = high
            ? RenderingServer.EnvironmentSsaoQuality.Medium
            : RenderingServer.EnvironmentSsaoQuality.Low;

        viewport.Msaa3D = msaa;
        RenderingServer.DirectionalShadowAtlasSetSize(shadowSize, true);
        RenderingServer.DirectionalSoftShadowFilterSetQuality(shadowQuality);
        RenderingServer.EnvironmentSetSsaoQuality(
            ssaoQuality,
            (bool)ProjectSettings.GetSetting("rendering/environment/ssao/half_size", true),
            (float)ProjectSettings.GetSetting("rendering/environment/ssao/adaptive_target", 0.5f),
            (int)ProjectSettings.GetSetting("rendering/environment/ssao/blur_passes", 2),
            (float)ProjectSettings.GetSetting("rendering/environment/ssao/fade_out_from", 50.0f),
            (float)ProjectSettings.GetSetting("rendering/environment/ssao/fade_out_to", 300.0f));

        viewport.SetMeta("render_quality", quality.ToString().ToLowerInvariant());
        viewport.SetMeta("msaa_3d", (int)msaa);
        viewport.SetMeta("directional_shadow_size", shadowSize);
    }

    public static EnvironmentQuality FromCommandLine()
    {
        var arguments = OS.GetCmdlineUserArgs();
        if (arguments.Contains(SkyLighting.GrayboxArgument, StringComparer.Ordinal))
        {
            return EnvironmentQuality.Graybox;
        }
        var qualityArgument = arguments.FirstOrDefault(value =>
            value.StartsWith("--environment-quality=", StringComparison.Ordinal));
        var value = qualityArgument?["--environment-quality=".Length..] ?? "balanced";
        return Enum.TryParse<EnvironmentQuality>(value, ignoreCase: true, out var quality)
            ? quality
            : EnvironmentQuality.Balanced;
    }
}
