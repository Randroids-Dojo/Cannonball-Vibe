using Cannonball.Game.Input;
using Cannonball.Game.Lifecycle;
using Godot;

namespace Cannonball.Game.Vehicle.Showroom;

/// <summary>A private display world; the real run never moves into the studio.</summary>
public partial class VehicleShowroom : CanvasLayer
{
    public const string ScenePath = "res://game/Vehicle/Showroom/VehicleShowroom.tscn";
    [Export] public string AssetId { get; set; } = "endurance-sedan";
    public event Action? Closed;
    private readonly Godot.Collections.Dictionary _state = new();
    private readonly List<(Node Node, ProcessModeEnum Mode)> _hostModes = [];
    private readonly List<(CanvasLayer Layer, bool Visible)> _hostLayers = [];
    private readonly Dictionary<string, CheckButton> _openingButtons = new(StringComparer.Ordinal);
    private readonly RuntimeShutdown _shutdown = new();
    private Node3D? _host;
    private bool _hostVisible, _previousPause, _closing;
    private Control _root = null!, _interface = null!;
    private SubViewport _viewport = null!;
    private Window? _window;
    private bool _windowConnected;
    private Node3D _world = null!, _floor = null!;
    private CannonballVehicle _display = null!;
    private VehicleVisualRig? _rig;
    private EnduranceSedanPresentation? _presentation;
    private Camera3D _camera = null!;
    private Label _viewLabel = null!, _notice = null!, _pointerHelp = null!, _controllerHelp = null!;
    private PanelContainer _noticePanel = null!;
    private Button _orbitButton = null!, _homeButton = null!;
    private CheckButton _headlights = null!, _wipers = null!, _hazards = null!;
    private OptionButton _lightingOptions = null!;
    private PopupMenu _lightingPopup = null!;
    private Godot.Environment _environment = null!;
    private ShaderMaterial _skyMaterial = null!;
    private DirectionalLight3D _key = null!, _fill = null!, _inspectionLight = null!;
    private ShowroomMetrics? _metrics;
    private (MeshInstance3D Mesh, Aabb Bounds)[] _cameraObstacles = [];
    private float _cameraClearance;
    private Vector3 _target = new(0, .74f, 0), _smoothedTarget = new(0, .74f, 0);
    private float _yaw = -.72f, _pitch = .24f, _distance = 8.2f;
    private float _smoothYaw = -.72f, _smoothPitch = .24f, _smoothDistance = 8.2f;
    private bool _dragOrbit, _dragPan, _autoOrbit, _interior, _uiVisible = true;
    private string _view = "overview", _lighting = "studio", _lastPhoto = "";
    private double _stateElapsed, _noticeRemaining;
    private ulong _drawnFrames;
    private ulong _worldInstanceId;
    private bool _drawConnected;

    public void OpenOver(Node3D host)
    {
        if (IsInsideTree()) throw new InvalidOperationException("Showroom is already open.");
        _host = host;
        _hostVisible = host.Visible;
        _previousPause = host.GetTree().Paused;
        foreach (var node in Walk(host))
        {
            if (node == host || node.ProcessMode != ProcessModeEnum.Inherit)
            {
                _hostModes.Add((node, node.ProcessMode));
                node.ProcessMode = ProcessModeEnum.Disabled;
            }
            if (node is CanvasLayer layer)
            {
                _hostLayers.Add((layer, layer.Visible));
                layer.Hide();
            }
        }
        host.Hide();
        host.GetTree().Paused = true;
        host.GetTree().Root.AddChild(this);
    }

    public override void _Ready()
    {
        try { Initialize(); }
        catch (Exception error)
        {
            _closing = true;
            GD.PushError($"Showroom could not open: {error}");
            if (_host is not null) { RestoreHost(); QueueFree(); }
            else _ = _shutdown.Request(this, () => Task.CompletedTask, 1, false);
        }
    }

