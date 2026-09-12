using System.Security.Cryptography;
using System.Text.Json;
using Cannonball.Core.Runs;
using Cannonball.Game.Input;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Cannonball.Game.World.Environments;
using Godot;

namespace Cannonball.Game.Automation;

/// <summary>Posed inspection fixtures. Never substitutes for the unfrozen driving scenario.</summary>
public sealed class EnduranceSedanPresentationScenario : IDisposable
{
    public static readonly string[] BaseStages =
    [
        "contract", "view-front", "view-rear", "view-left", "view-right", "view-top", "view-underside",
        "view-front-three-quarter", "view-rear-three-quarter", "turntable", "cockpit", "view-footwell", "view-rear-cabin",
        "inspection-keyboard", "inspection-controller",
        "open-Door_FL", "close-Door_FL", "open-Door_FR", "close-Door_FR",
        "open-Door_RL", "close-Door_RL", "open-Door_RR", "close-Door_RR",
        "open-Hood_Hinge", "close-Hood_Hinge", "open-Trunk_Hinge", "close-Trunk_Hinge",
        "lights-off", "headlights", "brake-lights", "reverse-lights", "left-indicator", "right-indicator", "hazards",
        "wipers-sweep", "wipers-park", "steering-small-right", "controls-left", "controls-right",
        "instruments-forward", "instruments-reverse", "instruments-low-fuel", "instruments-damage",
        "instruments-cooling", "instruments-tires", "instruments-panel-open", "instruments-park-brake", "mirrors-configuration",
        "lod-near", "lod-middle", "lod-far", "lod-return",
    ];
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private static readonly DriveInputState Neutral = new(0, 0, 0, 0, 0, false, false);
    private static readonly Dictionary<string, string> WarningStages = new(StringComparer.Ordinal)
    {
        ["instruments-low-fuel"] = "LOW FUEL", ["instruments-damage"] = "DAMAGE",
        ["instruments-cooling"] = "COOLING", ["instruments-tires"] = "TIRES",
        ["instruments-panel-open"] = "PANEL OPEN", ["instruments-park-brake"] = "PARK BRAKE",
    };
    private readonly Node _parent;
    private readonly CannonballVehicle _vehicle;
    private readonly WorldStreamer _streamer;
    private readonly VehicleVisualRig _rig;
    private readonly EnduranceSedanPresentation _presentation;
    private readonly VehicleCondition _originalCondition;
    private readonly Camera3D _camera = new() { Name = "SedanInspectionCamera", Fov = 45, Near = 0.025f, Far = 200 };
    private readonly Node3D _fixture = new() { Name = "SedanPresentationFixture" };
    private readonly List<MeshInstance3D> _mirrorTargets = [];
    private readonly Dictionary<string, int> _mirrorObservedUpdates = new(StringComparer.Ordinal);
    private readonly Dictionary<string, int> _doorMirrorUpdateStart = new(StringComparer.Ordinal);
    private readonly Dictionary<string, List<Vector2>> _mirrorCentroids = new(StringComparer.Ordinal);
    private readonly List<object> _mirrorSamples = [];
    private readonly Dictionary<string, object> _displayUvMeasurements = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Vector3[]> _displayUvCorners = new(StringComparer.Ordinal);
    private readonly Dictionary<string, object> _warningVisibilities = new(StringComparer.Ordinal);
    private readonly Dictionary<string, int> _mirrorImageSamples = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Basis> _rest = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Vector3> _pedalCenters = new(StringComparer.Ordinal);
    private readonly List<object> _results = [];
    private readonly List<object> _captures = [];
    private readonly StreamWriter _frames;
    private readonly StreamWriter _mirrorFrameLog;
    private readonly string _directory;
    private readonly bool _rendered;
    private readonly string[] _expected;
    private readonly string? _diagnosticProbe;
    private readonly float? _diagnosticCameraSourceY;
    private readonly LightingPreset _mirrorLighting = LightingPreset.Day;
    private readonly Dictionary<Node3D, Transform3D> _originalMirrorAnchorTransforms = [];
    private readonly MeshInstance3D _floor;
    private Task? _captureTask;
    private Exception? _renderException;
    private int _stage;
    private long _frameSamples;
    private double _stageTime;
    private bool _begun;
    private bool _captured;
    private bool _leftSeenOn;
    private bool _rightSeenOn;
    private bool _blinkSeenOff;
    private bool _hazardsSeenTogether;
    private bool _hazardsMixedAfterLatency;
    private ulong _stageStartRenderFrame;
    private float _minimumWiperLeft;
    private float _minimumWiperRight;
    private bool _disposed;

