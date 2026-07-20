using Cannonball.Core.Simulation;
using Godot;

namespace Cannonball.Game.UI;

public sealed partial class TripMapHud : CanvasLayer
{
    public event Action? Closed;

    private ColorRect _root = null!;
    private TripMapCanvas _canvas = null!;
    private Label _summary = null!;
    private Label _inspection = null!;
    private Label _selection = null!;
    private Button _close = null!;
    private TripMapProjectionState? _state;
    private int _alternativeIndex;
    private int _featureIndex;

    public bool IsOpen => _root.Visible;

    public override void _Ready()
    {
        ProcessMode = ProcessModeEnum.Always;
        SetMeta("automation_id", "trip-map.layer");
        _root = new ColorRect
        {
            Name = "TripMapRoot",
            Color = new Color("0c121c"),
            Visible = false,
            MouseFilter = Control.MouseFilterEnum.Stop,
            ProcessMode = ProcessModeEnum.Always,
        };
        _root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        _root.SetMeta("automation_id", "trip-map.root");
        AddChild(_root);

        var title = Label("Title", "trip-map.title", "TRIP OVERVIEW", 32);
        title.Position = new Vector2(42, 30);
        title.Size = new Vector2(600, 46);
        var pauseNotice = Label(
            "PauseNotice",
            "trip-map.pause-notice",
            "Opening Trip Overview pauses driving and the run clock.",
            17);
        pauseNotice.Position = new Vector2(44, 77);
        pauseNotice.Size = new Vector2(800, 32);

        _canvas = new TripMapCanvas
        {
            Name = "MapCanvas",
            Position = new Vector2(36, 122),
            Size = new Vector2(1390, 890),
        };
        _canvas.SetMeta("automation_id", "trip-map.canvas");
        _root.AddChild(_canvas);

        var sidePanel = new ColorRect
        {
            Name = "InformationPanel",
            Position = new Vector2(1450, 28),
            Size = new Vector2(438, 984),
            Color = new Color("17202c"),
        };
        sidePanel.SetMeta("automation_id", "trip-map.information");
        _root.AddChild(sidePanel);

        _summary = PanelLabel(sidePanel, "Summary", "trip-map.summary", 22, 28, 280);
        _selection = PanelLabel(sidePanel, "Selection", "trip-map.selection", 18, 330, 150);
        _inspection = PanelLabel(sidePanel, "Inspection", "trip-map.inspection", 18, 500, 200);

        AddButton(sidePanel, "PreviousItem", "trip-map.previous", "PREVIOUS", 724,
            () => ChangeInspection(-1));
        AddButton(sidePanel, "NextItem", "trip-map.next", "NEXT", 784,
            () => ChangeInspection(1));
        AddButton(sidePanel, "ZoomOut", "trip-map.zoom-out", "−", 850,
            () => { _canvas.ZoomBy(0.8f); UpdateAutomationState(); }, 82, 30);
        AddButton(sidePanel, "Recenter", "trip-map.recenter", "RECENTER", 850,
            () => { _canvas.Recenter(); UpdateAutomationState(); }, 178, 122);
        AddButton(sidePanel, "ZoomIn", "trip-map.zoom-in", "+", 850,
            () => { _canvas.ZoomBy(1.25f); UpdateAutomationState(); }, 82, 314);
        _close = AddButton(sidePanel, "Close", "trip-map.close", "RETURN TO DRIVE", 916,
            Close);
        UpdateAutomationState();
    }

    public override void _Process(double delta)
    {
        if (!IsOpen)
        {
            return;
        }
        const float panStep = 14;
        if (Godot.Input.IsActionPressed("trip_map_pan_left")) _canvas.PanBy(Vector2.Left * panStep);
        if (Godot.Input.IsActionPressed("trip_map_pan_right")) _canvas.PanBy(Vector2.Right * panStep);
        if (Godot.Input.IsActionPressed("trip_map_pan_up")) _canvas.PanBy(Vector2.Up * panStep);
        if (Godot.Input.IsActionPressed("trip_map_pan_down")) _canvas.PanBy(Vector2.Down * panStep);
        if (Godot.Input.IsActionJustPressed("trip_map_zoom_in")) _canvas.ZoomBy(1.25f);
        if (Godot.Input.IsActionJustPressed("trip_map_zoom_out")) _canvas.ZoomBy(0.8f);
        if (Godot.Input.IsActionJustPressed("trip_map_recenter")) _canvas.Recenter();
        if (Godot.Input.IsActionJustPressed("trip_map_previous")) ChangeInspection(-1);
        if (Godot.Input.IsActionJustPressed("trip_map_next")) ChangeInspection(1);
        UpdateAutomationState();
    }

    public override void _UnhandledKeyInput(InputEvent @event)
    {
        if (!IsOpen || @event is not InputEventKey { Pressed: true, Echo: false, Keycode: Key.Escape })
        {
            return;
        }
        Close();
        GetViewport().SetInputAsHandled();
    }

    public void Open(TripMapProjectionState state)
    {
        _state = state;
        _alternativeIndex = 0;
        _featureIndex = 0;
        _canvas.SetState(state);
        _root.Visible = true;
        UpdateText();
        UpdateAutomationState();
        _close.GrabFocus();
        GetTree().Paused = true;
    }

