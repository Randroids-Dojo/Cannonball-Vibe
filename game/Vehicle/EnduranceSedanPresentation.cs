using Cannonball.Game.Input;
using Godot;

namespace Cannonball.Game.Vehicle;

/// <summary>Runtime-driven lights, cockpit, opening panels, wipers and live mirrors.</summary>
public partial class EnduranceSedanPresentation : Node
{
    public static readonly string[] OpeningNames = ["Door_FL", "Door_FR", "Door_RL", "Door_RR", "Hood_Hinge", "Trunk_Hinge"];
    public static readonly string[] RequiredNodes =
    [
        .. OpeningNames, "SteeringWheel_Pivot", "Pedal_Accelerator", "Pedal_Brake", "Wiper_L", "Wiper_R",
        "Mirror_Left", "Mirror_Right", "Mirror_Rear", "MirrorCamera_Left", "MirrorCamera_Right", "MirrorCamera_Rear",
        "Instrument_Cluster", "Light_Brake_L", "Light_Brake_R", "Light_Brake_Center", "Light_Reverse_L", "Light_Reverse_R",
        "Light_Indicator_FL", "Light_Indicator_FR", "Light_Indicator_RL", "Light_Indicator_RR",
    ];
    public const uint MirrorSurfaceLayer = 1u << 18;
    private readonly Dictionary<string, Joint> _joints = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Lamp> _lamps = new(StringComparer.Ordinal);
    private readonly List<Mirror> _mirrors = [];
    private readonly List<StandardMaterial3D> _ownedMaterials = [];
    private readonly Dictionary<(ulong SourceRid, string Channel), StandardMaterial3D> _lampMaterialCache = [];
    private readonly Godot.Collections.Dictionary _automationState = new();
    private VehicleVisualRig _rig = null!;
    private CannonballVehicle _vehicle = null!;
    private EnduranceSedanPresentationSetup _setup = null!;
    private SubViewport _instruments = null!;
    private Label _speedLabel = null!;
    private Label _gearLabel = null!;
    private Label _rpmLabel = null!;
    private Label _fuelLabel = null!;
    private Label _warningLabel = null!;
    private ProgressBar _rpmBar = null!;
    private ProgressBar _fuelBar = null!;
    private double _elapsed;
    private double _instrumentElapsed;
    private double _wiperPhase;
    private bool _wiperParking;
    private bool _environmentHeadlights = true;
    private float _speedMph;
    private float _rpm = 750;
    private string _gear = "P";
    private string _warning = string.Empty;
    private float _steeringWheelAngle;
    private float _acceleratorAngle;
    private float _brakeAngle;

    public bool WipersOn { get; private set; }
    public bool HazardsOn { get; private set; }
    public int IndicatorDirection { get; private set; }
    public int HeadlampMode { get; private set; } // 0 auto, 1 on, 2 off
    public bool HeadlightsOn => HeadlampMode == 1 || HeadlampMode == 0 && _environmentHeadlights;
    public bool AnyOpeningActive
    {
        get
        {
            foreach (var name in OpeningNames)
                if (_joints[name].Value > 0.001f || _joints[name].Target > 0.001f) return true;
            return false;
        }
    }
    public bool AutoLodEnabled { get; set; } = true;
    public ulong LodSelectionRenderFrame { get; private set; }
    public bool LodSelectionInitialized { get; private set; }
    public ulong CreatedRenderFrame { get; private set; }
    public float LodSelectionDistanceMeters { get; private set; }
    public Vector3 LodSelectionCameraPosition { get; private set; }
    public Vector3 LodSelectionBodyPosition { get; private set; }
    public bool MirrorsEnabled { get; set; } = true;
    public bool BrakeLightsOn { get; private set; }
    public bool ReverseLightsOn { get; private set; }
    public bool LeftIndicatorLit { get; private set; }
    public bool RightIndicatorLit { get; private set; }
    public IReadOnlyList<Mirror> Mirrors => _mirrors;
    public EnduranceSedanPresentationSetup Setup => _setup;
    public SubViewport InstrumentViewport => _instruments;
    public Rect2 InstrumentWarningRect => _warningLabel.GetRect();

    public void Configure(VehicleVisualRig rig, CannonballVehicle vehicle, EnduranceSedanPresentationSetup setup)
    {
        _rig = rig;
        _vehicle = vehicle;
        _setup = setup;
        _setup.Validate();
    }