    public EnduranceSedanPresentationScenario(Node parent, CannonballVehicle vehicle, WorldStreamer streamer, string directory)
    {
        _parent = parent;
        _vehicle = vehicle;
        _streamer = streamer;
        _rig = vehicle.VisualRig ?? throw new InvalidOperationException("Presentation requires the actual sedan wrapper.");
        _presentation = _rig.Presentation ?? throw new InvalidOperationException("Production presentation is missing; --sedan-blockout cannot pass this suite.");
        _originalCondition = vehicle.Condition;
        _directory = Path.GetFullPath(directory);
        _rendered = OS.GetCmdlineUserArgs().Contains("--sedan-captures", StringComparer.Ordinal);
        if (_rendered && DisplayServer.GetName() == "headless") throw new InvalidOperationException("Rendered mirror/capture proof requires a native renderer.");
        var probeArguments = OS.GetCmdlineUserArgs().Where(argument => argument.StartsWith("--sedan-presentation-probe=", StringComparison.Ordinal)).ToArray();
        if (probeArguments.Length > 1) throw new InvalidOperationException("Only one sedan presentation diagnostic probe may be selected.");
        _diagnosticProbe = probeArguments.Length == 1 ? probeArguments[0]["--sedan-presentation-probe=".Length..] : null;
        if (_diagnosticProbe is not null && (_diagnosticProbe != "mirrors" || !_rendered))
            throw new InvalidOperationException("--sedan-presentation-probe=mirrors requires native --sedan-captures and is not a full acceptance run.");
        var lightingArguments = OS.GetCmdlineUserArgs().Where(argument => argument.StartsWith("--sedan-mirror-lighting=", StringComparison.Ordinal)).ToArray();
        if (lightingArguments.Length > 1) throw new InvalidOperationException("Only one mirror diagnostic lighting preset may be selected.");
        if (lightingArguments.Length == 1)
        {
            var lighting = lightingArguments[0]["--sedan-mirror-lighting=".Length..];
            if (_diagnosticProbe != "mirrors" || lighting is not ("daylight" or "night"))
                throw new InvalidOperationException("--sedan-mirror-lighting=daylight|night requires the native mirror-only probe.");
            _mirrorLighting = lighting == "night" ? LightingPreset.Night : LightingPreset.Day;
        }
        var cameraArguments = OS.GetCmdlineUserArgs().Where(argument => argument.StartsWith("--sedan-mirror-camera-source-y=", StringComparison.Ordinal)).ToArray();
        if (cameraArguments.Length > 1) throw new InvalidOperationException("Only one diagnostic mirror-camera source Y may be selected.");
        if (cameraArguments.Length == 1)
        {
            if (_diagnosticProbe != "mirrors" || !float.TryParse(cameraArguments[0]["--sedan-mirror-camera-source-y=".Length..],
                    System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var sourceY) ||
                !float.IsFinite(sourceY) || sourceY is < 0.4f or > 0.7f)
                throw new InvalidOperationException("A diagnostic mirror-camera Y in 0.4..0.7 m requires the native mirror-only probe.");
            _diagnosticCameraSourceY = sourceY;
        }
        _expected = _diagnosticProbe == "mirrors" ? ["mirrors-configuration", "mirrors-live", "mirrors-door-follow", "mirrors-disabled"] :
            _rendered ? [.. BaseStages, "mirrors-live", "mirrors-door-follow", "mirrors-disabled"] : BaseStages;
        Directory.CreateDirectory(_directory);
        _frames = new StreamWriter(Path.Combine(_directory, "presentation-frames.jsonl"), false);
        _mirrorFrameLog = new StreamWriter(Path.Combine(_directory, "mirror-samples.jsonl"), false) { AutoFlush = true };
        parent.AddChild(_fixture);
        parent.AddChild(_camera);
        _floor = Box("InspectionFloor", new Vector3(0, -0.06f, 0), new Vector3(240, 0.12f, 240), new Color("7c858c"));
        _fixture.AddChild(_floor);
        using (var floorShape = new BoxShape3D { Size = new Vector3(240, 0.12f, 240) })
        {
            var floorBody = new StaticBody3D { Name = "InspectionFloorContact", Position = _floor.Position, CollisionLayer = 1, CollisionMask = 2 };
            floorBody.AddChild(new CollisionShape3D { Shape = floorShape });
            _fixture.AddChild(floorBody);
        }
        for (var i = 0; i < 3; i++)
        {
            var target = Box("MirrorTarget" + i, Vector3.Zero, new Vector3(0.55f, 0.7f, 0.2f),
                i == 0 ? new Color(1, 0, 1) : i == 1 ? new Color(0, 1, 0) : new Color(0, 1, 1), unshaded: true);
            target.Visible = false;
            _fixture.AddChild(target);
            _mirrorTargets.Add(target);
        }
        _streamer.ProcessMode = Node.ProcessModeEnum.Disabled;
        _streamer.Visible = false;
        _vehicle.PlaceForReview(Vector3.Zero, Vector3.Forward);
        if (_diagnosticCameraSourceY is { } cameraSourceY)
        {
            var frame = _rig.ResolveAnchor("AssetRoot").GlobalTransform;
            foreach (var mirror in _presentation.Mirrors.Where(mirror => mirror.Name != "Rear"))
            {
                _originalMirrorAnchorTransforms[mirror.Anchor] = mirror.Anchor.Transform;
                var point = frame.AffineInverse() * mirror.Anchor.GlobalPosition;
                point.Z = -cameraSourceY;
                mirror.Anchor.GlobalPosition = frame * point;
            }
        }
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = Neutral;
        foreach (var name in EnduranceSedanPresentation.OpeningNames.Concat(new[] { "SteeringWheel_Pivot", "Pedal_Accelerator", "Pedal_Brake", "Wiper_L", "Wiper_R" }))
            _rest[name] = _rig.ResolveAnchor(name).Basis;
        foreach (var name in new[] { "Pedal_Accelerator", "Pedal_Brake" })
        {
            var pad = _rig.ResolveAnchor("LOD0_" + name + "Pad") as MeshInstance3D ?? throw new InvalidOperationException("Pedal pad mesh is missing.");
            _pedalCenters[name] = _rig.ResolveAnchor(name).GlobalTransform.AffineInverse() * (pad.GlobalTransform * pad.GetAabb().GetCenter());
        }
        Lighting(_mirrorLighting);
        CameraAt(new Vector3(4.6f, 2.6f, -6.4f));
        if (_rendered) RenderingServer.FramePostDraw += ObserveRenderedFrame;
        GD.Print($"CANNONBALL_SEDAN_PRESENTATION_BEGIN stages={_expected.Length} posed=true rendered={_rendered.ToString().ToLowerInvariant()} diagnostic={_diagnosticProbe ?? "none"}");
    }

    public bool Complete { get; private set; }
    public string CurrentStage => _stage < _expected.Length ? _expected[_stage] : "complete";

    public void Advance(double delta)
    {
        if (Complete || _disposed) return;
        if (_renderException is not null) throw new InvalidOperationException("Rendered presentation verification failed.", _renderException);
        if (_captureTask is { IsFaulted: true }) _captureTask.GetAwaiter().GetResult();
        if (!_begun) { BeginStage(); _begun = true; }
        _stageTime += delta;
        if (CurrentStage == "turntable") CameraAt(new Vector3(Mathf.Sin((float)(_stageTime / 8 * Mathf.Tau)) * 6.8f, 2.5f, -Mathf.Cos((float)(_stageTime / 8 * Mathf.Tau)) * 6.8f));
        _vehicle.Condition = CurrentStage switch
        {
            "instruments-low-fuel" => _originalCondition with { FuelLiters = 10 },
            "instruments-damage" => _originalCondition with { Damage = 0.2 },
            "instruments-cooling" => _originalCondition with { CoolingCondition = 0.2 },
            "instruments-tires" => _originalCondition with { TireCondition = 0.2 },
            _ => _vehicle.Condition,
        };
        if (CurrentStage == "mirrors-live")
        {
            for (var i = 0; i < _mirrorTargets.Count; i++)
            {
                var mirror = _presentation.Mirrors[i];
                _mirrorTargets[i].GlobalPosition = mirror.Anchor.GlobalPosition + new Vector3(i == 0 ? -1.0f : i == 1 ? 1.0f : 0, 0.0f, 7.0f) +
                    Vector3.Right * Mathf.Sin((float)_stageTime * 1.4f) * 0.6f;
            }
        }
        // Main advances this fixture before the child's presenter process.
        // The first sample can therefore still belong to the previous input.
        // Apply the same explicit bounded output latency to every blink test.
        if (Engine.GetProcessFrames() - _stageStartRenderFrame > 2)
        {
            _leftSeenOn |= _presentation.LeftIndicatorLit;
            _rightSeenOn |= _presentation.RightIndicatorLit;
            _blinkSeenOff |= !_presentation.LeftIndicatorLit && !_presentation.RightIndicatorLit;
            if (CurrentStage == "hazards")
            {
                _hazardsSeenTogether |= _presentation.LeftIndicatorLit && _presentation.RightIndicatorLit;
                _hazardsMixedAfterLatency |= _presentation.LeftIndicatorLit != _presentation.RightIndicatorLit;
            }
        }
        var presentationState = _presentation.CaptureSnapshot();
        using var snapshot = JsonDocument.Parse(JsonSerializer.Serialize(presentationState));
        _minimumWiperLeft = Math.Min(_minimumWiperLeft, (float)snapshot.RootElement.GetProperty("joints").GetProperty("Wiper_L").GetProperty("angle_deg").GetDouble());
        _minimumWiperRight = Math.Min(_minimumWiperRight, (float)snapshot.RootElement.GetProperty("joints").GetProperty("Wiper_R").GetProperty("angle_deg").GetDouble());
        _frames.WriteLine(JsonSerializer.Serialize(new
        {
            stage = CurrentStage, elapsed_s = _stageTime, render_frame = Engine.GetProcessFrames(), physics_frame = Engine.GetPhysicsFrames(),
            fixture = "posed presentation; conditioned input/state fixture", frozen = _vehicle.Freeze,
            input = _vehicle.LastDriveInput, signed_speed_mps = _vehicle.SignedLongitudinalSpeedMetersPerSecond,
            camera = _vehicle.GetViewport().GetCamera3D().Name.ToString(), lod = _rig.ActiveLod,
            lighting = SkyLighting.CurrentPreset?.ToString(),
            source_geometry_visible = _streamer.Visible, state = presentationState,
            stance = CaptureStance(),
        }));
        _frameSamples++;
        if (_stageTime < Duration()) return;
        ValidateStage(snapshot.RootElement);
        if (_rendered && !_captured)
        {
            _captureTask ??= CaptureAsync(CurrentStage);
            return;
        }
        _results.Add(new { stage = CurrentStage, status = "passed", duration_s = _stageTime, posed = true, rendered = _rendered, state = _presentation.CaptureSnapshot() });
        GD.Print($"CANNONBALL_SEDAN_PRESENTATION_STAGE_OK stage={CurrentStage} posed=true");
        _frames.Flush();
        _stage++;
        _stageTime = 0;
        _begun = _captured = false;
        _captureTask = null;
        if (_stage == _expected.Length) Finish();
    }