    private void Initialize()
    {
        Name = "VehicleShowroom";
        Layer = 60;
        ProcessMode = ProcessModeEnum.Always;
        SetMeta("automation_id", "showroom.root");
        SetMeta("automation_state", _state);
        if (!InputMap.HasAction(GameInputMap.VehicleInspection)) GameInputMap.Configure();
        if (_host is null) GetTree().AutoAcceptQuit = false;
        _root = new Control { Name = "ShowroomRoot", MouseFilter = Control.MouseFilterEnum.Ignore };
        AddChild(_root);
        _root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        var container = new TextureRect
        {
            ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize, StretchMode = TextureRect.StretchModeEnum.Scale,
            MouseFilter = Control.MouseFilterEnum.Ignore,
        };
        _root.AddChild(container);
        container.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        _viewport = new SubViewport
        {
            Name = "ShowroomViewport", OwnWorld3D = true, HandleInputLocally = false,
            RenderTargetUpdateMode = SubViewport.UpdateMode.Always,
            Msaa3D = GetViewport().Msaa3D, PositionalShadowAtlasSize = 2048,
        };
        _root.AddChild(_viewport);
        using (var texture = _viewport.GetTexture()) container.Texture = texture;
        _window = GetWindow();
        if (_host is null) _window.Title = "Cannonball | Car showroom";
        ResizeRenderViewport();
        _window.SizeChanged += ResizeRenderViewport;
        _windowConnected = true;
        _world = new Node3D { Name = "Studio", PhysicsInterpolationMode = PhysicsInterpolationModeEnum.Off };
        _viewport.AddChild(_world);
        using (var resolvedWorld = _viewport.FindWorld3D()) _worldInstanceId = resolvedWorld.GetInstanceId();
        BuildStudio();
        _display = new CannonballVehicle
        {
            RigSetup = VehicleRigSetup.Load(AssetId), ForceGrayboxVisual = AssetId == "graybox",
            Freeze = true, InspectionActive = true, AutopilotEnabled = false,
            ProcessMode = ProcessModeEnum.Always, PhysicsInterpolationMode = PhysicsInterpolationModeEnum.Off,
        };
        _world.AddChild(_display);
        _display.Name = "ShowroomVehicle";
        _display.PlaceForReview(Vector3.Zero, Vector3.Forward);
        _display.SetPhysicsProcess(false);
        _display.DrivingInputController.ProcessMode = ProcessModeEnum.Disabled;
        _display.InspectionPanel.ProcessMode = ProcessModeEnum.Disabled;
        _display.InspectionPanel.Hide();
        _display.ChaseCameraRig.ProcessMode = ProcessModeEnum.Disabled;
        _display.CockpitCameraRig.ProcessMode = ProcessModeEnum.Disabled;
        if (_display.ContactShading is { } contact) contact.ProcessMode = ProcessModeEnum.Disabled;
        _rig = _display.VisualRig;
        _presentation = _rig?.Presentation;
        if (_presentation is not null)
        {
            _presentation.AutoLodEnabled = false;
            _presentation.MirrorsEnabled = false;
            _presentation.SetProcessUnhandledInput(false);
        }
        _rig?.SetLod(0);
        // Reuse the cockpit camera so the existing mirror policy remains authoritative.
        // Its driving camera controller is disabled; the viewer owns only this copy's pose.
        _camera = _display.CockpitCameraRig.Camera;
        _camera.TopLevel = true;
        _camera.Current = true;
        _camera.Near = .025f;
        _camera.Far = 80;
        _camera.CullMask = (1u << 20) - 1;
        foreach (var node in Walk(_display))
            if (node.HasMeta("automation_id")) node.RemoveMeta("automation_id");
        _cameraObstacles = Walk(_display).OfType<MeshInstance3D>()
            .Select(mesh => (mesh, mesh.GetAabb())).ToArray();
        BuildInterface();
        _homeButton.GrabFocus();
        SetLighting(0);
        SelectView("overview");
        UpdateCamera(1);
        if (Automation.AutomationInspection.Enabled)
        {
            _metrics = new ShowroomMetrics();
            _metrics.BeginCase(_view, _lighting);
            _state["renderer"] = RenderingServer.GetCurrentRenderingMethod();
            _state["fps_cap"] = Engine.MaxFps;
            _state["vsync_mode"] = (int)DisplayServer.WindowGetVsyncMode();
        }
        RenderingServer.FramePostDraw += OnFrameDrawn;
        _drawConnected = true;
        PublishState();
        GD.Print($"CANNONBALL_SHOWROOM_READY asset={AssetId} private_world=true driving_body_unchanged=true");
    }