    public override void _Ready()
    {
        Name = "EnduranceSedanPresentation";
        // Both camera rigs update at the default priority. Select LOD only
        // after they have followed a rebase/teleport on this render frame.
        ProcessPriority = 100;
        CreatedRenderFrame = Engine.GetProcessFrames();
        SetMeta("automation_id", "vehicle.endurance-sedan.presentation");
        SetMeta("automation_state", _automationState);
        foreach (var name in RequiredNodes) _ = _rig.ResolveAnchor(name);
        for (var i = 0; i < OpeningNames.Length; i++)
            AddJoint(OpeningNames[i], i < 4 ? Vector3.Up : Vector3.Right, _setup.OpeningAnglesDegrees[i], parentAxis: true);
        AddJoint("SteeringWheel_Pivot", Vector3.Forward, 1, parentAxis: false);
        AddJoint("Pedal_Accelerator", Vector3.Right, _setup.AcceleratorAngleDegrees, parentAxis: false);
        AddJoint("Pedal_Brake", Vector3.Right, _setup.BrakeAngleDegrees, parentAxis: false);
        AddJoint("Wiper_L", _setup.WiperParentAxis.Normalized(), _setup.WiperSweepDegrees[0], parentAxis: true);
        AddJoint("Wiper_R", _setup.WiperParentAxis.Normalized(), _setup.WiperSweepDegrees[1], parentAxis: true);
        BuildLights();
        BuildInstruments();
        BuildMirrors();
        RenderingServer.FramePostDraw += OnFramePostDraw;
        SetProcessUnhandledInput(true);
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (GetTree().Paused || @event.IsEcho()) return;
        var handled = true;
        if (@event.IsActionPressed(GameInputMap.VehicleHeadlights)) CycleHeadlampMode();
        else if (@event.IsActionPressed(GameInputMap.VehicleIndicatorLeft)) SetIndicator(-1);
        else if (@event.IsActionPressed(GameInputMap.VehicleIndicatorRight)) SetIndicator(1);
        else if (@event.IsActionPressed(GameInputMap.VehicleHazards)) SetHazards(!HazardsOn);
        else if (@event.IsActionPressed(GameInputMap.VehicleWipers)) SetWipers(!WipersOn);
        else handled = false;
        if (handled) GetViewport().SetInputAsHandled();
    }

    public override void _Process(double delta)
    {
        _elapsed += delta;
        UpdateJoints((float)delta);
        UpdateLights();
        UpdateInstruments(delta);
        UpdateMirrors();
        if (AutoLodEnabled)
        {
            var camera = _vehicle.GetViewport().GetCamera3D();
            var displayedBody = _vehicle.GetGlobalTransformInterpolated().Origin;
            var distance = camera?.GlobalPosition.DistanceTo(displayedBody) ?? 0;
            LodSelectionRenderFrame = Engine.GetProcessFrames();
            LodSelectionInitialized = true;
            LodSelectionDistanceMeters = distance;
            LodSelectionCameraPosition = camera?.GlobalPosition ?? Vector3.Zero;
            LodSelectionBodyPosition = displayedBody;
            var lod = AnyOpeningActive || _vehicle.CurrentCameraMode == "cockpit" || _vehicle.InspectionActive ? 0 :
                distance >= _setup.Lod2DistanceMeters ? 2 : distance >= _setup.Lod1DistanceMeters ? 1 : 0;
            if (_rig.ActiveLod != lod) _rig.SetLod(lod);
        }
    }

    public bool SetOpening(string name, bool open)
    {
        if (!OpeningNames.Contains(name, StringComparer.Ordinal)) throw new ArgumentException($"Unknown opening {name}");
        if (open && _vehicle.SpeedMetersPerSecond > 0.5f) return false;
        _joints[name].Target = open ? 1 : 0;
        return true;
    }
    public bool OpeningTarget(string name) => _joints[name].Target > 0.5f;
    public float OpeningAngleDegrees(string name) => _joints[name].AngleDegrees;
    public void SetWipers(bool on) { WipersOn = on; _wiperParking |= !on && _wiperPhase > 0.001; }
    public void SetHazards(bool on) => HazardsOn = on;
    public void SetIndicator(int direction) => IndicatorDirection = direction == IndicatorDirection ? 0 : Math.Clamp(direction, -1, 1);
    public void SetHeadlampMode(int mode) => HeadlampMode = Math.Clamp(mode, 0, 2);
    public void CycleHeadlampMode() => SetHeadlampMode((HeadlampMode + 1) % 3);
    public void SetEnvironmentHeadlights(bool on) => _environmentHeadlights = on;