    private double Duration() => CurrentStage switch
    {
        "turntable" => 8, "mirrors-live" => 6, "wipers-sweep" => 4, "wipers-park" => 1.6,
        "left-indicator" or "right-indicator" or "hazards" => 1.6,
        _ => 1.1,
    };

    private void BeginStage()
    {
        _vehicle.InspectionPanel.Close();
        _vehicle.LinearVelocity = Vector3.Zero;
        _vehicle.AutomationInputOverride = Neutral;
        _vehicle.Condition = _originalCondition;
        _floor.Visible = CurrentStage != "view-underside";
        _leftSeenOn = _rightSeenOn = _blinkSeenOff = false;
        _hazardsSeenTogether = _hazardsMixedAfterLatency = false;
        _stageStartRenderFrame = Engine.GetProcessFrames();
        _minimumWiperLeft = _minimumWiperRight = 0;
        if (CurrentStage.StartsWith("open-", StringComparison.Ordinal) || CurrentStage.StartsWith("close-", StringComparison.Ordinal))
        {
            var name = CurrentStage[(CurrentStage.IndexOf('-') + 1)..];
            _vehicle.InspectionPanel.Open();
            var control = Descendants(_vehicle.InspectionPanel).OfType<CheckButton>().Single(node => node.GetMeta("automation_id", "").AsString() == "vehicle.opening." + name.ToLowerInvariant().Replace('_', '-'));
            control.ButtonPressed = CurrentStage.StartsWith("open-", StringComparison.Ordinal);
            _vehicle.InspectionPanel.Close();
            CameraAt(name is "Hood_Hinge" ? new Vector3(3.6f, 2.5f, -4.6f) : name is "Trunk_Hinge" ? new Vector3(3.6f, 2.3f, 4.6f) : new Vector3(name.EndsWith("L", StringComparison.Ordinal) ? -4.8f : 4.8f, 1.9f, -1.2f));
        }
        switch (CurrentStage)
        {
            case "view-front": CameraAt(new Vector3(0, 1.3f, -7)); break;
            case "view-rear": CameraAt(new Vector3(0, 1.3f, 7)); break;
            case "view-left": CameraAt(new Vector3(-7, 1.2f, 0)); break;
            case "view-right": CameraAt(new Vector3(7, 1.2f, 0)); break;
            case "view-top": CameraAt(new Vector3(0.001f, 9, 0)); break;
            case "view-underside": CameraAt(new Vector3(0.001f, -6, 0)); break;
            case "view-front-three-quarter": CameraAt(new Vector3(4.6f, 2.6f, -6.4f)); break;
            case "view-rear-three-quarter": CameraAt(new Vector3(-4.6f, 2.6f, 6.4f)); break;
            case "cockpit": Cockpit(); break;
            case "view-footwell": CameraAt(new Vector3(-0.43f, 0.67f, 0.20f), new Vector3(-0.40f, 0.33f, -0.70f)); break;
            case "view-rear-cabin": CameraAt(new Vector3(0, 1.12f, -0.03f), new Vector3(0, 0.92f, 1.15f)); break;
            case "inspection-keyboard":
                CameraAt(new Vector3(4.6f, 2.6f, -6.4f));
                using (var key = new InputEventKey { Keycode = Key.F2, PhysicalKeycode = Key.F2, Pressed = true }) Godot.Input.ParseInputEvent(key);
                using (var key = new InputEventKey { Keycode = Key.F2, PhysicalKeycode = Key.F2, Pressed = false }) Godot.Input.ParseInputEvent(key);
                break;
            case "inspection-controller":
                using (var button = new InputEventJoypadButton { Device = 0, ButtonIndex = JoyButton.RightShoulder, Pressed = true }) Godot.Input.ParseInputEvent(button);
                using (var button = new InputEventJoypadButton { Device = 0, ButtonIndex = JoyButton.RightShoulder, Pressed = false }) Godot.Input.ParseInputEvent(button);
                break;
            case "lights-off": Lighting(LightingPreset.Night); _presentation.SetHeadlampMode(2); CameraAt(new Vector3(4.6f, 2.3f, -6.4f)); break;
            case "headlights": _presentation.SetHeadlampMode(1); break;
            case "brake-lights": CameraAt(new Vector3(3.5f, 1.9f, 6)); _vehicle.AutomationInputOverride = Neutral with { Brake = 0.8f }; break;
            case "reverse-lights": _vehicle.AutomationInputOverride = Neutral with { Reverse = 0.6f }; break;
            case "left-indicator": _presentation.SetIndicator(-1); break;
            case "right-indicator": _presentation.SetIndicator(1); break;
            case "hazards": _presentation.SetHazards(true); break;
            case "wipers-sweep": _presentation.SetHazards(false); _presentation.SetIndicator(1); Lighting(LightingPreset.Overcast); CameraAt(new Vector3(-3.4f, 2.7f, -3.5f)); _presentation.SetWipers(true); break;
            case "wipers-park": _presentation.SetWipers(false); break;
            case "steering-small-right": Cockpit(); _vehicle.AutomationInputOverride = Neutral with { Steering = 0.02f }; break;
            case "controls-left": Cockpit(); _vehicle.AutomationInputOverride = Neutral with { Throttle = 0.7f, Steering = -0.75f }; break;
            case "controls-right": _vehicle.AutomationInputOverride = Neutral with { Brake = 0.6f, Steering = 0.75f }; break;
            case "instruments-forward": Cockpit(); _vehicle.LinearVelocity = Vector3.Forward * 32.18688f; _vehicle.AutomationInputOverride = Neutral with { Throttle = 0.5f }; break;
            case "instruments-reverse": _vehicle.LinearVelocity = Vector3.Back * 3; _vehicle.AutomationInputOverride = Neutral with { Reverse = 0.4f }; break;
            case "instruments-low-fuel": _vehicle.Condition = _originalCondition with { FuelLiters = 10 }; break;
            case "instruments-panel-open": _presentation.SetOpening("Door_FL", true); break;
            case "instruments-park-brake": _presentation.SetOpening("Door_FL", false); _vehicle.AutomationInputOverride = Neutral with { Handbrake = 1 }; break;
            case "mirrors-configuration": Cockpit(); Lighting(_mirrorLighting); break;
            case "lod-near": CameraAt(new Vector3(0, 1.3f, 12)); break;
            case "lod-middle": CameraAt(new Vector3(0, 1.3f, 40)); break;
            case "lod-far": CameraAt(new Vector3(0, 1.3f, 80)); break;
            case "lod-return": CameraAt(new Vector3(0, 1.3f, 12)); break;
            case "mirrors-live": Cockpit(); Lighting(_mirrorLighting); foreach (var target in _mirrorTargets) target.Visible = true; break;
            case "mirrors-door-follow":
                foreach (var target in _mirrorTargets) target.Visible = false;
                foreach (var mirror in _presentation.Mirrors) _doorMirrorUpdateStart[mirror.Name] = mirror.UpdateCount;
                _presentation.SetOpening("Door_FL", true);
                _presentation.SetOpening("Door_FR", true);
                Cockpit();
                break;
            case "mirrors-disabled":
                _presentation.SetOpening("Door_FL", false);
                _presentation.SetOpening("Door_FR", false);
                CameraAt(new Vector3(4.6f, 2.6f, -6.4f));
                foreach (var target in _mirrorTargets) target.Visible = false;
                break;
        }
    }

