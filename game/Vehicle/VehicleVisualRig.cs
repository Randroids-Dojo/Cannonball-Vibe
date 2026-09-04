using Godot;

namespace Cannonball.Game.Vehicle;

public sealed partial class VehicleVisualRig : Node3D
{
    public const uint CockpitExteriorRenderLayer = 1u << 19;
    public const string CarPaintShaderPath = "res://assets/vehicles/hero-gt/shaders/car_paint.gdshader";

    public static readonly string[] RequiredSemanticNodes =
    [
        "AssetRoot", "Chassis", "Visual_LOD0", "Visual_LOD1", "Visual_LOD2",
        "CollisionProxy", "Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR",
        "Suspension_FL", "Suspension_FR", "Suspension_RL", "Suspension_RR",
        "Contact_FL", "Contact_FR", "Contact_RL", "Contact_RR",
        "Camera_ChaseTarget", "Camera_Cockpit", "Light_Head_FL", "Light_Head_FR",
        "Light_Tail_RL", "Light_Tail_RR", "Exhaust_L", "Exhaust_R",
        "Driver_Reference", "MaterialGroup_Body", "MaterialGroup_Glass",
        "MaterialGroup_Wheels", "MaterialGroup_Interior", "MaterialGroup_Lights",
        "Damage_Front", "Damage_Rear", "Damage_Left", "Damage_Right", "Damage_Roof",
    ];

    /// <summary>
    /// Meshes the cockpit camera must not draw: the glass it sits behind and
    /// the roof it sits under. The interior stays visible; that is the point
    /// of a cockpit view.
    /// </summary>
    public static readonly string[] CockpitExcludedMeshes = ["LOD0_Cabin", "LOD0_RoofSpine"];

    /// <summary>
    /// Texture bindings the packer detached from the generated scene. The
    /// sourced maps live in a rights-gated folder the release presets
    /// exclude, and a scene that names a missing resource fails to load, so
    /// the scene ships untextured and the wrapper binds whatever exists.
    /// </summary>
    public const string SourcedTexturesPath = "res://assets/vehicles/hero-gt/hero-gt.generated.textures.json";

    private static readonly string[] WheelSuffixes = ["FL", "FR", "RL", "RR"];
    private readonly Node3D[] _wheelPivots = new Node3D[4];
    private readonly Node3D[] _suspensionAnchors = new Node3D[4];
    private readonly Vector3[] _suspensionRestPositions = new Vector3[4];
    private readonly List<MeshInstance3D> _damageIndicators = [];
    private readonly Godot.Collections.Dictionary _automationState = new();
    private Node3D _lod0 = null!;
    private Node3D _lod1 = null!;
    private Node3D _lod2 = null!;
    private float _wheelRotationRadians;

    public bool ContractResolved { get; private set; }
    public int ResolvedSemanticNodeCount { get; private set; }
    public int ActiveLod { get; private set; }
    public float SteeringRadians { get; private set; }
    public float WheelRotationRadians => _wheelRotationRadians;
    public float MaximumSuspensionTravelMeters { get; private set; }
    public Node3D ChaseCameraTarget { get; private set; } = null!;
    public Node3D CockpitCameraAnchor { get; private set; } = null!;