    private void AddJoint(string name, Vector3 axis, float maximumDegrees, bool parentAxis)
    {
        var node = _rig.ResolveAnchor(name);
        _joints[name] = new Joint(node, node.Basis, axis, maximumDegrees, parentAxis);
    }

    private void UpdateJoints(float delta)
    {
        foreach (var name in OpeningNames)
        {
            var joint = _joints[name];
            joint.Value = Mathf.MoveToward(joint.Value, joint.Target, delta / _setup.OpeningDurationSeconds);
            joint.Apply(joint.MaximumDegrees * joint.Value);
        }
        var input = _vehicle.LastDriveInput;
        // A positive turn about the local forward-facing column moves the
        // top of the rim right, matching the front tires' rightward heading.
        _steeringWheelAngle = Mathf.RadToDeg(_vehicle.CurrentSteeringRadians) * _setup.SteeringRatio;
        _acceleratorAngle = _setup.AcceleratorAngleDegrees * Math.Max(input.Throttle, input.Reverse);
        _brakeAngle = _setup.BrakeAngleDegrees * input.Brake;
        _joints["SteeringWheel_Pivot"].Apply(_steeringWheelAngle);
        _joints["Pedal_Accelerator"].Apply(_acceleratorAngle);
        _joints["Pedal_Brake"].Apply(_brakeAngle);
        if (WipersOn || _wiperParking)
        {
            var previous = _wiperPhase;
            _wiperPhase = (_wiperPhase + delta / _setup.WiperPeriodSeconds) % 1;
            if (!WipersOn && _wiperPhase < previous) { _wiperParking = false; _wiperPhase = 0; }
        }
        var sweep = (float)(0.5 - 0.5 * Math.Cos(_wiperPhase * Math.Tau));
        _joints["Wiper_L"].Apply(_setup.WiperSweepDegrees[0] * sweep);
        _joints["Wiper_R"].Apply(_setup.WiperSweepDegrees[1] * sweep);
    }

    private void BuildLights()
    {
        foreach (var name in new[] { "Light_Head_FL", "Light_Head_FR" })
        {
            var lamp = BindLamp(name, new Color(0.88f, 0.94f, 1), 6);
            var beam = new SpotLight3D
            {
                Name = name + "_Beam", LightColor = new Color(0.88f, 0.94f, 1), LightEnergy = 8,
                SpotRange = 110, SpotAngle = 34, SpotAttenuation = 1.0f,
                ShadowEnabled = !World.Environments.SkyLighting.GrayboxRequested(), RotationDegrees = new Vector3(-2, 0, 0),
            };
            _rig.ResolveAnchor(name).AddChild(beam);
            lamp.Light = beam;
        }
        foreach (var name in new[] { "Light_Tail_RL", "Light_Tail_RR" }) BindLamp(name, new Color(1, 0.012f, 0.006f), 2);
        foreach (var name in new[] { "Light_Brake_L", "Light_Brake_R" })
            BindLamp(name, new Color(1, 0.005f, 0.003f), 9, spill: 0.35f);
        BindLamp("Light_Brake_Center", new Color(1, 0.005f, 0.003f), 9);
        foreach (var name in new[] { "Light_Reverse_L", "Light_Reverse_R" }) BindLamp(name, Colors.White, 5, spill: 0.65f);
        foreach (var name in new[] { "Light_Indicator_FL", "Light_Indicator_FR", "Light_Indicator_RL", "Light_Indicator_RR" })
            BindLamp(name, new Color(1, 0.29f, 0.006f), 7);
    }