    private void ValidateStage(JsonElement state)
    {
        Require(_vehicle.Freeze, "posed suite unexpectedly enabled rigid-body driving");
        ValidateRearSpill();
        if (CurrentStage.StartsWith("lod-", StringComparison.Ordinal)) ValidateVisibleLamps(state);
        if (CurrentStage.StartsWith("open-", StringComparison.Ordinal) || CurrentStage.StartsWith("close-", StringComparison.Ordinal))
        {
            var name = CurrentStage[(CurrentStage.IndexOf('-') + 1)..];
            var open = CurrentStage.StartsWith("open-", StringComparison.Ordinal);
            var index = Array.IndexOf(EnduranceSedanPresentation.OpeningNames, name);
            var expectedAngle = open ? _presentation.Setup.OpeningAnglesDegrees[index] : 0;
            Require(Math.Abs(_presentation.OpeningAngleDegrees(name) - expectedAngle) < 0.01f, "opening endpoint mismatch");
            var expectedBasis = new Basis(index < 4 ? Vector3.Up : Vector3.Right, Mathf.DegToRad(expectedAngle)) * _rest[name];
            Require(_rig.ResolveAnchor(name).Basis.IsEqualApprox(expectedBasis), "actual hinge basis differs from its source contract");
            Require(state.GetProperty("joints").GetProperty(name).GetProperty("mesh_descendants").GetInt32() > 0, "opening has no modeled assembly");
        }
        switch (CurrentStage)
        {
            case "contract":
                Require(_rig.ContractResolved && _presentation.Mirrors.Count == 3, "production contract incomplete");
                VerifyDisplayUv("Instrument_Cluster", _presentation.InstrumentViewport);
                foreach (var mirror in _presentation.Mirrors) VerifyDisplayUv("Mirror_" + mirror.Name, mirror.Viewport, mirror: true);
                break;
            case "inspection-keyboard":
            case "inspection-controller": Require(_vehicle.InspectionPanel.IsOpen && _vehicle.GetViewport().GuiGetFocusOwner() is not null, "input event did not open a focused inspection panel"); break;
            case "lights-off": Require(!state.GetProperty("headlights").GetBoolean(), "headlights did not switch off"); break;
            case "headlights": Require(state.GetProperty("headlights").GetBoolean(), "headlights did not switch on"); break;
            case "brake-lights": Require(state.GetProperty("brakes").GetBoolean(), "brake state did not light brakes"); break;
            case "reverse-lights": Require(state.GetProperty("reverse").GetBoolean(), "reverse state did not light reverse emitters"); break;
            case "left-indicator": Require(_leftSeenOn && !_rightSeenOn && _blinkSeenOff, "left indicator did not blink independently"); break;
            case "right-indicator": Require(_rightSeenOn && !_leftSeenOn && _blinkSeenOff, "right indicator did not blink independently"); break;
            case "hazards": Require(_hazardsSeenTogether && !_hazardsMixedAfterLatency && _blinkSeenOff, "hazards did not blink simultaneously after the two-frame latency allowance"); break;
            case "wipers-sweep": Require(_minimumWiperLeft < -77.5f && _minimumWiperRight < -73.5f, "wipers did not traverse their declared sweep"); break;
            case "wipers-park":
                Require(!state.GetProperty("wiper_parking").GetBoolean(), "wipers are still parking");
                foreach (var name in new[] { "Wiper_L", "Wiper_R" })
                    Require(Math.Abs(state.GetProperty("joints").GetProperty(name).GetProperty("angle_deg").GetDouble()) < 1 && _rig.ResolveAnchor(name).Basis.IsEqualApprox(_rest[name]), "wiper angle or actual rest basis did not return to park: " + name);
                break;
            case "steering-small-right":
                var column = _rig.ResolveAnchor("SteeringWheel_Pivot");
                var restTop = _rest["SteeringWheel_Pivot"] * (Vector3.Up * 0.18f);
                var movedTop = column.Basis * (Vector3.Up * 0.18f);
                var tireNose = _rig.ResolveAnchor("Suspension_FL").Basis * Vector3.Forward;
                Require(_vehicle.CurrentSteeringRadians is > 0 and < 0.03f && tireNose.X > 0 && movedTop.X - restTop.X > 0.01f,
                    "small right steering does not move both the actual tire nose and the top of the actual rim right");
                break;
            case "controls-left":
            case "controls-right":
                Require(Math.Abs(state.GetProperty("steering_wheel_deg").GetDouble() - Mathf.RadToDeg(_vehicle.CurrentSteeringRadians) * 14.5) < 0.01, "steering wheel does not follow the actual steering state");
                Require(Math.Abs(state.GetProperty("accelerator_deg").GetDouble() - _vehicle.LastDriveInput.Throttle * -18) < 0.01 && Math.Abs(state.GetProperty("brake_pedal_deg").GetDouble() - _vehicle.LastDriveInput.Brake * -12) < 0.01, "pedals do not follow control state");
                foreach (var name in new[] { "Pedal_Accelerator", "Pedal_Brake" })
                {
                    var amount = name == "Pedal_Accelerator" ? _vehicle.LastDriveInput.Throttle : _vehicle.LastDriveInput.Brake;
                    var maximum = name == "Pedal_Accelerator" ? -18 : -12;
                    var actual = _rig.ResolveAnchor(name).Basis;
                    Require(actual.IsEqualApprox(_rest[name] * new Basis(Vector3.Right, Mathf.DegToRad(maximum * amount))), "pedal actual basis does not match control input: " + name);
                    if (amount > 0.1f)
                        Require((actual * _pedalCenters[name]).Z < (_rest[name] * _pedalCenters[name]).Z - 0.005f, "actual pedal pad does not move forward under pressure: " + name);
                }
                break;
            case "instruments-forward": Require(state.GetProperty("display").GetProperty("speed").GetString() == "72" && state.GetProperty("gear").GetString() == "4" && state.GetProperty("rpm").GetDouble() is > 3850 and < 3900, "72mph fictional kinematic instrument fixture mismatch"); break;
            case "instruments-reverse": Require(state.GetProperty("gear").GetString() == "R", "reverse instrument fixture mismatch"); break;
            case "instruments-low-fuel": Require(state.GetProperty("warning").GetString() == "LOW FUEL" && state.GetProperty("display").GetProperty("fuel").GetString() == "10 L", "fuel/warning does not follow explicit vehicle condition"); break;
            case "mirrors-configuration":
                for (var mirrorIndex = 0; mirrorIndex < _presentation.Mirrors.Count; mirrorIndex++)
                {
                    var mirror = _presentation.Mirrors[mirrorIndex];
                    Require(mirror.Viewport.Size == (mirror.Name == "Rear" ? new Vector2I(384, 128) : new Vector2I(256, 128)) && (mirror.Camera.CullMask & EnduranceSedanPresentation.MirrorSurfaceLayer) == 0 && !mirror.Viewport.OwnWorld3D, "mirror size/world/nonrecursive configuration mismatch");
                    VerifyMirrorBinding(mirror);
                    if (_rendered && !_mirrorImageSamples.ContainsKey("hidden-" + mirror.Name))
                    {
                        using var image = mirror.Viewport.GetTexture().GetImage();
                        Require(image is not null && !image.IsEmpty(), "mirror hidden-target image is empty");
                        image!.Convert(Image.Format.Rgba8);
                        var pixels = MeasureTargetPixels(image, mirrorIndex);
                        var sample = new { mirror = mirror.Name, frame = Engine.GetProcessFrames(), scope = "targets-hidden-negative-control", pixels = pixels.Count, targets_visible = _mirrorTargets.Any(target => target.Visible) };
                        _mirrorSamples.Add(sample);
                        _mirrorFrameLog.WriteLine(JsonSerializer.Serialize(sample));
                        SaveImage(image, "mirror-" + mirror.Name + "-targets-hidden.png");
                        _mirrorImageSamples["hidden-" + mirror.Name] = 1;
                        Require(mirror.UpdateCount >= 3 && !_mirrorTargets.Any(target => target.Visible) && pixels.Count < 8,
                            "mirror detector found its target color in the hidden-target background: " + mirror.Name);
                    }
                }
                break;
            case "lod-near":
            case "lod-return": Require(_rig.ActiveLod == 0, "near distance did not select LOD0"); break;
            case "lod-middle": Require(_rig.ActiveLod == 1, "middle distance did not select LOD1"); break;
            case "lod-far": Require(_rig.ActiveLod == 2, "far distance did not select LOD2"); break;
            case "mirrors-live":
                foreach (var mirror in _presentation.Mirrors)
                    Require(_mirrorCentroids.TryGetValue(mirror.Name, out var points) && points.Count >= 10 && points.Max(point => point.X) - points.Min(point => point.X) >= 3, "live mirror has no independently observed moving target: " + mirror.Name);
                break;
            case "mirrors-door-follow":
                foreach (var mirror in _presentation.Mirrors.Where(mirror => mirror.Name != "Rear"))
                {
                    var doorName = mirror.Name == "Left" ? "Door_FL" : "Door_FR";
                    var door = _rig.ResolveAnchor(doorName);
                    Require(door.IsAncestorOf(mirror.Anchor) && door.IsAncestorOf(_rig.ResolveAnchor("Mirror_" + mirror.Name)), "side mirror or camera is not attached to its front door");
                    Require(Math.Abs(_presentation.OpeningAngleDegrees(doorName)) > 60, "front door did not open for mirror-follow check");
                    var expected = mirror.Anchor.GetGlobalTransformInterpolated() * new Transform3D(
                        new Basis(Vector3.Up, Mathf.Pi + mirror.Yaw) * new Basis(Vector3.Right, -0.03f), Vector3.Zero);
                    Require(mirror.Active && mirror.UpdateCount - _doorMirrorUpdateStart[mirror.Name] >= 8 &&
                        mirror.Camera.GlobalPosition.DistanceTo(expected.Origin) < 0.001f && mirror.Camera.GlobalBasis.IsEqualApprox(expected.Basis),
                        "actual mirror camera/render updates did not follow the opening door: " + mirror.Name);
                    VerifyMirrorBinding(mirror);
                }
                break;
            case "mirrors-disabled": Require(_presentation.Mirrors.All(mirror => !mirror.Active && !mirror.PendingUpdate), "mirrors continued outside cockpit"); break;
        }
        foreach (var lamp in state.GetProperty("lamps").EnumerateObject())
        {
            var lit = lamp.Value.GetProperty("lit").GetBoolean();
            Require(lamp.Value.GetProperty("material_emission").EnumerateArray().All(value => lit ? value.GetDouble() > 0 : value.GetDouble() == 0), "native lamp material does not match state: " + lamp.Name);
            var lightVisible = lamp.Value.GetProperty("light_visible");
            Require(lightVisible.ValueKind == JsonValueKind.Null || lightVisible.GetBoolean() == lit, "native light visibility does not match its emitter state: " + lamp.Name);
        }
        if (WarningStages.TryGetValue(CurrentStage, out var expectedWarning))
            Require(state.GetProperty("warning").GetString() == expectedWarning &&
                state.GetProperty("display").GetProperty("warning").GetString()!.Contains(expectedWarning, StringComparison.Ordinal),
                "warning does not follow explicit condition/input/opening state: " + expectedWarning);
    }