    public override void _Ready()
    {
        Name = "HeroGtVisualRig";
        var resolved = RequiredSemanticNodes.ToDictionary(
            name => name,
            name => FindDescendant(this, name) ??
                throw new InvalidOperationException($"Hero GT wrapper is missing semantic node {name}."),
            StringComparer.Ordinal);
        ResolvedSemanticNodeCount = resolved.Count;
        ContractResolved = true;
        SetMeta("vehicle_visual_rig_ready", true);
        SetMeta("automation_state", _automationState);
        _lod0 = (Node3D)resolved["Visual_LOD0"];
        _lod1 = (Node3D)resolved["Visual_LOD1"];
        _lod2 = (Node3D)resolved["Visual_LOD2"];
        ChaseCameraTarget = (Node3D)resolved["Camera_ChaseTarget"];
        CockpitCameraAnchor = (Node3D)resolved["Camera_Cockpit"];
        for (var index = 0; index < WheelSuffixes.Length; index++)
        {
            var suffix = WheelSuffixes[index];
            _wheelPivots[index] = (Node3D)resolved[$"Wheel_{suffix}"];
            _suspensionAnchors[index] = (Node3D)resolved[$"Suspension_{suffix}"];
            _suspensionRestPositions[index] = _suspensionAnchors[index].Position;
        }
        BuildDamageIndicators(resolved);
        BindSourcedTextures();
        PolishImportedMaterials();
        // The collision proxy is a contract node for collision policy, not a
        // visual; the third-generation body tucks under at the sills and
        // tapers at the tail, so the box would show if it were drawn.
        if (resolved["CollisionProxy"] is GeometryInstance3D collisionProxy)
        {
            collisionProxy.Visible = false;
        }
        SetLod(0);
        SetDamageHighlight(false);
        _automationState["cockpit_excluded_mesh_count"] = 0;
        _automationState["cockpit_exterior_layer"] = (long)CockpitExteriorRenderLayer;
    }

    public void ApplyPhysicsState(
        float steeringRadians,
        float longitudinalSpeedMetersPerSecond,
        float deltaSeconds,
        IReadOnlyList<float> suspensionCompressionMeters)
    {
        if (!ContractResolved || suspensionCompressionMeters.Count != 4)
        {
            return;
        }
        SteeringRadians = steeringRadians;
        _wheelRotationRadians = Mathf.Wrap(
            _wheelRotationRadians + longitudinalSpeedMetersPerSecond / 0.34f * deltaSeconds,
            -Mathf.Pi,
            Mathf.Pi);
        MaximumSuspensionTravelMeters = 0;
        for (var index = 0; index < _wheelPivots.Length; index++)
        {
            var compression = Mathf.Clamp(suspensionCompressionMeters[index], 0, 0.62f);
            MaximumSuspensionTravelMeters = Math.Max(MaximumSuspensionTravelMeters, compression);
            _suspensionAnchors[index].Position =
                _suspensionRestPositions[index] + Vector3.Up * compression;
            var steering = index < 2 ? steeringRadians : 0;
            _wheelPivots[index].Basis =
                new Basis(Vector3.Up, steering) * new Basis(Vector3.Right, _wheelRotationRadians);
        }
    }

    public void SetLod(int lod)
    {
        ActiveLod = Math.Clamp(lod, 0, 2);
        SetVisualVisibility(_lod0, ActiveLod == 0);
        SetVisualVisibility(_lod1, ActiveLod == 1);
        SetVisualVisibility(_lod2, ActiveLod == 2);
        // Rolling wheels and brakes hang under the pivots and anchors, outside
        // the LOD groups; they show with LOD0 only.
        foreach (var suffix in WheelSuffixes)
        {
            foreach (var root in new[] { FindDescendant(this, $"Wheel_{suffix}"), FindDescendant(this, $"Suspension_{suffix}") })
            {
                if (root is null)
                {
                    continue;
                }
                foreach (var child in Descendants(root).OfType<GeometryInstance3D>())
                {
                    child.Visible = ActiveLod == 0;
                }
            }
        }
    }

    public void SetDamageHighlight(bool visible)
    {
        foreach (var indicator in _damageIndicators)
        {
            indicator.Visible = visible;
        }
    }

    public void ConfigureCockpitCamera(Camera3D camera)
    {
        ArgumentNullException.ThrowIfNull(camera);
        var excludedCount = 0;
        foreach (var name in CockpitExcludedMeshes)
        {
            if (FindDescendant(this, name) is not GeometryInstance3D geometry)
            {
                throw new InvalidOperationException(
                    $"Hero GT cockpit exclusion mesh '{name}' is missing.");
            }
            geometry.Layers = CockpitExteriorRenderLayer;
            excludedCount++;
        }
        camera.CullMask &= ~CockpitExteriorRenderLayer;
        _automationState["cockpit_excluded_mesh_count"] = excludedCount;
        _automationState["cockpit_excluded_meshes"] = new Godot.Collections.Array<string>(CockpitExcludedMeshes);
        _automationState["cockpit_camera_cull_mask"] = (long)camera.CullMask;
        _automationState["chase_exterior_geometry_visible"] = true;
    }