    private void OnFrameDrawn()
    {
        _drawnFrames++;
        _metrics?.RecordFrame(_viewport);
    }

    private void ResizeRenderViewport()
    {
        if (_window is not null)
            _viewport.Size = new Vector2I(Math.Max(1, _window.Size.X), Math.Max(1, _window.Size.Y));
    }

    public override void _Process(double delta)
    {
        if (_closing) return;
        var dt = (float)Math.Min(delta, .1);
        var lookX = Godot.Input.GetAxis(GameInputMap.CameraLookLeft, GameInputMap.CameraLookRight);
        var lookY = Godot.Input.GetAxis(GameInputMap.CameraLookDown, GameInputMap.CameraLookUp);
        var zoom = Godot.Input.GetAxis(GameInputMap.TripMapZoomOut, GameInputMap.TripMapZoomIn);
        if (Math.Abs(lookX) + Math.Abs(lookY) > .01f)
        {
            _autoOrbit = false;
            _yaw += lookX * dt * 1.3f;
            _pitch = Mathf.Clamp(_pitch + lookY * dt, -1.45f, 1.55f);
        }
        if (Math.Abs(zoom) > .01f) Zoom(-zoom * dt * 1.6f);
        var panX = Godot.Input.GetAxis(GameInputMap.SteerLeft, GameInputMap.SteerRight);
        var panY = Godot.Input.GetAxis(GameInputMap.Brake, GameInputMap.Accelerate);
        if (!_interior && Math.Abs(panX) + Math.Abs(panY) > .01f)
            Pan(new Vector2(-panX, panY) * dt * 120);
        if (_autoOrbit && !_interior) _yaw += dt * .16f;
        UpdateCamera(1 - MathF.Exp(-12 * dt));
        _stateElapsed += delta;
        if (_stateElapsed >= .1)
        {
            _stateElapsed %= .1;
            UpdateInterface();
            PublishState();
        }
        if (_noticeRemaining > 0 && (_noticeRemaining -= delta) <= 0) _noticePanel.Hide();
    }

    public override void _Input(InputEvent @event)
    {
        // Finish drags even when the cursor crosses a control or leaves the viewport.
        if (@event is InputEventMouseButton released && !released.Pressed)
        {
            if (released.ButtonIndex == MouseButton.Left) _dragOrbit = false;
            if (released.ButtonIndex is MouseButton.Right or MouseButton.Middle) _dragPan = false;
        }
        if (@event is InputEventMouseMotion motion && (_dragOrbit || _dragPan))
        {
            _autoOrbit = false;
            if (_dragOrbit)
            {
                _yaw += motion.Relative.X * (_interior ? .004f : -.004f);
                _pitch = Mathf.Clamp(_pitch + motion.Relative.Y * (_interior ? -.004f : .004f), -1.45f, 1.55f);
            }
            if (_dragPan && !_interior) Pan(motion.Relative);
            GetViewport().SetInputAsHandled();
        }
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (_closing || @event.IsEcho()) return;
        var handled = true;
        if (@event is InputEventMouseButton mouse && mouse.Pressed)
        {
            switch (mouse.ButtonIndex)
            {
                case MouseButton.Left: _dragOrbit = true; break;
                case MouseButton.Right: case MouseButton.Middle: _dragPan = true; break;
                case MouseButton.WheelUp: Zoom(-.12f); break;
                case MouseButton.WheelDown: Zoom(.12f); break;
                default: handled = false; break;
            }
        }
        else if (@event is InputEventKey key && key.Pressed)
        {
            switch (key.Keycode)
            {
                case Key.Escape: case Key.F2: Close(); break;
                case Key.R: SelectView("overview"); break;
                case Key.F1: SetInterfaceVisible(!_uiVisible); break;
                case Key.Space: ToggleOrbit(); break;
                case Key.H: _presentation?.CycleHeadlampMode(); break;
                case Key.T: _presentation?.SetWipers(!_presentation.WipersOn); break;
                default: handled = false; break;
            }
        }
        else if (@event is InputEventJoypadButton button && button.Pressed)
        {
            switch (button.ButtonIndex)
            {
                case JoyButton.B: Close(); break;
                case JoyButton.Y: SelectView("overview"); break;
                case JoyButton.X: SetAllOpen(!(_presentation?.AnyOpeningActive ?? false)); break;
                case JoyButton.LeftShoulder: CycleView(-1); break;
                case JoyButton.RightShoulder: CycleView(1); break;
                case JoyButton.RightStick: SetInterfaceVisible(!_uiVisible); break;
                default: handled = false; break;
            }
        }
        else handled = false;
        if (handled) GetViewport().SetInputAsHandled();
    }