    private Lamp BindLamp(string name, Color color, float emission, float spill = 0)
    {
        var anchor = _rig.ResolveAnchor(name);
        var materials = new List<StandardMaterial3D>();
        var channel = name.StartsWith("Light_Head", StringComparison.Ordinal) ? "head" :
            name.StartsWith("Light_Tail", StringComparison.Ordinal) ? "tail" :
            name.StartsWith("Light_Brake", StringComparison.Ordinal) ? "brake" :
            name.StartsWith("Light_Reverse", StringComparison.Ordinal) ? "reverse" :
            name.EndsWith("FL", StringComparison.Ordinal) || name.EndsWith("RL", StringComparison.Ordinal) ? "left-indicator" : "right-indicator";
        foreach (var instance in Meshes(anchor))
        {
            var mesh = instance.Mesh;
            if (mesh is null) continue;
            for (var i = 0; i < mesh.GetSurfaceCount(); i++)
            {
                var source = instance.GetActiveMaterial(i);
                var key = (source?.GetRid().Id ?? 0, channel);
                if (!_lampMaterialCache.TryGetValue(key, out var material))
                {
                    material = source?.Duplicate() as StandardMaterial3D ?? new StandardMaterial3D();
                    material.EmissionEnabled = true;
                    material.Emission = color;
                    material.EmissionEnergyMultiplier = 0;
                    _lampMaterialCache.Add(key, material);
                    _ownedMaterials.Add(material);
                }
                instance.SetSurfaceOverrideMaterial(i, material);
                if (!materials.Contains(material)) materials.Add(material);
            }
        }
        if (materials.Count == 0) throw new InvalidOperationException($"Lamp {name} has no descendant emitter geometry.");
        var lamp = new Lamp(materials, emission);
        if (spill > 0)
        {
            var light = new SpotLight3D
            {
                Name = name + "_Spill", LightColor = color, LightEnergy = spill,
                SpotRange = 4, SpotAngle = 55, SpotAttenuation = 1, ShadowEnabled = false,
                Basis = new Basis(Vector3.Up, Mathf.Pi) * new Basis(Vector3.Right, Mathf.DegToRad(-8)),
            };
            anchor.AddChild(light);
            lamp.Light = light;
        }
        _lamps[name] = lamp;
        return lamp;
    }

    private void UpdateLights()
    {
        var input = _vehicle.LastDriveInput;
        BrakeLightsOn = input.Brake > 0.02f || input.Handbrake > 0.02f;
        ReverseLightsOn = input.Reverse > 0.02f || _vehicle.SignedLongitudinalSpeedMetersPerSecond < -0.2f;
        var blink = _elapsed % 0.75 < 0.375;
        LeftIndicatorLit = blink && (HazardsOn || IndicatorDirection < 0);
        RightIndicatorLit = blink && (HazardsOn || IndicatorDirection > 0);
        foreach (var (name, lamp) in _lamps)
        {
            var lit = name.StartsWith("Light_Head", StringComparison.Ordinal) || name.StartsWith("Light_Tail", StringComparison.Ordinal) ? HeadlightsOn :
                name.StartsWith("Light_Brake", StringComparison.Ordinal) ? BrakeLightsOn :
                name.StartsWith("Light_Reverse", StringComparison.Ordinal) ? ReverseLightsOn :
                name.EndsWith("FL", StringComparison.Ordinal) || name.EndsWith("RL", StringComparison.Ordinal) ? LeftIndicatorLit : RightIndicatorLit;
            lamp.Apply(lit);
        }
    }

    private void BuildInstruments()
    {
        _instruments = new SubViewport
        {
            Name = "InstrumentViewport", Size = new Vector2I(512, 192), Disable3D = true,
            RenderTargetUpdateMode = SubViewport.UpdateMode.Once,
        };
        AddChild(_instruments);
        var background = new ColorRect { Color = new Color("070c11"), Size = new Vector2(512, 192), MouseFilter = Control.MouseFilterEnum.Ignore };
        _instruments.AddChild(background);
        _speedLabel = DisplayLabel(background, new Vector2(34, 15), new Vector2(185, 92), 66, "0");
        DisplayLabel(background, new Vector2(78, 99), new Vector2(100, 30), 19, "MPH");
        _gearLabel = DisplayLabel(background, new Vector2(230, 25), new Vector2(85, 62), 42, "P");
        _rpmLabel = DisplayLabel(background, new Vector2(300, 30), new Vector2(190, 36), 23, "750 RPM");
        _fuelLabel = DisplayLabel(background, new Vector2(300, 88), new Vector2(190, 32), 22, "82 L");
        _warningLabel = DisplayLabel(background, new Vector2(16, 0), new Vector2(480, 28), 20, "");
        _warningLabel.AddThemeColorOverride("font_color", new Color("ffbd4b"));
        _rpmBar = new ProgressBar { Position = new Vector2(306, 69), Size = new Vector2(174, 7), MaxValue = _setup.RedlineRpm, ShowPercentage = false };
        _fuelBar = new ProgressBar { Position = new Vector2(306, 126), Size = new Vector2(174, 7), MaxValue = _setup.FuelCapacityLiters, ShowPercentage = false };
        background.AddChild(_rpmBar);
        background.AddChild(_fuelBar);
        BindScreen(_rig.ResolveAnchor("Instrument_Cluster"), _instruments, mirror: false);
    }

