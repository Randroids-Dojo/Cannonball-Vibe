using Godot;

namespace Cannonball.Game.Vehicle;

public sealed partial class VehicleVisualRig : Node3D
{
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

    private static readonly string[] WheelSuffixes = ["FL", "FR", "RL", "RR"];
    private readonly Node3D[] _wheelPivots = new Node3D[4];
    private readonly Node3D[] _suspensionAnchors = new Node3D[4];
    private readonly Vector3[] _suspensionRestPositions = new Vector3[4];
    private readonly List<MeshInstance3D> _damageIndicators = [];
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
        SetLod(0);
        SetDamageHighlight(false);
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
        foreach (var suffix in WheelSuffixes)
        {
            var wheel = FindDescendant(this, $"Wheel_{suffix}");
            if (wheel is not null)
            {
                foreach (var child in Descendants(wheel).OfType<GeometryInstance3D>())
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
        var material = new StandardMaterial3D
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
            var indicator = new MeshInstance3D
            {
                Name = $"{name}_Indicator",
                Mesh = new SphereMesh { Radius = 0.12f, Height = 0.24f },
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