    public override void _Notification(int what)
    {
        if (what == NotificationApplicationFocusOut) _dragOrbit = _dragPan = false;
        if (what == NotificationWMCloseRequest && _host is null) Close();
    }

    private void Pan(Vector2 pixels)
    {
        _autoOrbit = false;
        _target += (-_camera.GlobalBasis.X * pixels.X + _camera.GlobalBasis.Y * pixels.Y) * _distance * .001f;
        _target = _target.Clamp(new Vector3(-2.5f, -.6f, -3), new Vector3(2.5f, 2.5f, 3));
    }

    private void Zoom(float amount)
    {
        _autoOrbit = false;
        if (_interior) _camera.Fov = Mathf.Clamp(_camera.Fov + amount * 28, 38, 92);
        else _distance = Mathf.Clamp(_distance * MathF.Exp(amount), .7f, 14);
    }

    private void UpdateCamera(float blend)
    {
        _smoothYaw = Mathf.Lerp(_smoothYaw, _yaw, blend);
        _smoothPitch = Mathf.Lerp(_smoothPitch, _pitch, blend);
        _smoothDistance = Mathf.Lerp(_smoothDistance, _distance, blend);
        _smoothedTarget = _smoothedTarget.Lerp(_target, blend);
        var direction = new Vector3(MathF.Sin(_smoothYaw) * MathF.Cos(_smoothPitch), MathF.Sin(_smoothPitch), -MathF.Cos(_smoothYaw) * MathF.Cos(_smoothPitch));
        if (_interior)
        {
            _camera.GlobalPosition = _target;
            _camera.LookAt(_target + direction, Vector3.Up);
        }
        else
        {
            var right = new Vector3(-MathF.Cos(_smoothYaw), 0, -MathF.Sin(_smoothYaw));
            var center = _smoothedTarget + right * (_uiVisible ? _smoothDistance * .085f : 0);
            _cameraClearance = ExteriorClearance(center, direction);
            _camera.GlobalPosition = center + direction * Math.Max(_smoothDistance, _cameraClearance);
            _camera.LookAt(center, Vector3.Up);
        }
        _floor.Visible = _interior || _camera.GlobalPosition.Y > .03f;
        _inspectionLight.Visible = !_interior && !_floor.Visible;
    }

    private float ExteriorClearance(Vector3 center, Vector3 direction)
    {
        var clearance = 0f;
        var aspect = _viewport.Size.X / (float)Math.Max(1, _viewport.Size.Y);
        var nearHalfHeight = _camera.Near * MathF.Tan(Mathf.DegToRad(_camera.Fov) / 2);
        var eyeRadius = Math.Max(.10f, MathF.Sqrt(_camera.Near * _camera.Near + nearHalfHeight * nearHalfHeight * (1 + aspect * aspect)) + .01f);
        foreach (var (mesh, authoredBounds) in _cameraObstacles)
        {
            if (!mesh.IsVisibleInTree() || authoredBounds.Size.LengthSquared() < .000001f) continue;
            var inverse = mesh.GlobalTransform.AffineInverse();
            // Row lengths transform the world-space camera sphere into conservative
            // local half-extents, including rotated/scaled opening assemblies.
            var rows = inverse.Basis.Transposed();
            var margin = new Vector3(rows.X.Length(), rows.Y.Length(), rows.Z.Length()) * eyeRadius;
            var bounds = new Aabb(authoredBounds.Position - margin, authoredBounds.Size + margin * 2);
            var origin = inverse * center;
            var ray = inverse.Basis * direction;
            var near = float.NegativeInfinity;
            var far = float.PositiveInfinity;
            var intersects = true;
            for (var axis = 0; axis < 3; axis++)
            {
                if (Math.Abs(ray[axis]) < .000001f)
                {
                    if (origin[axis] < bounds.Position[axis] || origin[axis] > bounds.End[axis])
                    { intersects = false; break; }
                    continue;
                }
                var first = (bounds.Position[axis] - origin[axis]) / ray[axis];
                var last = (bounds.End[axis] - origin[axis]) / ray[axis];
                near = Math.Max(near, Math.Min(first, last));
                far = Math.Min(far, Math.Max(first, last));
                if (far < near) { intersects = false; break; }
            }
            if (intersects && far >= 0 && far < 14) clearance = Math.Max(clearance, far + .002f);
        }
        return clearance;
    }