    public void Close()
    {
        if (!IsOpen)
        {
            return;
        }
        _root.Visible = false;
        GetTree().Paused = false;
        UpdateAutomationState();
        Closed?.Invoke();
    }

    private void ChangeInspection(int delta)
    {
        if (_state is null)
        {
            return;
        }
        if (_state.Alternatives.Count > 0)
        {
            _alternativeIndex = PositiveModulo(_alternativeIndex + delta, _state.Alternatives.Count);
        }
        if (_state.UpcomingFeatures.Count > 0)
        {
            _featureIndex = PositiveModulo(_featureIndex + delta, _state.UpcomingFeatures.Count);
        }
        UpdateText();
        UpdateAutomationState();
    }

    private void UpdateText()
    {
        if (_state is null)
        {
            return;
        }
        var completedMiles = _state.DistanceCompletedMeters / 1609.344;
        var remainingMiles = _state.DistanceRemainingMeters / 1609.344;
        var eta = TimeSpan.FromSeconds(_state.EstimatedRemainingSeconds);
        var etaHours = (int)Math.Floor(eta.TotalHours);
        _summary.Text =
            $"{_state.StartLabel}\nTO  {_state.DestinationLabel}\n\n" +
            $"{completedMiles:0.0} mi completed\n{remainingMiles:0.0} mi remaining\n" +
            $"ETA  {etaHours:0}:{eta.Minutes:00}\n" +
            $"{_state.TravelMode.DisplayName} // {_state.AssistProfile} estimate";

        _selection.Text = _state.Alternatives.Count == 0
            ? "ROUTE ALTERNATIVES\nNo alternate route at upcoming junctions"
            : $"ROUTE ALTERNATIVE {_alternativeIndex + 1}/{_state.Alternatives.Count}\n" +
                _state.Alternatives[_alternativeIndex].Label;

        if (_state.UpcomingFeatures.Count == 0)
        {
            _inspection.Text = "UPCOMING\nNo exits, transfers, or services on this segment";
        }
        else
        {
            var feature = _state.UpcomingFeatures[_featureIndex];
            var services = feature.Services.Count == 0
                ? ""
                : $"\nServices: {string.Join(", ", feature.Services)}";
            var distance = Math.Max(0,
                (feature.RouteDistanceMeters - _state.DistanceCompletedMeters) / 1609.344);
            _inspection.Text =
                $"UPCOMING {_featureIndex + 1}/{_state.UpcomingFeatures.Count}\n" +
                $"{feature.Title}\n{feature.Detail}\n{distance:0.0} mi ahead{services}";
        }
    }

    private void UpdateAutomationState()
    {
        _root.SetMeta(
            "automation_state",
            new Godot.Collections.Dictionary
            {
                ["open"] = IsOpen,
                ["simulation_paused"] = IsOpen && GetTree().Paused,
                ["zoom"] = _canvas?.Zoom ?? 1,
                ["pan_x"] = _canvas?.Pan.X ?? 0,
                ["pan_y"] = _canvas?.Pan.Y ?? 0,
                ["alternative_count"] = _state?.Alternatives.Count ?? 0,
                ["feature_count"] = _state?.UpcomingFeatures.Count ?? 0,
                ["service_stop_count"] = _state?.SelectedServiceStops.Count ?? 0,
                ["distance_completed_m"] = _state?.DistanceCompletedMeters ?? 0,
                ["distance_remaining_m"] = _state?.DistanceRemainingMeters ?? 0,
                ["estimated_remaining_s"] = _state?.EstimatedRemainingSeconds ?? 0,
                ["geometry_lod"] = _state?.GeometryLod ?? 0,
                ["projected_point_count"] = _state?.ProjectedPointCount ?? 0,
                ["draw_batch_count"] = _canvas?.DrawBatchCount ?? 0,
                ["travel_mode_id"] = _state?.TravelMode.Id ?? "real-time",
                ["travel_time_scale"] = _state?.TravelMode.EffectiveTimeScale ?? 1,
            });
    }

    private Label Label(string name, string automationId, string text, int fontSize)
    {
        var label = new Label { Name = name, Text = text };
        label.SetMeta("automation_id", automationId);
        label.AddThemeFontSizeOverride("font_size", fontSize);
        _root.AddChild(label);
        return label;
    }

    private static Label PanelLabel(
        Control parent,
        string name,
        string automationId,
        int fontSize,
        float y,
        float height)
    {
        var label = new Label
        {
            Name = name,
            Position = new Vector2(28, y),
            Size = new Vector2(382, height),
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
        };
        label.SetMeta("automation_id", automationId);
        label.AddThemeFontSizeOverride("font_size", fontSize);
        parent.AddChild(label);
        return label;
    }

    private static Button AddButton(
        Control parent,
        string name,
        string automationId,
        string text,
        float y,
        Action pressed,
        float width = 382,
        float x = 28)
    {
        var button = new Button
        {
            Name = name,
            Position = new Vector2(x, y),
            Size = new Vector2(width, 52),
            Text = text,
            FocusMode = Control.FocusModeEnum.All,
        };
        button.SetMeta("automation_id", automationId);
        button.AddThemeFontSizeOverride("font_size", 18);
        button.Pressed += pressed;
        parent.AddChild(button);
        return button;
    }

    private static int PositiveModulo(int value, int modulus) => ((value % modulus) + modulus) % modulus;
}
