using Godot;

namespace Cannonball.Game.Vehicle.Showroom;

public partial class VehicleShowroom
{
    private void BuildStudio()
    {
        _skyMaterial = new ShaderMaterial { Shader = GD.Load<Shader>("res://game/Vehicle/Showroom/studio_sky.gdshader") };
        using var sky = new Sky { SkyMaterial = _skyMaterial, RadianceSize = Sky.RadianceSizeEnum.Size256, ProcessMode = Sky.ProcessModeEnum.Realtime };
        _environment = new Godot.Environment
        {
            BackgroundMode = Godot.Environment.BGMode.Sky, Sky = sky,
            AmbientLightSource = Godot.Environment.AmbientSource.Color,
            AmbientLightColor = new Color(.72f, .78f, .86f), AmbientLightEnergy = .6f,
            ReflectedLightSource = Godot.Environment.ReflectionSource.Sky,
            TonemapMode = Godot.Environment.ToneMapper.Agx, TonemapExposure = 1,
            SsaoEnabled = true, SsaoRadius = .6f, SsaoIntensity = 1.4f, SsaoPower = 1.2f,
            SsaoDetail = .6f, SsaoLightAffect = .15f,
            GlowEnabled = true, GlowIntensity = .22f, GlowHdrThreshold = 1.7f,
        };
        _world.AddChild(new WorldEnvironment { Environment = _environment });
        _key = new DirectionalLight3D
        {
            Name = "StudioKey", RotationDegrees = new Vector3(-48, -35, 0),
            LightEnergy = 2.1f, LightColor = new Color(1, .96f, .9f),
            ShadowEnabled = true, ShadowBias = .1f, ShadowNormalBias = 1,
            DirectionalShadowMode = DirectionalLight3D.ShadowMode.Orthogonal,
            DirectionalShadowMaxDistance = 20, LightAngularDistance = 8,
        };
        _fill = new DirectionalLight3D
        {
            Name = "StudioFill", RotationDegrees = new Vector3(-18, 135, 0),
            LightEnergy = .65f, LightColor = new Color(.76f, .86f, 1), ShadowEnabled = false,
        };
        _world.AddChild(_key); _world.AddChild(_fill);
        _inspectionLight = new DirectionalLight3D
        {
            Name = "UnderbodyInspectionLight", RotationDegrees = new Vector3(70, 20, 0),
            LightEnergy = 1.8f, LightColor = new Color(.9f, .95f, 1),
            ShadowEnabled = false, Visible = false,
        };
        _world.AddChild(_inspectionLight);
        _floor = new Node3D { Name = "StudioFloor" };
        _world.AddChild(_floor);
        using var floorMaterial = new StandardMaterial3D { AlbedoColor = new Color(.085f, .09f, .10f), Roughness = .68f, Metallic = .12f };
        using var floorMesh = new PlaneMesh { Size = new Vector2(120, 120) };
        _floor.AddChild(new MeshInstance3D { Mesh = floorMesh, MaterialOverride = floorMaterial, Position = new Vector3(0, -.012f, 0) });
        using var ringMaterial = new StandardMaterial3D
        {
            AlbedoColor = new Color(.28f, .29f, .3f), Roughness = .72f,
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
        };
        using var ring = new TorusMesh { InnerRadius = 3.18f, OuterRadius = 3.192f, Rings = 96, RingSegments = 6 };
        _floor.AddChild(new MeshInstance3D { Mesh = ring, MaterialOverride = ringMaterial, Position = new Vector3(0, -.006f, 0) });
    }

    private void SetLighting(int preset)
    {
        _lighting = preset switch { 1 => "daylight", 2 => "night", _ => "studio" };
        _skyMaterial.SetShaderParameter("daylight", preset == 1 ? 1f : 0f);
        _skyMaterial.SetShaderParameter("panel_energy", preset == 2 ? 1.2f : 2.4f);
        _skyMaterial.SetShaderParameter("base_energy", preset == 2 ? .12f : preset == 1 ? .65f : .20f);
        _skyMaterial.SetShaderParameter("horizon_fill", preset == 2 ? .24f : 0f);
        _key.LightEnergy = preset == 2 ? .45f : preset == 1 ? 2.6f : 2.1f;
        _key.LightAngularDistance = preset == 1 ? .6f : 8;
        _key.LightColor = preset == 2 ? new Color(.55f, .69f, 1) : new Color(1, .96f, .9f);
        _fill.LightEnergy = preset == 2 ? .9f : .65f;
        _environment.AmbientLightEnergy = preset == 2 ? .5f : preset == 1 ? .8f : .6f;
        _presentation?.SetEnvironmentHeadlights(preset == 2);
        if (_presentation is null) _rig?.SetHeadlights(preset == 2);
        _metrics?.BeginCase(_view, _lighting);
        UpdateInterface();
    }
}