    public void SelectView(string view)
    {
        _view = view;
        _autoOrbit = false;
        _interior = view is "cockpit" or "rear-cabin";
        _target = new Vector3(0, .74f, 0);
        _camera.Fov = _interior ? 76 : 42;
        _camera.CullMask = (1u << 20) - 1;
        if (_interior) _camera.CullMask &= ~VehicleVisualRig.CockpitExteriorRenderLayer;
        if (_presentation is not null) _presentation.MirrorsEnabled = _interior;
        (_yaw, _pitch, _distance) = view switch
        {
            "front" => (0, .12f, 6.4f), "rear" => (Mathf.Pi, .12f, 6.4f),
            "left" => (-Mathf.Pi / 2, .12f, 8.6f), "right" => (Mathf.Pi / 2, .12f, 8.6f),
            "top" => (Mathf.Pi / 2, 1.55f, 8.1f), "underside" => (Mathf.Pi / 2, -1.35f, 8.1f),
            "engine" => (-.18f, .97f, 2.75f), "luggage" => (Mathf.Pi, .73f, 2.8f),
            "cockpit" => (0, -.42f, 1), "rear-cabin" => (Mathf.Pi, -.22f, 1),
            _ => (-.72f, .24f, 8.2f),
        };
        if (view == "engine") { _target = new Vector3(0, .8f, -1.6f); _presentation?.SetOpening("Hood_Hinge", true); }
        if (view == "luggage") { _target = new Vector3(0, .75f, 1.82f); _presentation?.SetOpening("Trunk_Hinge", true); }
        if (view == "cockpit") _target = _rig?.CockpitCameraAnchor.GlobalPosition ?? new Vector3(-.35f, 1.05f, -.2f);
        if (view == "rear-cabin") _target = new Vector3(0, 1.15f, .1f);
        // Interior and exterior transitions snap through no body surfaces.
        _smoothedTarget = _target;
        _smoothYaw = _yaw; _smoothPitch = _pitch; _smoothDistance = _distance;
        UpdateCamera(1);
        _metrics?.BeginCase(_view, _lighting);
        _viewLabel.Text = ViewTitle(view);
        UpdateInterface();
        PublishState();
    }

    private static readonly string[] ViewOrder = ["overview", "front", "rear", "left", "right", "top", "underside", "cockpit", "rear-cabin", "engine", "luggage"];
    private void CycleView(int step) => SelectView(ViewOrder[(Array.IndexOf(ViewOrder, _view) + step + ViewOrder.Length) % ViewOrder.Length]);
    private void SetAllOpen(bool open)
    {
        if (_presentation is null) return;
        foreach (var name in EnduranceSedanPresentation.OpeningNames) _presentation.SetOpening(name, open);
        UpdateInterface();
    }
    private void ToggleOrbit() { if (_interior) SelectView("overview"); _autoOrbit = !_autoOrbit; UpdateInterface(); }
    private const string ShowControlsNotice = "F1 / R3 to show controls";
    private void SetInterfaceVisible(bool visible)
    {
        _uiVisible = visible; _interface.Visible = visible;
        GetViewport().GuiReleaseFocus();
        if (visible)
        {
            _homeButton.GrabFocus();
            if (_notice.Text == ShowControlsNotice)
            {
                _noticeRemaining = 0;
                _noticePanel.Hide();
            }
        }
        else Notice(ShowControlsNotice);
    }
    private void Notice(string message)
    {
        _notice.Text = message;
        _notice.TooltipText = message;
        _noticePanel.Show();
        _noticeRemaining = 5;
    }
    private void SavePhoto()
    {
        var folder = ProjectSettings.GlobalizePath("user://showroom/photos");
        System.IO.Directory.CreateDirectory(folder);
        var path = System.IO.Path.Combine(folder, $"meridian-{DateTime.UtcNow:yyyyMMdd-HHmmss-fff}.png");
        using var texture = _viewport.GetTexture();
        using var image = texture.GetImage();
        var result = image.SavePng(path);
        if (result != Error.Ok) { Notice("Photo could not be saved"); GD.PushError($"Showroom photo: {result}"); return; }
        _lastPhoto = path;
        Notice("Photo saved  ·  " + path);
        PublishState();
    }