    private static Label DisplayLabel(Control parent, Vector2 position, Vector2 size, int fontSize, string text)
    {
        var label = new Label { Position = position, Size = size, Text = text, HorizontalAlignment = HorizontalAlignment.Center, MouseFilter = Control.MouseFilterEnum.Ignore };
        label.AddThemeFontSizeOverride("font_size", fontSize);
        label.AddThemeColorOverride("font_color", new Color("edf5fb"));
        parent.AddChild(label);
        return label;
    }

    private void UpdateInstruments(double delta)
    {
        _instrumentElapsed += delta;
        if (_instrumentElapsed < 0.05) return;
        _instrumentElapsed %= 0.05;
        var input = _vehicle.LastDriveInput;
        var speed = Math.Abs(_vehicle.SignedLongitudinalSpeedMetersPerSecond);
        _speedMph = speed / 0.44704f;
        var wheelRpm = speed / (Mathf.Tau * _vehicle.RigSetup.TireRadiusMeters) * 60;
        var reverse = ReverseLightsOn;
        var gear = 0;
        var shiftRpm = Mathf.Lerp(2400, 5500, Math.Max(input.Throttle, input.Reverse));
        while (gear < _setup.ForwardGearRatios.Length - 1 && wheelRpm * _setup.ForwardGearRatios[gear] * _setup.FinalDriveRatio > shiftRpm) gear++;
        _gear = reverse ? "R" : speed < 0.15f && input.Throttle < 0.02f ? (input.Handbrake > 0 ? "P" : "N") : (gear + 1).ToString();
        var ratio = reverse ? _setup.ReverseGearRatio : _setup.ForwardGearRatios[gear];
        _rpm = Mathf.Clamp(wheelRpm * ratio * _setup.FinalDriveRatio, _setup.IdleRpm, _setup.RedlineRpm);
        var condition = _vehicle.Condition;
        _warning = condition.FuelLiters < 20 ? "LOW FUEL" : condition.Damage > 0.05 ? "DAMAGE" :
            condition.CoolingCondition < 0.4 ? "COOLING" : condition.TireCondition < 0.3 ? "TIRES" :
            AnyOpeningActive ? "PANEL OPEN" : input.Handbrake > 0.02f ? "PARK BRAKE" : string.Empty;
        _speedLabel.Text = Math.Round(_speedMph).ToString("0");
        _gearLabel.Text = _gear;
        _rpmLabel.Text = $"{Math.Round(_rpm / 10) * 10:0} RPM";
        _fuelLabel.Text = $"{condition.FuelLiters:0} L";
        _warningLabel.Text = $"{(LeftIndicatorLit ? "<" : " ")}   {_warning}   {(RightIndicatorLit ? ">" : " ")}";
        _rpmBar.Value = _rpm;
        _fuelBar.Value = Math.Clamp(condition.FuelLiters, 0, _setup.FuelCapacityLiters);
        _instruments.RenderTargetUpdateMode = SubViewport.UpdateMode.Once;
        _automationState["speed_mph"] = _speedMph;
        _automationState["gear"] = _gear;
        _automationState["rpm"] = _rpm;
        _automationState["fuel_liters"] = condition.FuelLiters;
        _automationState["fuel_capacity_liters"] = _setup.FuelCapacityLiters;
        _automationState["warning"] = _warning;
    }

    private void BuildMirrors()
    {
        foreach (var (suffix, yaw) in new[] { ("Left", -0.16f), ("Right", 0.16f), ("Rear", 0.0f) })
        {
            var viewport = new SubViewport
            {
                Name = $"MirrorViewport_{suffix}", Size = suffix == "Rear" ? _setup.RearMirrorResolution : _setup.SideMirrorResolution,
                World3D = _vehicle.GetWorld3D(), OwnWorld3D = false,
                RenderTargetUpdateMode = SubViewport.UpdateMode.Disabled,
                Msaa3D = Viewport.Msaa.Disabled,
            };
            var camera = new Camera3D { Name = $"MirrorView_{suffix}", Current = true, Fov = 55, Near = 0.035f, Far = 180, CullMask = ((1u << 20) - 1) & ~MirrorSurfaceLayer };
            viewport.AddChild(camera);
            AddChild(viewport);
            RenderingServer.ViewportSetMeasureRenderTime(viewport.GetViewportRid(), true);
            var mirror = new Mirror(suffix, viewport, camera, _rig.ResolveAnchor($"MirrorCamera_{suffix}"), yaw);
            _mirrors.Add(mirror);
            BindScreen(_rig.ResolveAnchor($"Mirror_{suffix}"), viewport, mirror: true);
        }
    }