    private void ValidateRearSpill()
    {
        Require(!Descendants(_rig.ResolveAnchor("Light_Brake_Center")).OfType<Light3D>().Any(),
            "central brake lamp must not have an artificial interior spill light");
        foreach (var name in new[] { "Light_Brake_L", "Light_Brake_R", "Light_Reverse_L", "Light_Reverse_R" })
        {
            var lights = Descendants(_rig.ResolveAnchor(name)).OfType<Light3D>().ToArray();
            Require(lights.Length == 1 && lights[0] is SpotLight3D, "rear lamp spill must use one directed spot: " + name);
            var spot = (SpotLight3D)lights[0];
            var forward = _vehicle.GlobalBasis.Inverse() * -spot.GlobalBasis.Z;
            Require(forward.DistanceTo(new Vector3(0, -0.1391731f, 0.9902681f)) < 0.00001f &&
                spot.SpotRange == 4 && spot.SpotAngle == 55 && !spot.ShadowEnabled,
                "actual rear/downward spill direction, range or shadow cost changed: " + name);
        }
    }

    private void ObserveRenderedFrame()
    {
        if (Complete || CurrentStage != "mirrors-live" || !_begun) return;
        try
        {
            for (var i = 0; i < _presentation.Mirrors.Count; i++)
            {
                var mirror = _presentation.Mirrors[i];
                if (mirror.UpdateCount == 0 || mirror.UpdateCount == _mirrorObservedUpdates.GetValueOrDefault(mirror.Name)) continue;
                _mirrorObservedUpdates[mirror.Name] = mirror.UpdateCount;
                var texture = mirror.Viewport.GetTexture();
                using var image = texture.GetImage();
                if (image is null || image.IsEmpty()) throw new InvalidOperationException("Mirror image is empty.");
                image.Convert(Image.Format.Rgba8);
                var pixels = MeasureTargetPixels(image, i);
                var count = pixels.Count;
                var target = _mirrorTargets[i].GlobalPosition;
                var projected = mirror.Camera.UnprojectPosition(target);
                var inMainCamera = _vehicle.GetViewport().GetCamera3D().IsPositionInFrustum(target);
                var centroid = pixels.Centroid;
                var sample = new { mirror = mirror.Name, frame = Engine.GetProcessFrames(), completed_frame = mirror.LastUpdateFrame, requested_frame = mirror.RequestedAtFrame, update = mirror.UpdateCount, pixels = count, target_world = Vec(target), target_projection = new[] { projected.X, projected.Y }, observed_centroid = new[] { centroid.X, centroid.Y }, projection_error_px = count > 0 ? centroid.DistanceTo(projected) : (float?)null, main_camera_visible = inMainCamera };
                _mirrorSamples.Add(sample);
                _mirrorFrameLog.WriteLine(JsonSerializer.Serialize(sample));
                var imageSample = _mirrorImageSamples.GetValueOrDefault(mirror.Name) + 1;
                _mirrorImageSamples[mirror.Name] = imageSample;
                if (imageSample is 1 or 20) SaveImage(image, $"mirror-{mirror.Name}-sample-{imageSample:00}.png");
                Require(!inMainCamera, "mirror target is visible to the main camera");
                if (count >= 8)
                {
                    Require(centroid.DistanceTo(projected) <= 5.0f, "mirror target pixels differ by more than 5px from their camera projection: " + mirror.Name);
                    VerifyMirrorBinding(mirror);
                    if (!_mirrorCentroids.TryGetValue(mirror.Name, out var points)) _mirrorCentroids[mirror.Name] = points = [];
                    points.Add(centroid);
                    if (points.Count is 1 or 20) SaveImage(image, $"mirror-{mirror.Name}-{points.Count:00}.png");
                }
            }
        }
        catch (Exception exception) { _renderException = exception; }
    }