    private void PublishState()
    {
        if (!Automation.AutomationInspection.Enabled) return;
        _state["asset_id"] = AssetId; _state["view"] = _view; _state["lighting"] = _lighting;
        _state["camera_x"] = _camera.GlobalPosition.X; _state["camera_y"] = _camera.GlobalPosition.Y; _state["camera_z"] = _camera.GlobalPosition.Z;
        _state["yaw"] = _yaw; _state["pitch"] = _pitch; _state["distance"] = _distance;
        _state["target_x"] = _target.X; _state["target_y"] = _target.Y; _state["target_z"] = _target.Z;
        _state["ui_visible"] = _uiVisible; _state["auto_orbit"] = _autoOrbit;
        _state["lighting_popup_open"] = _lightingPopup.Visible; _state["lighting_popup_index"] = _lightingPopup.GetFocusedItem();
        _state["body_frozen"] = _display.Freeze; _state["private_world"] = _viewport.OwnWorld3D;
        _state["world_instance_id"] = _worldInstanceId; _state["vehicle_instance_id"] = _display.GetInstanceId();
        _state["rendered_frames"] = _drawnFrames; _state["run_paused"] = GetTree().Paused;
        _state["floor_visible"] = _floor.Visible; _state["photo_path"] = _lastPhoto;
        _state["display_speed_mps"] = _display.SpeedMetersPerSecond;
        _state["viewport_width"] = _viewport.Size.X; _state["viewport_height"] = _viewport.Size.Y;
        _state["camera_clearance_m"] = _interior ? 0 : _cameraClearance;
        _metrics?.Publish(_state);
        _state["headlights"] = _presentation?.HeadlightsOn ?? _rig?.HeadlightsOn ?? false;
        _state["wipers"] = _presentation?.WipersOn ?? false; _state["hazards"] = _presentation?.HazardsOn ?? false;
        foreach (var name in EnduranceSedanPresentation.OpeningNames)
        {
            _state["opening_" + name] = _presentation?.OpeningTarget(name) ?? false;
            _state["angle_" + name] = _presentation?.OpeningAngleDegrees(name) ?? 0;
        }
    }

    public void Close()
    {
        if (_closing) return;
        _closing = true;
        if (_host is null) { _ = _shutdown.Request(this, () => Task.CompletedTask, 0, false); return; }
        RestoreHost();
        QueueFree();
    }

    private void RestoreHost()
    {
        if (_host is null) return;
        GetViewport().GuiReleaseFocus();
        foreach (var (node, mode) in _hostModes) if (IsInstanceValid(node)) node.ProcessMode = mode;
        foreach (var (layer, visible) in _hostLayers) if (IsInstanceValid(layer)) layer.Visible = visible;
        _host.Visible = _hostVisible;
        GetTree().Paused = _previousPause;
        Closed?.Invoke();
    }

    public override void _ExitTree()
    {
        if (_drawConnected) { RenderingServer.FramePostDraw -= OnFrameDrawn; _drawConnected = false; }
        if (_windowConnected && IsInstanceValid(_window)) { _window!.SizeChanged -= ResizeRenderViewport; _windowConnected = false; }
        _state.Dispose(); _environment?.Dispose(); _skyMaterial?.Dispose(); _metrics?.Dispose();
    }

    private static IEnumerable<Node> Walk(Node root)
    {
        yield return root;
        for (var i = 0; i < root.GetChildCount(); i++)
            foreach (var child in Walk(root.GetChild(i))) yield return child;
    }
}
