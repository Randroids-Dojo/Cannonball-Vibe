using Godot;
using Cannonball.Core.Runs;
using Cannonball.Game.Input;

namespace Cannonball.Game.UI;

public sealed partial class PrototypeHud : CanvasLayer
{
    public event Action? TripOverviewRequested;
    public event Action? RestartRunRequested;

    private Label _speed = null!;
    private Label _distance = null!;
    private Label _streaming = null!;
    private ColorRect _driverMenu = null!;
    private Label _menuStatus = null!;
    private Button _restartRun = null!;
    private bool _restartConfirmationArmed;

    public override void _Ready()
    {
        ProcessMode = ProcessModeEnum.Always;
        SetMeta("automation_id", "hud.root");
        AddChild(new ColorRect
        {
            Name = "TelemetryBackground",
            Position = new Vector2(24, 24),
            Size = new Vector2(390, 152),
            Color = new Color(0.02f, 0.025f, 0.04f, 0.82f),
        });
        var title = CreateLabel("Title", "hud.title", new Vector2(44, 38), 24);
        title.Text = "CANNONBALL // M0 FEEL";
        _speed = CreateLabel("Speed", "hud.speed", new Vector2(44, 72), 32);
        _distance = CreateLabel("Distance", "hud.distance", new Vector2(44, 112), 18);
        _streaming = CreateLabel("Streaming", "hud.streaming", new Vector2(44, 140), 14);
        var help = CreateLabel("Help", "hud.help", new Vector2(24, 1030), 16);
        help.Text = "W/RT go  S brake  LT brake/reverse  A D/LS steer  Q/B alt reverse  SPACE/X handbrake  B/LB rear  V/R3 camera  M/VIEW map  R/Y recover  ESC/MENU pause";
        CreateDriverMenu();
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event is InputEventKey { Echo: true })
        {
            return;
        }
        if (@event.IsActionPressed(GameInputMap.PauseMenu, allowEcho: false, exactMatch: true))
        {
            if (_driverMenu.Visible)
            {
                SetDriverMenuOpen(false);
            }
            else if (!GetTree().Paused)
            {
                SetDriverMenuOpen(true);
            }
            GetViewport().SetInputAsHandled();
            return;
        }
        if (_driverMenu.Visible &&
            @event.IsActionPressed("ui_cancel", allowEcho: false, exactMatch: true))
        {
            if (_restartConfirmationArmed)
            {
                CancelRestartConfirmation();
            }
            else
            {
                SetDriverMenuOpen(false);
            }
            GetViewport().SetInputAsHandled();
        }
    }

    public void UpdateTelemetry(
        float metersPerSecond,
        double distanceMeters,
        double routeLengthMeters,
        int chunks,
        double originMeters,
        AssistProfile assistProfile)
    {
        _speed.Text = $"{metersPerSecond * 2.236936f,3:0} MPH";
        // The total is the loaded route's length: 25 miles on the Boulder
        // fixture, 500 on the first continental segment.
        _distance.Text =
            $"{distanceMeters / 1609.344:0.00} / {routeLengthMeters / 1609.344:0.00} MILES";
        _streaming.Text =
            $"{assistProfile.ToString().ToUpperInvariant()}  //  STREAM {chunks} CHUNKS  //  ORIGIN {originMeters / 1000.0:0.0} KM";
    }

    private Label CreateLabel(string name, string automationId, Vector2 position, int fontSize)
    {
        var label = new Label { Name = name, Position = position };
        label.SetMeta("automation_id", automationId);
        label.AddThemeFontSizeOverride("font_size", fontSize);
        AddChild(label);
        return label;
    }

    private void CreateDriverMenu()
    {
        _driverMenu = new ColorRect
        {
            Name = "DriverMenu",
            Position = new Vector2(660, 188),
            Size = new Vector2(600, 704),
            Color = new Color(0.018f, 0.024f, 0.04f, 0.96f),
            Visible = false,
            MouseFilter = Control.MouseFilterEnum.Stop,
        };
        _driverMenu.SetMeta("automation_id", "menu.driver.root");
        AddChild(_driverMenu);

        var title = CreateMenuLabel("DriverMenuTitle", "menu.driver.title", "DRIVER MENU", 40, 48);
        title.HorizontalAlignment = HorizontalAlignment.Center;
        var subtitle = CreateMenuLabel(
            "DriverMenuSubtitle",
            "menu.driver.subtitle",
            "Trip controls and driving options",
            21,
            112);
        subtitle.HorizontalAlignment = HorizontalAlignment.Center;

        CreateMenuButton(
            "ResumeDrive",
            "menu.driver.resume",
            "RESUME DRIVE",
            198,
            () => SetDriverMenuOpen(false));
        CreateMenuButton(
            "DrivingOptions",
            "menu.driver.options",
            "DRIVING OPTIONS",
            290,
            () =>
            {
                CancelRestartConfirmation();
                SetMenuStatus("Driving options selected");
            });
        CreateMenuButton(
            "TripOverview",
            "menu.driver.trip-overview",
            "TRIP OVERVIEW (PAUSES)",
            382,
            () =>
            {
                CancelRestartConfirmation();
                OpenTripOverview();
            });
        _restartRun = CreateMenuButton(
            "RestartRun",
            "menu.driver.restart-run",
            "RESTART RUN",
            474,
            ArmOrConfirmRestartRun);

        _menuStatus = CreateMenuLabel(
            "DriverMenuStatus",
            "menu.driver.status",
            "Paused at current route position",
            18,
            566);
        _menuStatus.HorizontalAlignment = HorizontalAlignment.Center;

        var hint = CreateMenuLabel(
            "DriverMenuHint",
            "menu.driver.hint",
            "ESC/B closes  //  arrows/D-pad move  //  ENTER/A selects",
            16,
            646);
        hint.HorizontalAlignment = HorizontalAlignment.Center;
        SetDriverMenuState(false, "closed");
    }

    private Label CreateMenuLabel(
        string name,
        string automationId,
        string text,
        int fontSize,
        float y)
    {
        var label = new Label
        {
            Name = name,
            Position = new Vector2(36, y),
            Size = new Vector2(528, 52),
            Text = text,
        };
        label.SetMeta("automation_id", automationId);
        label.AddThemeFontSizeOverride("font_size", fontSize);
        _driverMenu.AddChild(label);
        return label;
    }

    private Button CreateMenuButton(
        string name,
        string automationId,
        string text,
        float y,
        Action onPressed)
    {
        var button = new Button
        {
            Name = name,
            Position = new Vector2(88, y),
            Size = new Vector2(424, 68),
            Text = text,
            FocusMode = Control.FocusModeEnum.All,
        };
        button.SetMeta("automation_id", automationId);
        button.AddThemeFontSizeOverride("font_size", 22);
        button.Pressed += onPressed;
        _driverMenu.AddChild(button);
        return button;
    }

    private void SetDriverMenuOpen(bool open)
    {
        CancelRestartConfirmation();
        if (!open)
        {
            GetTree().Paused = false;
        }
        _driverMenu.Visible = open;
        if (open)
        {
            _driverMenu.GetNode<Button>("ResumeDrive").GrabFocus();
            SetMenuStatus("Paused at current route position");
            GetTree().Paused = true;
        }
        else
        {
            SetDriverMenuState(false, "closed");
        }
    }

    private void SetMenuStatus(string status)
    {
        _menuStatus.Text = status;
        SetDriverMenuState(true, status);
    }

    private void OpenTripOverview()
    {
        SetDriverMenuOpen(false);
        TripOverviewRequested?.Invoke();
    }

    private void ArmOrConfirmRestartRun()
    {
        if (!_restartConfirmationArmed)
        {
            _restartConfirmationArmed = true;
            _restartRun.Text = "CONFIRM RESTART RUN";
            SetMenuStatus("Press again to discard current run progress");
            return;
        }

        SetDriverMenuOpen(false);
        RestartRunRequested?.Invoke();
    }

    private void CancelRestartConfirmation()
    {
        _restartConfirmationArmed = false;
        if (_restartRun is not null)
        {
            _restartRun.Text = "RESTART RUN";
        }
    }

    private void SetDriverMenuState(bool open, string status)
    {
        UpdateDriverMenuState(open, status);
    }

    private void UpdateDriverMenuState(bool open, string status)
    {
        _driverMenu.SetMeta(
            "automation_state",
            new Godot.Collections.Dictionary
            {
                ["open"] = open,
                ["status"] = status,
                ["button_count"] = 4,
                ["simulation_paused"] = open,
                ["restart_confirmation_armed"] = _restartConfirmationArmed,
            });
    }
}