    private static (int Count, Vector2 Centroid) MeasureTargetPixels(Image image, int marker)
    {
        // Tone mapping changes a bright green marker to (123,209,70), and
        // the modeled rear glass attenuates cyan to about (20,122,125).
        // Color separation preserves the marker identity through those real
        // responses. A rendered targets-hidden check rejects background hits.
        var bytes = image.GetData();
        var count = 0;
        double sumX = 0, sumY = 0;
        for (var y = 0; y < image.GetHeight(); y++) for (var x = 0; x < image.GetWidth(); x++)
        {
            var at = (y * image.GetWidth() + x) * 4;
            var red = (int)bytes[at]; var green = (int)bytes[at + 1]; var blue = (int)bytes[at + 2];
            var match = marker switch
            {
                0 => red > 80 && blue > 80 && red - green > 40 && blue - green > 40,
                1 => green > 80 && green - red > 40 && green - blue > 40,
                _ => green > 80 && blue > 80 && green - red > 40 && blue - red > 40,
            };
            if (match) { count++; sumX += x; sumY += y; }
        }
        return (count, count > 0 ? new Vector2((float)(sumX / count), (float)(sumY / count)) : new Vector2(-1, -1));
    }

    private object CaptureStance()
    {
        var suffixes = new[] { "FL", "FR", "RL", "RR" };
        return new
        {
            chassis_origin = Vec(_vehicle.GlobalPosition), visible_floor_y = _floor.GlobalPosition.Y + 0.06f,
            wheels = Enumerable.Range(0, 4).Select(index =>
            {
                var ray = _vehicle.SuspensionRay(index);
                var center = _rig.ResolveAnchor("Wheel_" + suffixes[index]).GlobalPosition;
                return new
                {
                    wheel = suffixes[index], center = Vec(center),
                    nominal_tire_bottom_y = center.Y - _vehicle.RigSetup.TireRadiusMeters,
                    compression_m = _vehicle.SuspensionCompressionMeters(index),
                    contact = ray.IsColliding(),
                    collider = ray.IsColliding() ? (ray.GetCollider() as Node)?.Name.ToString() : null,
                    contact_position = ray.IsColliding() ? Vec(ray.GetCollisionPoint()) : null,
                    collision_mask = ray.CollisionMask,
                };
            }).ToArray(),
        };
    }

    private void VerifyDisplayUv(string name, SubViewport viewport, bool mirror = false)
    {
        var anchor = _rig.ResolveAnchor(name);
        var meshes = Descendants(anchor).OfType<MeshInstance3D>().Where(mesh => mesh.IsVisibleInTree()).ToArray();
        Require(meshes.Length > 0, "display has no visible mesh: " + name);
        var sums = new Vector3[4];
        var counts = new int[4];
        var expectedTexture = viewport.GetTexture();
        foreach (var mesh in meshes)
        {
            var material = mesh.MaterialOverride as StandardMaterial3D;
            Require(material?.AlbedoTexture?.GetRid() == expectedTexture.GetRid(), "display uses a different viewport texture: " + name);
            if (!mirror)
                Require(material!.Uv1Scale.IsEqualApprox(Vector3.One) && material.Uv1Offset.IsZeroApprox(), "instrument material changes the authored UV transform");
            var transform = anchor.GlobalTransform.AffineInverse() * mesh.GlobalTransform;
            for (var surface = 0; surface < mesh.Mesh.GetSurfaceCount(); surface++)
            {
                using var arrays = mesh.Mesh.SurfaceGetArrays(surface);
                var vertices = arrays[(int)Mesh.ArrayType.Vertex].AsVector3Array();
                var uvs = arrays[(int)Mesh.ArrayType.TexUV].AsVector2Array();
                Require(vertices.Length > 0 && vertices.Length == uvs.Length, "display vertex/UV inventory mismatch: " + name);
                for (var index = 0; index < vertices.Length; index++)
                {
                    var uv = uvs[index];
                    Require(uv.IsFinite() && uv.X is >= -0.0001f and <= 1.0001f && uv.Y is >= -0.0001f and <= 1.0001f, "display UV lies outside its single image: " + name);
                    var u = Mathf.Abs(uv.X) < 0.0001f ? 0 : Mathf.Abs(uv.X - 1) < 0.0001f ? 1 : -1;
                    var v = Mathf.Abs(uv.Y) < 0.0001f ? 0 : Mathf.Abs(uv.Y - 1) < 0.0001f ? 1 : -1;
                    if (u < 0 || v < 0) continue;
                    var corner = u + 2 * v;
                    sums[corner] += transform * vertices[index];
                    counts[corner]++;
                }
            }
        }
        Require(counts.All(count => count > 0), "display does not cover all four image corners: " + name);
        var corners = sums.Select((sum, index) => sum / counts[index]).ToArray();
        _displayUvCorners[name] = corners;
        var right = corners[1] - corners[0];
        var down = corners[2] - corners[0];
        var aspect = right.Length() / down.Length();
        _displayUvMeasurements[name] = new
        {
            corners = corners.Select(Vec).ToArray(), corner_vertex_counts = counts,
            u_direction = Vec(right.Normalized()), v_direction = Vec(down.Normalized()),
            aspect_ratio = aspect, viewport_aspect_ratio = (float)viewport.Size.X / viewport.Size.Y,
            matching_viewport_texture = true, material_horizontal_reflection = mirror,
        };
        Require(right.Normalized().Dot(Vector3.Right) > 0.99f && down.Normalized().Dot(Vector3.Down) > 0.95f,
            "actual display UV axes do not run right and down on the visible surface: " + name);
        if (!mirror)
            Require(Math.Abs(aspect / ((float)viewport.Size.X / viewport.Size.Y) - 1) < 0.02,
                "instrument surface stretches its viewport aspect by more than two percent");
    }

    private void VerifyMirrorBinding(EnduranceSedanPresentation.Mirror mirror)
    {
        // These resources belong to the presenter/viewport. Several surfaces
        // share the same material and texture, so disposing a borrowed alias
        // would invalidate the expected identity used by the next surface.
        var expectedTexture = mirror.Viewport.GetTexture();
        var meshes = Descendants(_rig.ResolveAnchor("Mirror_" + mirror.Name)).OfType<MeshInstance3D>().ToArray();
        Require(meshes.Length > 0, "mirror has no display surfaces: " + mirror.Name);
        foreach (var mesh in meshes)
        {
            var material = mesh.MaterialOverride as StandardMaterial3D;
            Require(material is not null, "mirror has no actual StandardMaterial override");
            var texture = material!.AlbedoTexture;
            Require(texture is not null && texture.GetRid() == expectedTexture.GetRid() && material.Uv1Scale.IsEqualApprox(new Vector3(-1, 1, 1)) && material.Uv1Offset.IsEqualApprox(new Vector3(1, 0, 0)), "mirror surface texture identity or horizontal reflection differs from its matching viewport: " + mirror.Name);
        }
    }

    private void ValidateVisibleLamps(JsonElement state)
    {
        foreach (var lamp in state.GetProperty("lamps").EnumerateObject())
        {
            var visible = Descendants(_rig.ResolveAnchor(lamp.Name)).OfType<MeshInstance3D>().Where(mesh => mesh.IsVisibleInTree()).ToArray();
            Require(visible.Length > 0, "active LOD has no state-driven lamp emitter: " + lamp.Name);
            var expectedEnergy = lamp.Value.GetProperty("emission").GetDouble();
            foreach (var mesh in visible)
            {
                Require(mesh.Name.ToString().StartsWith($"LOD{_rig.ActiveLod}_", StringComparison.Ordinal), "visible lamp does not belong to the actual selected LOD: " + mesh.Name);
                for (var surface = 0; surface < mesh.Mesh.GetSurfaceCount(); surface++)
                {
                    var material = mesh.GetActiveMaterial(surface) as StandardMaterial3D;
                    Require(material is not null && material.EmissionEnabled && Math.Abs(material.EmissionEnergyMultiplier - expectedEnergy) < 0.001,
                        "visible lamp material does not match runtime emission state: " + mesh.Name);
                }
            }
        }
    }