    private void BindScreen(Node3D anchor, SubViewport viewport, bool mirror)
    {
        var instances = Meshes(anchor).ToArray();
        if (instances.Length == 0) throw new InvalidOperationException($"Screen {anchor.Name} has no descendant display mesh.");
        var texture = viewport.GetTexture();
        var material = new StandardMaterial3D
        {
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
            AlbedoColor = Colors.White, AlbedoTexture = texture, Roughness = 1,
        };
        if (mirror) { material.Uv1Scale = new Vector3(-1, 1, 1); material.Uv1Offset = new Vector3(1, 0, 0); }
        _ownedMaterials.Add(material);
        foreach (var instance in instances)
        {
            instance.MaterialOverride = material;
            if (mirror) instance.Layers = MirrorSurfaceLayer;
        }
    }

    private void UpdateMirrors()
    {
        var active = MirrorsEnabled && _vehicle.CurrentCameraMode == "cockpit";
        for (var index = 0; index < _mirrors.Count; index++)
        {
            var mirror = _mirrors[index];
            if (active && !mirror.Active)
                mirror.NextUpdateSeconds = _elapsed + index / (_mirrors.Count * _setup.MirrorRefreshHz);
            mirror.Active = active;
            if (!active)
            {
                mirror.Viewport.RenderTargetUpdateMode = SubViewport.UpdateMode.Disabled;
                mirror.PendingUpdate = false;
                continue;
            }
            if (mirror.PendingUpdate || _elapsed + 0.000001 < mirror.NextUpdateSeconds) continue;
            mirror.Camera.GlobalTransform = mirror.Anchor.GetGlobalTransformInterpolated() *
                new Transform3D(new Basis(Vector3.Up, Mathf.Pi + mirror.Yaw) * new Basis(Vector3.Right, -0.03f), Vector3.Zero);
            mirror.Viewport.RenderTargetUpdateMode = SubViewport.UpdateMode.Once;
            mirror.RequestedAtSeconds = _elapsed;
            mirror.RequestedAtTicksUsec = Time.GetTicksUsec();
            mirror.RequestedAtFrame = Engine.GetProcessFrames();
            mirror.RequestCount++;
            mirror.PendingUpdate = true;
            mirror.NextUpdateSeconds = _elapsed + 1.0 / _setup.MirrorRefreshHz;
        }
    }

    private void OnFramePostDraw()
    {
        // Requested updates are not completed images. Dummy/headless rendering
        // cannot supply visual freshness evidence, even when this signal fires.
        if (DisplayServer.GetName() == "headless") return;
        foreach (var mirror in _mirrors)
        {
            // SubViewport caches the requested mode in Godot 4.7; its getter
            // does not reflect RenderingServer consuming UPDATE_ONCE. This
            // post-draw barrier completes the scheduled active viewport, while
            // the native pixel test independently verifies changing images.
            if (!mirror.PendingUpdate || !mirror.Active || !mirror.Viewport.IsInsideTree()) continue;
            mirror.Viewport.RenderTargetUpdateMode = SubViewport.UpdateMode.Disabled;
            mirror.PendingUpdate = false;
            mirror.LastUpdateSeconds = mirror.RequestedAtSeconds;
            mirror.LastUpdateFrame = Engine.GetProcessFrames();
            mirror.LastUpdateTicksUsec = Time.GetTicksUsec();
            mirror.LastImageSampleTicksUsec = mirror.RequestedAtTicksUsec;
            mirror.UpdateCount++;
        }
    }

    /// <summary>Allocation-free lamp readback for bounded native benchmark sampling.</summary>
    public VehicleDrivingIllumination CaptureDrivingIllumination()
    {
        var headMaterials = 0;
        var headEmitting = 0;
        var tailMaterials = 0;
        var tailEmitting = 0;
        var beams = 0;
        var visibleBeams = 0;
        var shadowedBeams = 0;
        var visibleBeamEnergy = 0f;
        foreach (var (name, lamp) in _lamps)
        {
            var head = name.StartsWith("Light_Head", StringComparison.Ordinal);
            if (!head && !name.StartsWith("Light_Tail", StringComparison.Ordinal)) continue;
            foreach (var material in lamp.Materials)
            {
                var emitting = material.EmissionEnabled && material.EmissionEnergyMultiplier > 0 &&
                    material.Emission.R + material.Emission.G + material.Emission.B > 0;
                if (head) { headMaterials++; if (emitting) headEmitting++; }
                else { tailMaterials++; if (emitting) tailEmitting++; }
            }
            if (head && lamp.Light is { } light)
            {
                beams++;
                if (light.ShadowEnabled) shadowedBeams++;
                if (light.IsVisibleInTree() && light.LightEnergy > 0)
                {
                    visibleBeams++;
                    visibleBeamEnergy += light.LightEnergy;
                }
            }
        }
        return new VehicleDrivingIllumination(HeadlightsOn, headMaterials, headEmitting,
            tailMaterials, tailEmitting, beams, visibleBeams, shadowedBeams, visibleBeamEnergy);
    }