    /// <summary>
    /// Material properties the glTF importer cannot carry, applied by the
    /// project-owned wrapper as ADR-0012 directs. The Blender source records
    /// its intent as material custom properties, which arrive as the
    /// material's <c>extras</c> metadata: the paint becomes the flake
    /// clear-coat shader, glass becomes a depth-sorted transparent surface,
    /// carbon keeps its clear coat, and cut metal stays fully metallic. A
    /// re-export cannot erase this because it is keyed by the extras the
    /// export itself writes; materials without extras fall back to their
    /// names so the second-generation asset keeps working.
    /// </summary>
    private void BindSourcedTextures()
    {
        var bound = 0;
        var missing = 0;
        _automationState["sourced_textures_bound"] = 0;
        _automationState["sourced_textures_missing"] = 0;
        if (!FileAccess.FileExists(SourcedTexturesPath))
        {
            return;
        }
        var parsed = Json.ParseString(FileAccess.GetFileAsString(SourcedTexturesPath));
        if (parsed.Obj is not Godot.Collections.Dictionary sidecar ||
            !sidecar.TryGetValue("materials", out var materialsValue) ||
            materialsValue.Obj is not Godot.Collections.Dictionary bindings)
        {
            GD.PushWarning($"Hero GT texture sidecar {SourcedTexturesPath} is not a schema-1 binding table.");
            return;
        }
        using (sidecar)
        using (bindings)
        {
            var seen = new HashSet<Rid>();
            foreach (var meshInstance in Descendants(this).OfType<MeshInstance3D>())
            {
                using var mesh = meshInstance.Mesh;
                if (mesh is null)
                {
                    continue;
                }
                for (var surface = 0; surface < mesh.GetSurfaceCount(); surface++)
                {
                    using var surfaceMaterial = mesh.SurfaceGetMaterial(surface);
                    if (surfaceMaterial is not StandardMaterial3D material || !seen.Add(material.GetRid()))
                    {
                        continue;
                    }
                    if (!bindings.TryGetValue(material.ResourceName, out var slotsValue) ||
                        slotsValue.Obj is not Godot.Collections.Dictionary slots)
                    {
                        continue;
                    }
                    using (slots)
                    {
                        foreach (var slot in slots.Keys)
                        {
                            var path = slots[slot].AsString();
                            if (!ResourceLoader.Exists(path))
                            {
                                missing++;
                                continue;
                            }
                            using var texture = ResourceLoader.Load<Texture2D>(path);
                            material.Set(slot.AsString(), texture);
                            bound++;
                        }
                    }
                }
            }
        }
        _automationState["sourced_textures_bound"] = bound;
        _automationState["sourced_textures_missing"] = missing;
    }