    private async Task CaptureAsync(string stage)
    {
        await _parent.ToSignal(RenderingServer.Singleton, RenderingServer.SignalName.FramePostDraw);
        var contactShading = CaptureRenderedContactShading();
        var viewport = _vehicle.GetViewport();
        var texture = viewport.GetTexture();
        using var image = texture.GetImage();
        if (image is null || image.IsEmpty()) throw new InvalidOperationException("Actual presentation capture is empty.");
        var path = SaveImage(image, $"{_stage + 1:00}-{stage}.png");
        _captures.Add(new { stage, camera = viewport.GetCamera3D().Name.ToString(), camera_position = Vec(viewport.GetCamera3D().GlobalPosition),
            size = new[] { image.GetWidth(), image.GetHeight() }, path, sha256 = Hash(path), frame = Engine.GetProcessFrames(), posed = true,
            lighting = SkyLighting.CurrentPreset?.ToString(), actual_environment_preset = _parent.GetNode<WorldEnvironment>("NightEnvironment").Environment!.GetMeta("lighting_preset", "missing").AsString(),
            renderer = RenderingServer.GetCurrentRenderingMethod().ToString(),
            render_quality = new
            {
                actual_msaa_3d = viewport.Msaa3D.ToString(),
                applied_tier = viewport.GetMeta("render_quality", "missing").AsString(),
                applied_directional_shadow_size = viewport.GetMeta("directional_shadow_size", -1).AsInt32(),
                global_quality_basis = "Atlas/tier are applied-call metadata; MSAA is a live Viewport property.",
            }, lod = _rig.ActiveLod, contact_shading = contactShading });
        if (stage is "cockpit" or "instruments-forward" || WarningStages.ContainsKey(stage))
        {
            var display = _presentation.InstrumentViewport.GetTexture();
            using var displayImage = display.GetImage();
            SaveImage(displayImage, "display-" + stage + ".png");
            if (WarningStages.TryGetValue(stage, out var expectedWarning)) VerifyWarningVisibility(image, displayImage, expectedWarning);
        }
        _captured = true;
    }

    private object CaptureRenderedContactShading()
    {
        var shading = _vehicle.ContactShading;
        Require(shading is not null, "selected sedan has no contact-shading component");
        var floorTransform = _floor.GetGlobalTransformInterpolated();
        var floorTop = floorTransform * new Vector3(0, 0.06f, 0);
        var floorNormal = floorTransform.Basis.Y.Normalized();
        var stance = Enumerable.Range(0, 4).Select(index =>
        {
            var suffix = new[] { "FL", "FR", "RL", "RR" }[index];
            var ray = _vehicle.SuspensionRay(index);
            var center = _rig.ResolveAnchor("Wheel_" + suffix).GetGlobalTransformInterpolated().Origin;
            if (shading!.SupportedRenderer)
            {
                var state = shading.ReadWheel(index);
                Require(state.Supported && state.EligibleReceiver && state.Visible,
                    "actual inspection contact shading is not visible on all four supported wheels: " + suffix);
                Require(ray.GetCollider() is Node collider && collider.Name == "InspectionFloorContact" && collider.GetParent() == _fixture,
                    "inspection contact ray did not hit this fixture's actual floor: " + suffix);
                Require(state.DerivedDisplayErrorMeters <= 0.001f && state.WheelTangentialErrorMeters <= 0.001f && state.ContactPlaneErrorMeters <= 0.001f,
                    "displayed contact shading is displaced from the interpolated wheel/contact plane: " + suffix);
            }
            return new { wheel = suffix, displayed_center = Vec(center), nominal_tire_bottom_above_floor_m = (center - floorTop).Dot(floorNormal) - _vehicle.RigSetup.TireRadiusMeters };
        }).ToArray();
        if (shading!.SupportedRenderer)
        {
            Require((_floor.Layers & VehicleContactShading.ReceiverLayer) != 0,
                "actual visible inspection floor is missing the contact-shading receiver layer");
            Require(Descendants(_fixture).OfType<MeshInstance3D>().All(mesh => mesh == _floor || (mesh.Layers & VehicleContactShading.ReceiverLayer) == 0),
                "contact shading registered an unrelated inspection mesh");
        }
        return new
        {
            boundary = "native-frame-post-draw", process_frame = Engine.GetProcessFrames(), physics_frame = Engine.GetPhysicsFrames(), drawn_frame = Engine.GetFramesDrawn(),
            status = shading.SupportedRenderer ? "passed" : "unsupported-renderer",
            snapshot = shading.CaptureSnapshot(), floor_path = _floor.GetPath().ToString(), floor_layers = _floor.Layers,
            floor_visible = _floor.IsVisibleInTree(), displayed_floor_origin = Vec(floorTransform.Origin), displayed_floor_top = Vec(floorTop), displayed_floor_normal = Vec(floorNormal),
            displayed_chassis_origin = Vec(_vehicle.GetGlobalTransformInterpolated().Origin), stance,
            scope = "Actual contact eligibility, layers and displayed alignment; visual quality and performance need independent review.",
        };
    }

    private void VerifyWarningVisibility(Image cockpitImage, Image displayImage, string expectedWarning)
    {
        var rectangle = _presentation.InstrumentWarningRect;
        var glyphs = new List<Vector2I>();
        for (var y = (int)rectangle.Position.Y; y < rectangle.End.Y; y++)
            for (var x = (int)rectangle.Position.X; x < rectangle.End.X; x++)
            {
                var color = displayImage.GetPixel(x, y);
                if (color.R >= 0.8f && color.G >= 0.45f && color.R - color.G >= 0.1f && color.G - color.B >= 0.2f)
                    glyphs.Add(new Vector2I(x, y));
            }
        _warningVisibilities[CurrentStage] = new { stage = CurrentStage, warning = expectedWarning, source_glyph_pixels = glyphs.Count,
            passed = false, failure = "No strong amber glyphs measured yet" };
        Require(glyphs.Count >= 40, "actual " + expectedWarning + " viewport has no strong amber warning glyphs");
        var corners = _displayUvCorners["Instrument_Cluster"];
        var transform = _rig.ResolveAnchor("Instrument_Cluster").GetGlobalTransformInterpolated();
        var camera = _vehicle.GetViewport().GetCamera3D();
        var middle = (glyphs.Min(point => point.Y) + glyphs.Max(point => point.Y)) * 0.5f;
        var counts = new int[2];
        var matched = new int[2];
        var projected = new List<object>();
        foreach (var glyph in glyphs)
        {
            var u = (glyph.X + 0.5f) / displayImage.GetWidth();
            var v = (glyph.Y + 0.5f) / displayImage.GetHeight();
            var local = corners[0] + (corners[1] - corners[0]) * u + (corners[2] - corners[0]) * v;
            var pixel = camera.UnprojectPosition(transform * local);
            var x = Mathf.RoundToInt(pixel.X);
            var y = Mathf.RoundToInt(pixel.Y);
            var seen = false;
            for (var dy = -1; dy <= 1; dy++)
                for (var dx = -1; dx <= 1; dx++)
                    if (x + dx >= 0 && x + dx < cockpitImage.GetWidth() && y + dy >= 0 && y + dy < cockpitImage.GetHeight())
                    {
                        var color = cockpitImage.GetPixel(x + dx, y + dy);
                        seen |= color.R >= 0.3f && color.G >= 0.2f && color.R - color.G >= 0.06f && color.G - color.B >= 0.1f;
                    }
            var half = glyph.Y <= middle ? 0 : 1;
            counts[half]++;
            if (seen) matched[half]++;
            projected.Add(new { source_pixel = new[] { glyph.X, glyph.Y }, cockpit_pixel = new[] { pixel.X, pixel.Y }, matched = seen });
        }
        var totalRatio = (float)matched.Sum() / glyphs.Count;
        var halfRatios = matched.Select((value, index) => counts[index] > 0 ? (float)value / counts[index] : 0).ToArray();
        _warningVisibilities[CurrentStage] = new
        {
            stage = CurrentStage, frame = Engine.GetProcessFrames(), warning = expectedWarning,
            warning_rect = new[] { rectangle.Position.X, rectangle.Position.Y, rectangle.Size.X, rectangle.Size.Y },
            source_glyph_pixels = glyphs.Count, matched_glyph_pixels = matched.Sum(), total_ratio = totalRatio,
            half_source_counts = counts, half_matched_counts = matched, half_ratios = halfRatios,
            required_total_ratio = 0.90, required_half_ratio = 0.85, search_radius_pixels = 1,
            screen_corners = corners.Select(point => Vec(transform * point)).ToArray(),
            camera_position = Vec(camera.GlobalPosition), camera_forward = Vec(-camera.GlobalBasis.Z),
            passed = totalRatio >= 0.90f && halfRatios.All(ratio => ratio >= 0.85f), projected_glyph_samples = projected,
        };
        Require(totalRatio >= 0.90f && halfRatios.All(ratio => ratio >= 0.85f),
            $"actual cockpit warning glyphs are occluded: total={totalRatio:0.000}, upper={halfRatios[0]:0.000}, lower={halfRatios[1]:0.000}");
    }