    public object CaptureSnapshot() => new
    {
        headlights = HeadlightsOn, headlamp_mode = HeadlampMode, brakes = BrakeLightsOn, reverse = ReverseLightsOn,
        indicator_direction = IndicatorDirection, hazards = HazardsOn, left_lit = LeftIndicatorLit, right_lit = RightIndicatorLit,
        wipers = WipersOn, wiper_parking = _wiperParking,
        joints = _joints.ToDictionary(pair => pair.Key, pair => new
        {
            angle_deg = pair.Value.AngleDegrees, target = pair.Value.Target,
            basis = BasisRows(_rig.ResolveAnchor(pair.Key).Basis),
            mesh_descendants = Meshes(_rig.ResolveAnchor(pair.Key)).Count(),
        }),
        steering_wheel_deg = _steeringWheelAngle, accelerator_deg = _acceleratorAngle, brake_pedal_deg = _brakeAngle,
        speed_mph = _speedMph, gear = _gear, rpm = _rpm, fuel_liters = _vehicle.Condition.FuelLiters,
        fuel_capacity_liters = _setup.FuelCapacityLiters, warning = _warning,
        display = new { speed = _speedLabel.Text, gear = _gearLabel.Text, rpm = _rpmLabel.Text, fuel = _fuelLabel.Text, warning = _warningLabel.Text, rpm_bar = _rpmBar.Value, fuel_bar = _fuelBar.Value },
        lamps = _lamps.ToDictionary(pair => pair.Key, pair => new
        {
            lit = pair.Value.Lit, material_count = pair.Value.Materials.Count,
            material_emission = pair.Value.Materials.Select(material => material.EmissionEnergyMultiplier).ToArray(),
            emission = pair.Value.Lit ? pair.Value.Energy : 0,
            light_visible = pair.Value.Light?.Visible,
            light = pair.Value.Light is { } light ? new
            {
                type = light.GetClass().ToString(), energy = light.LightEnergy, shadows = light.ShadowEnabled,
                basis = BasisRows(light.Basis),
                range_m = light is SpotLight3D spot ? spot.SpotRange : light is OmniLight3D omni ? omni.OmniRange : (float?)null,
                angle_degrees = light is SpotLight3D cone ? cone.SpotAngle : (float?)null,
            } : null,
            visible_emitters = Meshes(_rig.ResolveAnchor(pair.Key)).Where(mesh => mesh.IsVisibleInTree()).Select(mesh => mesh.Name.ToString()).ToArray(),
        }),
        mirrors = _mirrors.Select(mirror => new
        {
            name = mirror.Name, active = mirror.Active, size = new[] { mirror.Viewport.Size.X, mirror.Viewport.Size.Y },
            last_update_frame = mirror.LastUpdateFrame, update_count = mirror.UpdateCount,
            requested_frame = mirror.RequestedAtFrame, request_count = mirror.RequestCount, pending_update = mirror.PendingUpdate,
            age_ms = mirror.UpdateCount > 0 ? (_elapsed - mirror.LastUpdateSeconds) * 1000 : (double?)null,
            wall_age_ms = mirror.UpdateCount > 0 ? (Time.GetTicksUsec() - mirror.LastUpdateTicksUsec) / 1000.0 : (double?)null,
            wall_image_age_ms = mirror.UpdateCount > 0 ? (Time.GetTicksUsec() - mirror.LastImageSampleTicksUsec) / 1000.0 : (double?)null,
            camera_position = new[] { mirror.Camera.GlobalPosition.X, mirror.Camera.GlobalPosition.Y, mirror.Camera.GlobalPosition.Z },
            camera_basis = BasisRows(mirror.Camera.GlobalBasis),
            anchor_position = new[] { mirror.Anchor.GlobalPosition.X, mirror.Anchor.GlobalPosition.Y, mirror.Anchor.GlobalPosition.Z },
            anchor_basis = BasisRows(mirror.Anchor.GlobalBasis),
            draw_calls = mirror.Viewport.GetRenderInfo(Viewport.RenderInfoType.Visible, Viewport.RenderInfo.DrawCallsInFrame),
            primitives = mirror.Viewport.GetRenderInfo(Viewport.RenderInfoType.Visible, Viewport.RenderInfo.PrimitivesInFrame),
            gpu_ms = RenderingServer.ViewportGetMeasuredRenderTimeGpu(mirror.Viewport.GetViewportRid()),
            cpu_ms = RenderingServer.ViewportGetMeasuredRenderTimeCpu(mirror.Viewport.GetViewportRid()),
        }).ToArray(),
    };