    private void PolishImportedMaterials()
    {
        var polished = 0;
        var paintShader = ResourceLoader.Exists(CarPaintShaderPath)
            ? ResourceLoader.Load<Shader>(CarPaintShaderPath)
            : null;
        var paintMaterials = new Dictionary<string, ShaderMaterial>(StringComparer.Ordinal);
        foreach (var meshInstance in Descendants(this).OfType<MeshInstance3D>())
        {
            // Every wrapper taken here is released before the next mesh: the
            // scene owns the native resources, and managed wrappers left to the
            // garbage collector finalize after the native side is gone at
            // shutdown, which the .NET runtime reports as a fatal error.
            using var mesh = meshInstance.Mesh;
            if (mesh is null)
            {
                continue;
            }
            for (var surface = 0; surface < mesh.GetSurfaceCount(); surface++)
            {
                using var surfaceMaterial = mesh.SurfaceGetMaterial(surface);
                if (surfaceMaterial is not StandardMaterial3D material)
                {
                    continue;
                }
                var name = material.ResourceName;
                using var extras = material.HasMeta("extras") && material.GetMeta("extras").Obj is Godot.Collections.Dictionary dictionary
                    ? dictionary
                    : new Godot.Collections.Dictionary();
                var family = extras.TryGetValue("cv_shader", out var shaderValue)
                    ? shaderValue.AsString()
                    : FamilyFromName(name);
                switch (family)
                {
                    case "car_paint" when paintShader is not null:
                        if (!paintMaterials.TryGetValue(name, out var paint))
                        {
                            paint = BuildCarPaint(paintShader, material, extras);
                            paintMaterials[name] = paint;
                        }
                        meshInstance.SetSurfaceOverrideMaterial(surface, paint);
                        polished++;
                        break;
                    case "car_paint":
                        material.ClearcoatEnabled = true;
                        material.Clearcoat = 1.0f;
                        material.ClearcoatRoughness = 0.05f;
                        material.Metallic = 0.22f;
                        material.MetallicSpecular = 0.55f;
                        material.Roughness = 0.38f;
                        polished++;
                        break;
                    case "glass":
                        material.Transparency = BaseMaterial3D.TransparencyEnum.Alpha;
                        material.DepthDrawMode = BaseMaterial3D.DepthDrawModeEnum.Always;
                        material.CullMode = BaseMaterial3D.CullModeEnum.Back;
                        material.Roughness = Math.Clamp(material.Roughness, 0.02f, 0.1f);
                        material.Metallic = 0.0f;
                        material.MetallicSpecular = 0.6f;
                        material.SpecularMode = BaseMaterial3D.SpecularModeEnum.SchlickGgx;
                        material.RenderPriority = name.Contains("Lens", StringComparison.Ordinal) ? 1 : 0;
                        polished++;
                        break;
                    case "clearcoat":
                        material.ClearcoatEnabled = true;
                        material.Clearcoat = extras.TryGetValue("cv_clearcoat", out var coat) ? (float)coat.AsDouble() : 1.0f;
                        material.ClearcoatRoughness = extras.TryGetValue("cv_clearcoat_roughness", out var coatRoughness)
                            ? (float)coatRoughness.AsDouble()
                            : 0.06f;
                        polished++;
                        break;
                    case "metal":
                        material.Metallic = 1.0f;
                        material.Roughness = Math.Clamp(material.Roughness, 0.12f, 0.4f);
                        polished++;
                        break;
                }
                if (extras.TryGetValue("cv_alpha_scissor", out var scissor))
                {
                    material.Transparency = BaseMaterial3D.TransparencyEnum.AlphaScissor;
                    material.AlphaScissorThreshold = (float)scissor.AsDouble();
                    material.CullMode = BaseMaterial3D.CullModeEnum.Disabled;
                }
            }
        }
        _automationState["polished_material_surfaces"] = polished;
        _automationState["car_paint_shader"] = paintShader is not null;
        // Every surface now holds its own native reference; releasing the
        // managed wrappers here keeps the .NET finalizer from touching
        // resources the scene tree has already freed at shutdown (the same
        // rule the damage indicators follow).
        foreach (var paint in paintMaterials.Values)
        {
            paint.Dispose();
        }
        paintShader?.Dispose();
    }

    private static string FamilyFromName(string name)
    {
        if (name.EndsWith("Material_Body", StringComparison.Ordinal))
        {
            return "car_paint";
        }
        if (name.EndsWith("Material_Glass", StringComparison.Ordinal))
        {
            return "glass";
        }
        if (name.EndsWith("Material_Wheel", StringComparison.Ordinal) || name.EndsWith("Material_Trim", StringComparison.Ordinal))
        {
            return "metal";
        }
        return "";
    }

