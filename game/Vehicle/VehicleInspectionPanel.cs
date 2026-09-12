using Cannonball.Game.Input;
using Godot;

namespace Cannonball.Game.Vehicle;

/// <summary>Parked inspection and selection, reachable by keyboard and the existing controller UI contract.</summary>
public partial class VehicleInspectionPanel : CanvasLayer
{
    private CannonballVehicle _vehicle = null!;
    private Control _root = null!;
    private PanelContainer _panel = null!;
    private Label _hint = null!;
    private Label _state = null!;
    private OptionButton _vehicles = null!;
    private PopupMenu _vehiclePopup = null!;
    private Button _close = null!;
    private bool _previousFreeze;
    private bool _previousAutopilot;
    private double _stateElapsed;
    private double _messageTime;
    private readonly Dictionary<string, CheckButton> _openingButtons = new(StringComparer.Ordinal);
    private readonly Godot.Collections.Dictionary _automationState = new();

    public event Action<string>? VehicleSelected;
    public bool IsOpen => _vehicle.InspectionActive;
    public void Configure(CannonballVehicle vehicle) => _vehicle = vehicle;

    public override void _Ready()
    {
        Name = "VehicleInspectionPanel";
        Layer = 18;
        ProcessMode = ProcessModeEnum.Always;
        SetMeta("automation_id", "vehicle.inspection.panel");
        SetMeta("automation_state", _automationState);
        _root = new Control { Name = "VehicleInspectionRoot", MouseFilter = Control.MouseFilterEnum.Ignore };
        AddChild(_root);
        _root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        _hint = new Label { Text = "F2 / RB  Vehicle", MouseFilter = Control.MouseFilterEnum.Ignore };
        _hint.AddThemeFontSizeOverride("font_size", 16);
        _root.AddChild(_hint);
        _hint.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.BottomRight);
        _hint.OffsetLeft = -215;
        _hint.OffsetRight = -22;
        _hint.OffsetTop = -38;
        _hint.OffsetBottom = -12;
        _panel = new PanelContainer { Name = "ParkedInspection", Visible = false };
        _panel.SetMeta("automation_id", "vehicle.inspection.window");
        _root.AddChild(_panel);
        _panel.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.CenterRight);
        _panel.OffsetLeft = -520;
        _panel.OffsetRight = -20;
        _panel.OffsetTop = -315;
        _panel.OffsetBottom = 315;
        using var style = new StyleBoxFlat { BgColor = new Color(0.035f, 0.045f, 0.055f, 0.97f), ContentMarginLeft = 20, ContentMarginRight = 20, ContentMarginTop = 16, ContentMarginBottom = 16 };
        _panel.AddThemeStyleboxOverride("panel", style);
        var scroll = new ScrollContainer { HorizontalScrollMode = ScrollContainer.ScrollMode.Disabled };
        _panel.AddChild(scroll);
        var column = new VBoxContainer { SizeFlagsHorizontal = Control.SizeFlags.ExpandFill };
        column.AddThemeConstantOverride("separation", 10);
        scroll.AddChild(column);
        var title = new Label { Text = "Vehicle inspection" };
        title.AddThemeFontSizeOverride("font_size", 25);
        column.AddChild(title);
        _state = new Label { Text = "Parked", AutowrapMode = TextServer.AutowrapMode.WordSmart };
        _state.SetMeta("automation_id", "vehicle.inspection.status");
        column.AddChild(_state);
        var presentation = _vehicle.VisualRig?.Presentation;
        if (presentation is not null)
        {
            var equipment = new GridContainer { Columns = 2 };
            column.AddChild(equipment);
            AddButton(equipment, "Headlights  [H]", "vehicle.controls.headlights", presentation.CycleHeadlampMode);
            AddButton(equipment, "Wipers  [T]", "vehicle.controls.wipers", () => presentation.SetWipers(!presentation.WipersOn));
            AddButton(equipment, "Left signal  [,]", "vehicle.controls.signal-left", () => presentation.SetIndicator(-1));
            AddButton(equipment, "Right signal  [.]", "vehicle.controls.signal-right", () => presentation.SetIndicator(1));
            AddButton(equipment, "Hazards  [/]", "vehicle.controls.hazards", () => presentation.SetHazards(!presentation.HazardsOn));
            AddButton(equipment, "Chase / cockpit", "vehicle.controls.camera", _vehicle.ToggleCameraMode);
            column.AddChild(new HSeparator());
            var openings = new GridContainer { Columns = 2 };
            column.AddChild(openings);
            var labels = new[] { "Driver door", "Front passenger", "Rear left door", "Rear right door", "Hood", "Trunk" };
            for (var i = 0; i < EnduranceSedanPresentation.OpeningNames.Length; i++)
            {
                var name = EnduranceSedanPresentation.OpeningNames[i];
                var button = new CheckButton { Text = labels[i], FocusMode = Control.FocusModeEnum.All, SizeFlagsHorizontal = Control.SizeFlags.ExpandFill };
                button.SetMeta("automation_id", "vehicle.opening." + name.ToLowerInvariant().Replace('_', '-'));
                button.Toggled += value => presentation.SetOpening(name, value);
                openings.AddChild(button);
                _openingButtons[name] = button;
            }
        }
        column.AddChild(new HSeparator());
        column.AddChild(new Label { Text = "Select vehicle at the current road position" });
        _vehicles = new OptionButton { Name = "VehicleChoices", FocusMode = Control.FocusModeEnum.All };
        _vehiclePopup = _vehicles.GetPopup();
        _vehicles.SetMeta("automation_id", "vehicle.selection.options");
        _vehicles.AddItem("Meridian S8R — endurance sedan", 0);
        _vehicles.AddItem("Hero GT", 1);
        _vehicles.AddItem("Graybox", 2);
        _vehicles.Select(_vehicle.UsesGrayboxVisual ? 2 : _vehicle.RigSetup.AssetId == "endurance-sedan" ? 0 : 1);
        column.AddChild(_vehicles);
        AddButton(column, "Use selected vehicle", "vehicle.selection.apply", () =>
        {
            var selected = _vehicles.GetSelectedId() switch { 0 => "endurance-sedan", 2 => "graybox", _ => "hero-gt" };
            Close();
            VehicleSelected?.Invoke(selected);
        });
        _close = AddButton(column, "Return to driving  [F2 / RB / Esc / B]", "vehicle.inspection.close", Close);
        UpdateState();
    }

    public override void _ShortcutInput(InputEvent @event)
    {
        // The later-created HUD receives unhandled Escape first. While this
        // panel is open, route its close shortcut after GUI popup handling but
        // before the HUD can open the pause menu behind the inspection panel.
        if (IsOpen) _UnhandledInput(@event);
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event.IsEcho()) return;
        if (@event.IsActionPressed(GameInputMap.VehicleInspection))
        {
            if (IsOpen) Close(); else Open();
            GetViewport().SetInputAsHandled();
        }
        else if (IsOpen && (@event.IsActionPressed(GameInputMap.UiCancel) || @event.IsActionPressed(GameInputMap.PauseMenu)))
        {
            Close();
            // Escape also maps to the HUD's normal pause menu.
            Godot.Input.ActionRelease(GameInputMap.PauseMenu);
            GetViewport().SetInputAsHandled();
        }
    }

    public bool Open()
    {
        if (IsOpen) return true;
        if (GetTree().Paused || _vehicle.SpeedMetersPerSecond > 0.5f)
        {
            _hint.Text = "Stop the vehicle to inspect";
            _messageTime = 3;
            return false;
        }
        _previousFreeze = _vehicle.Freeze;
        _previousAutopilot = _vehicle.AutopilotEnabled;
        _vehicle.DrivingInputController.ClearAndSuppress("vehicle_inspection");
        _vehicle.AutopilotEnabled = false;
        _vehicle.InspectionActive = true;
        _vehicle.Freeze = true;
        _panel.Visible = true;
        _close.GrabFocus();
        UpdateState();
        return true;
    }

    public void Close()
    {
        if (!IsOpen) return;
        _vehicle.DrivingInputController.ClearAndSuppress("vehicle_inspection_closed");
        _panel.Visible = false;
        _vehicle.InspectionActive = false;
        _vehicle.AutopilotEnabled = _previousAutopilot;
        _vehicle.Freeze = _previousFreeze;
        _vehicle.ResetPhysicsInterpolation();
        GetViewport().GuiReleaseFocus();
        UpdateState();
    }

    public override void _Process(double delta)
    {
        if (_messageTime > 0)
        {
            _messageTime -= delta;
            if (_messageTime <= 0) _hint.Text = "F2 / RB  Vehicle";
        }
        if (!IsOpen) return;
        _stateElapsed += delta;
        if (_stateElapsed < 0.1) return;
        _stateElapsed %= 0.1;
        UpdateState();
    }

    private void UpdateState()
    {
        if (Automation.AutomationInspection.Enabled)
        {
            _automationState["open"] = IsOpen;
            _automationState["selected_asset"] = _vehicle.UsesGrayboxVisual ? "graybox" : _vehicle.RigSetup.AssetId;
            _automationState["body_frozen"] = _vehicle.Freeze;
            _automationState["camera_mode"] = _vehicle.CurrentCameraMode;
            _automationState["user_data_directory"] = OS.GetUserDataDir();
            _automationState["selection_popup_open"] = _vehiclePopup.Visible;
            _automationState["selection_popup_index"] = _vehiclePopup.GetFocusedItem();
        }
        if (_vehicle.VisualRig?.Presentation is { } presentation)
        {
            _state.Text = $"Meridian S8R  ·  Parked\nHeadlights: {(presentation.HeadlampMode == 0 ? "Auto" : presentation.HeadlampMode == 1 ? "On" : "Off")}  ·  Wipers: {(presentation.WipersOn ? "On" : "Off")}  ·  Hazards: {(presentation.HazardsOn ? "On" : "Off")}";
            foreach (var (name, button) in _openingButtons) button.SetPressedNoSignal(presentation.OpeningTarget(name));
            if (Automation.AutomationInspection.Enabled)
            {
                _automationState["headlamp_mode"] = presentation.HeadlampMode;
                _automationState["wipers"] = presentation.WipersOn;
                _automationState["hazards"] = presentation.HazardsOn;
                _automationState["indicator_direction"] = presentation.IndicatorDirection;
                foreach (var name in EnduranceSedanPresentation.OpeningNames)
                {
                    _automationState["opening_" + name] = presentation.OpeningTarget(name);
                    _automationState["angle_" + name] = presentation.OpeningAngleDegrees(name);
                }
            }
        }
        else _state.Text = _vehicle.UsesGrayboxVisual ? "Graybox  ·  Parked" : "Hero GT  ·  Parked";
    }

    private static Button AddButton(Node parent, string text, string automationId, Action pressed)
    {
        var button = new Button { Text = text, FocusMode = Control.FocusModeEnum.All, SizeFlagsHorizontal = Control.SizeFlags.ExpandFill, CustomMinimumSize = new Vector2(0, 37) };
        button.SetMeta("automation_id", automationId);
        button.Pressed += pressed;
        parent.AddChild(button);
        return button;
    }

    public override void _ExitTree() => _automationState.Dispose();
}