    private static float[][] BasisRows(Basis value) =>
        [[value.X.X, value.X.Y, value.X.Z], [value.Y.X, value.Y.Y, value.Y.Z], [value.Z.X, value.Z.Y, value.Z.Z]];

    public override void _ExitTree()
    {
        RenderingServer.FramePostDraw -= OnFramePostDraw;
        foreach (var material in _ownedMaterials) material.Dispose();
        _ownedMaterials.Clear();
        _lampMaterialCache.Clear();
        _automationState.Dispose();
    }

    private static IEnumerable<MeshInstance3D> Meshes(Node root)
    {
        if (root is MeshInstance3D mesh) yield return mesh;
        foreach (var child in root.GetChildren()) foreach (var descendant in Meshes(child)) yield return descendant;
    }

    private sealed class Joint(Node3D node, Basis rest, Vector3 axis, float maximumDegrees, bool parentAxis)
    {
        public float Value;
        public float Target;
        public float AngleDegrees { get; private set; }
        public float MaximumDegrees { get; } = maximumDegrees;
        public void Apply(float degrees)
        {
            AngleDegrees = degrees;
            var turn = new Basis(axis, Mathf.DegToRad(degrees));
            node.Basis = parentAxis ? turn * rest : rest * turn;
        }
    }

    private sealed class Lamp(List<StandardMaterial3D> materials, float energy)
    {
        public List<StandardMaterial3D> Materials { get; } = materials;
        public float Energy { get; } = energy;
        public Light3D? Light { get; set; }
        public bool Lit { get; private set; }
        private bool _initialized;
        public void Apply(bool lit)
        {
            if (_initialized && Lit == lit) return;
            _initialized = true;
            Lit = lit;
            foreach (var material in Materials) material.EmissionEnergyMultiplier = lit ? Energy : 0;
            if (Light is not null) Light.Visible = lit;
        }
    }

    public sealed class Mirror(string name, SubViewport viewport, Camera3D camera, Node3D anchor, float yaw)
    {
        public string Name { get; } = name;
        public SubViewport Viewport { get; } = viewport;
        public Camera3D Camera { get; } = camera;
        public Node3D Anchor { get; } = anchor;
        public float Yaw { get; } = yaw;
        public bool Active { get; internal set; }
        public bool PendingUpdate { get; internal set; }
        public double NextUpdateSeconds { get; internal set; }
        public double RequestedAtSeconds { get; internal set; }
        public ulong RequestedAtTicksUsec { get; internal set; }
        public ulong RequestedAtFrame { get; internal set; }
        public int RequestCount { get; internal set; }
        public double LastUpdateSeconds { get; internal set; } = double.NegativeInfinity;
        public ulong LastUpdateFrame { get; internal set; }
        public ulong LastUpdateTicksUsec { get; internal set; }
        public ulong LastImageSampleTicksUsec { get; internal set; }
        public int UpdateCount { get; internal set; }
    }
}

public readonly record struct VehicleDrivingIllumination(bool HeadlightsOn,
    int HeadMaterials, int HeadEmittingMaterials, int TailMaterials, int TailEmittingMaterials,
    int Beams, int VisibleBeams, int ShadowedBeams, float VisibleBeamEnergy)
{
    public bool Matches(bool expectedOn) => HeadlightsOn == expectedOn && HeadMaterials > 0 && TailMaterials > 0 &&
        Beams == 2 && (expectedOn
            ? HeadEmittingMaterials == HeadMaterials && TailEmittingMaterials == TailMaterials && VisibleBeams == Beams && VisibleBeamEnergy > 0
            : HeadEmittingMaterials == 0 && TailEmittingMaterials == 0 && VisibleBeams == 0 && VisibleBeamEnergy == 0);
}