    private static ShaderMaterial BuildCarPaint(Shader shader, StandardMaterial3D source, Godot.Collections.Dictionary extras)
    {
        var paint = new ShaderMaterial { Shader = shader, ResourceName = source.ResourceName };
        paint.SetShaderParameter("base_color", source.AlbedoColor);
        paint.SetShaderParameter("metallic", source.Metallic);
        paint.SetShaderParameter("roughness", source.Roughness);
        if (extras.TryGetValue("cv_clearcoat", out var coat))
        {
            paint.SetShaderParameter("clearcoat", (float)coat.AsDouble());
        }
        if (extras.TryGetValue("cv_clearcoat_roughness", out var coatRoughness))
        {
            paint.SetShaderParameter("clearcoat_roughness", Math.Max(0.01f, (float)coatRoughness.AsDouble()));
        }
        if (extras.TryGetValue("cv_flake_scale", out var flakeScale))
        {
            paint.SetShaderParameter("flake_scale", (float)flakeScale.AsDouble());
        }
        if (extras.TryGetValue("cv_flake_strength", out var flakeStrength))
        {
            paint.SetShaderParameter("flake_strength", (float)flakeStrength.AsDouble());
        }
        if (extras.TryGetValue("cv_normal_strength", out var normalStrength))
        {
            paint.SetShaderParameter("orange_peel_strength", (float)normalStrength.AsDouble());
        }
        if (extras.TryGetValue("cv_edge_tint", out var edgeTint) && edgeTint.Obj is Godot.Collections.Array tint && tint.Count == 3)
        {
            paint.SetShaderParameter("edge_tint", new Color((float)tint[0].AsDouble(), (float)tint[1].AsDouble(), (float)tint[2].AsDouble()));
        }
        if (source.NormalTexture is { } orangePeel)
        {
            paint.SetShaderParameter("orange_peel", orangePeel);
        }
        return paint;
    }

    public VehicleVisualSnapshot CaptureSnapshot() => new(
        ContractResolved,
        ResolvedSemanticNodeCount,
        ActiveLod,
        SteeringRadians,
        WheelRotationRadians,
        MaximumSuspensionTravelMeters,
        ChaseCameraTarget.Position,
        CockpitCameraAnchor.Position,
        _damageIndicators.Count);

    private void BuildDamageIndicators(IReadOnlyDictionary<string, Node> resolved)
    {
        // Released once every indicator has taken its own reference; see the note
        // in CannonballVehicle.
        using var material = new StandardMaterial3D
        {
            AlbedoColor = new Color(1.0f, 0.08f, 0.035f, 0.72f),
            EmissionEnabled = true,
            Emission = new Color(1.0f, 0.02f, 0.01f),
            EmissionEnergyMultiplier = 2.5f,
            Transparency = BaseMaterial3D.TransparencyEnum.Alpha,
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
        };
        foreach (var name in new[] { "Damage_Front", "Damage_Rear", "Damage_Left", "Damage_Right", "Damage_Roof" })
        {
            var anchor = (Node3D)resolved[name];
            using var indicatorMesh = new SphereMesh { Radius = 0.12f, Height = 0.24f };
            var indicator = new MeshInstance3D
            {
                Name = $"{name}_Indicator",
                Mesh = indicatorMesh,
                MaterialOverride = material,
            };
            anchor.AddChild(indicator);
            _damageIndicators.Add(indicator);
        }
    }

    private static void SetVisualVisibility(Node root, bool visible)
    {
        foreach (var geometry in Descendants(root).OfType<GeometryInstance3D>())
        {
            geometry.Visible = visible;
        }
    }

    private static Node? FindDescendant(Node root, string name) =>
        Descendants(root).FirstOrDefault(node => node.Name == name);

    private static IEnumerable<Node> Descendants(Node root)
    {
        foreach (var child in root.GetChildren())
        {
            yield return child;
            foreach (var descendant in Descendants(child))
            {
                yield return descendant;
            }
        }
    }
}

public sealed record VehicleVisualSnapshot(
    bool ContractResolved,
    int SemanticNodeCount,
    int ActiveLod,
    float SteeringRadians,
    float WheelRotationRadians,
    float MaximumSuspensionTravelMeters,
    Vector3 ChaseCameraTarget,
    Vector3 CockpitCameraAnchor,
    int DamageZoneCount);