    private void CameraAt(Vector3 point, Vector3? target = null)
    {
        _vehicle.SetCameraMode(false);
        _camera.GlobalPosition = point;
        _camera.LookAt(target ?? new Vector3(0, 0.8f, 0), Math.Abs(point.Y) > 5 ? Vector3.Forward : Vector3.Up);
        _camera.MakeCurrent();
    }
    private void Cockpit() { _camera.Current = false; _vehicle.SetCameraMode(true); }
    private void Lighting(LightingPreset preset) => SkyLighting.Apply(_parent.GetNode<DirectionalLight3D>(SkyLighting.LightNodeName), _parent.GetNode<WorldEnvironment>(SkyLighting.EnvironmentNodeName).Environment!, preset);
    private static MeshInstance3D Box(string name, Vector3 point, Vector3 size, Color color, bool unshaded = false)
    {
        using var material = new StandardMaterial3D { AlbedoColor = color, Roughness = 0.85f, ShadingMode = unshaded ? BaseMaterial3D.ShadingModeEnum.Unshaded : BaseMaterial3D.ShadingModeEnum.PerPixel };
        using var mesh = new BoxMesh { Size = size, Material = material };
        return new MeshInstance3D { Name = name, Position = point, Mesh = mesh };
    }
    private string SaveImage(Image image, string name)
    {
        var path = Path.Combine(_directory, name);
        var error = image.SavePng(path);
        if (error != Error.Ok) throw new IOException($"Could not save {path}: {error}");
        return path;
    }
    private static float[] Vec(Vector3 value) => [value.X, value.Y, value.Z];
    private static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private static IEnumerable<Node> Descendants(Node node) { foreach (var child in node.GetChildren()) { yield return child; foreach (var descendant in Descendants(child)) yield return descendant; } }
    private void Require(bool condition, string message) { if (!condition) throw new InvalidOperationException($"Sedan presentation '{CurrentStage}': {message}"); }

    private void Finish()
    {
        _vehicle.InspectionPanel.Close();
        _vehicle.Condition = _originalCondition;
        _vehicle.AutomationInputOverride = Neutral;
        _frames.Dispose();
        _mirrorFrameLog.Dispose();
        WriteSummary("passed");
        Complete = true;
        GD.Print($"CANNONBALL_SEDAN_PRESENTATION_OK stages={_results.Count} posed=true rendered={_rendered.ToString().ToLowerInvariant()} diagnostic={_diagnosticProbe ?? "none"}");
    }

    private void WriteSummary(string status)
    {
        var inputs = new Dictionary<string, string>();
        var unavailableInputs = new List<string>();
        foreach (var relative in new[] { "game/Automation/EnduranceSedanPresentationScenario.cs", "game/Vehicle/VehicleContactShading.cs", "game/Vehicle/EnduranceSedanPresentation.cs", "game/Vehicle/EnduranceSedanPresentationSetup.cs", "game/Vehicle/Setups/EnduranceSedanPresentation.tres", "game/Vehicle/VehicleInspectionPanel.cs", "game/Main.cs", "game/Vehicle/Setups/EnduranceSedan.tres", "game/Vehicle/Visuals/EnduranceSedan.tscn", "docs/vehicles/endurance-sedan/specification.json", "data/assets/vehicles/derived/endurance-sedan.glb", "assets/vehicles/endurance-sedan/endurance-sedan.generated.tscn" })
        {
            var absolute = ProjectSettings.GlobalizePath("res://" + relative);
            if (File.Exists(absolute)) inputs[relative] = Hash(absolute);
            else unavailableInputs.Add(relative);
        }
        File.WriteAllText(Path.Combine(_directory, "presentation-summary.json"), JsonSerializer.Serialize(new
        {
            schema_version = 1, task_id = "P1-018", status,
            vehicle = "endurance-sedan", loaded_asset = _vehicle.RigSetup.AssetId,
            physics_hz = Engine.PhysicsTicksPerSecond, frame_samples = _frameSamples,
            scope = _diagnosticProbe is null ? "posed presentation fixtures; not driving evidence" : "targeted native diagnostic only; not full presentation acceptance",
            diagnostic_probe = _diagnosticProbe, failed_stage = status == "passed" ? null : CurrentStage,
            diagnostic_side_mirror_camera_source_y_m = _diagnosticCameraSourceY,
            mirror_lighting = _mirrorLighting == LightingPreset.Night ? "night" : "daylight",
            git_revision = OS.GetEnvironment("CANNONBALL_GIT_REVISION"), utc = DateTimeOffset.UtcNow, platform = OS.GetName(), engine = Engine.GetVersionInfo()["string"].AsString(),
            arguments = OS.GetCmdlineUserArgs(), input_hashes = inputs,
            input_hash_scope = "physically available repository files; packaged PCK/assembly hashes are bound by the external package verifier",
            unavailable_input_paths = unavailableInputs, user_data_directory = OS.GetUserDataDir(),
            executable_path = OS.GetExecutablePath(), runtime_is_debug_build = OS.IsDebugBuild(),
            expected_stages = _expected, completed_stages = _results,
            rendered = _rendered, renderer = RenderingServer.GetCurrentRenderingMethod().ToString(), captures = _captures, mirror_samples = _mirrorSamples,
            display_uv_measurements = _displayUvMeasurements,
            warning_visibility = _warningVisibilities.GetValueOrDefault("instruments-low-fuel"),
            warning_visibilities = _warningVisibilities,
            mirror_samples_sha256 = Hash(Path.Combine(_directory, "mirror-samples.jsonl")),
            frames_sha256 = Hash(Path.Combine(_directory, "presentation-frames.jsonl")), human_approval = (string?)null,
            limitations = new[] { "Posed fixtures do not prove handling or physical device usability", "Native target pixels prove mirror image updates; frame-budget and freshness deadlines need the separate real-time benchmark", "Swept mesh clearances and wiper glass contact require the geometric export/QA pass", "Human visual, rights and usability gates remain open" },
        }, JsonOptions));
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        if (_rendered) RenderingServer.FramePostDraw -= ObserveRenderedFrame;
        foreach (var (anchor, transform) in _originalMirrorAnchorTransforms)
            if (GodotObject.IsInstanceValid(anchor)) anchor.Transform = transform;
        _frames.Dispose();
        _mirrorFrameLog.Dispose();
        if (!Complete) WriteSummary("failed");
    }
}
