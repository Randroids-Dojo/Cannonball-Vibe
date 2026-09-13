using Godot;

namespace Cannonball.Game.Vehicle.Showroom;

public partial class VehicleShowroom
{
    private static readonly Color Ink = new("e8ebed"), Muted = new("98a4ad"), Accent = new("d2e19a");

    private void BuildInterface()
    {
        using var theme = new Theme { DefaultFontSize = 20 };
        theme.SetColor("font_color", "Label", Ink);
        theme.SetColor("font_color", "Button", Ink);
        theme.SetColor("font_hover_color", "Button", Colors.White);
        theme.SetColor("font_pressed_color", "Button", new Color("172018"));
        theme.SetColor("font_disabled_color", "Button", new Color("69737a"));
        using var normal = Style(new Color("252c31"), 10, 10);
        using var hover = Style(new Color("354047"), 10, 10);
        using var pressed = Style(Accent, 10, 10);
        using var focus = Style(new Color(0, 0, 0, 0), 10, 10);
        focus.BorderColor = Accent; focus.SetBorderWidthAll(2);
        theme.SetStylebox("normal", "Button", normal);
        theme.SetStylebox("hover", "Button", hover);
        theme.SetStylebox("pressed", "Button", pressed);
        theme.SetStylebox("focus", "Button", focus);
        theme.SetStylebox("disabled", "Button", normal);
        _root.Theme = theme;
        _interface = new Control { MouseFilter = Control.MouseFilterEnum.Ignore };
        _root.AddChild(_interface); _interface.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);

        var headingPanel = new PanelContainer { Position = new Vector2(30, 20), MouseFilter = Control.MouseFilterEnum.Ignore };
        _interface.AddChild(headingPanel);
        using var headingStyle = Style(new Color(.035f, .046f, .053f, .94f), 14, 16);
        headingPanel.AddThemeStyleboxOverride("panel", headingStyle);
        var heading = new VBoxContainer { MouseFilter = Control.MouseFilterEnum.Ignore };
        headingPanel.AddChild(heading);
        Text(heading, "CANNONBALL   /   PRIVATE GARAGE", 17, Muted);
        Text(heading, AssetId == "endurance-sedan" ? "MERIDIAN S8R" : AssetId == "graybox" ? "GRAYBOX" : "HERO GT", 46, Ink);
        Text(heading, AssetId == "endurance-sedan" ? "Endurance specification  ·  Obsidian black" : "Vehicle inspection", 20, Muted);

        var panel = new PanelContainer { MouseFilter = Control.MouseFilterEnum.Stop };
        _interface.AddChild(panel);
        panel.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.RightWide);
        panel.OffsetLeft = -340; panel.OffsetRight = -30; panel.OffsetTop = 30; panel.OffsetBottom = -112;
        using var panelStyle = Style(new Color(.065f, .083f, .095f, .96f), 18, 20);
        panel.AddThemeStyleboxOverride("panel", panelStyle);
        var scroll = new ScrollContainer { HorizontalScrollMode = ScrollContainer.ScrollMode.Disabled, FollowFocus = true };
        scroll.SetMeta("automation_id", "showroom.controls");
        panel.AddChild(scroll);
        var column = new VBoxContainer { SizeFlagsHorizontal = Control.SizeFlags.ExpandFill };
        column.AddThemeConstantOverride("separation", 12); scroll.AddChild(column);
        Text(column, "EXPLORE", 17, Accent);
        var views = Grid(column);
        foreach (var view in new[] { "front", "rear", "left", "right", "top", "underside" })
            Button(views, ViewTitle(view), "showroom.view." + view, () => SelectView(view));
        Separator(column);
        Text(column, "OPEN PANELS", 17, Accent);
        var openings = Grid(column);
        var titles = new[] { "Driver", "Passenger", "Rear left", "Rear right", "Hood", "Trunk" };
        for (var i = 0; i < EnduranceSedanPresentation.OpeningNames.Length; i++)
        {
            var name = EnduranceSedanPresentation.OpeningNames[i];
            var toggle = new CheckButton { Text = titles[i], Disabled = _presentation is null, FocusMode = Control.FocusModeEnum.All, CustomMinimumSize = new Vector2(0, 40) };
            toggle.SetMeta("automation_id", "showroom.opening." + name.ToLowerInvariant().Replace('_', '-'));
            toggle.TooltipText = "Open or close " + titles[i].ToLowerInvariant() + (i < 4 ? " door" : "");
            toggle.Toggled += value => _presentation?.SetOpening(name, value);
            openings.AddChild(toggle); _openingButtons[name] = toggle;
        }
        var all = Grid(column);
        Button(all, "Open all", "showroom.open-all", () => SetAllOpen(true)).Disabled = _presentation is null;
        Button(all, "Close all", "showroom.close-all", () => SetAllOpen(false)).Disabled = _presentation is null;
        Separator(column);
        Text(column, "ATMOSPHERE", 17, Accent);
        _lightingOptions = new OptionButton { CustomMinimumSize = new Vector2(0, 42) };
        _lightingOptions.SetMeta("automation_id", "showroom.lighting");
        foreach (var title in new[] { "Neutral studio", "Daylight", "Night" }) _lightingOptions.AddItem(title);
        _lightingPopup = _lightingOptions.GetPopup();
        _lightingOptions.ItemSelected += index => SetLighting((int)index);
        column.AddChild(_lightingOptions);
        _headlights = Toggle(column, "Headlights", "showroom.headlights", value => { if (_presentation is not null) _presentation.SetHeadlampMode(value ? 1 : 2); else _rig?.SetHeadlights(value); });
        _wipers = Toggle(column, "Wipers", "showroom.wipers", value => _presentation?.SetWipers(value));
        _hazards = Toggle(column, "Hazards", "showroom.hazards", value => _presentation?.SetHazards(value));
        _wipers.Disabled = _hazards.Disabled = _presentation is null;
        Separator(column);
        _orbitButton = Button(column, "Start turntable", "showroom.orbit", ToggleOrbit);
        Button(column, "Save photo", "showroom.photo", SavePhoto).TooltipText = "Save the car view without interface elements";
        Button(column, "Hide controls   F1 / R3", "showroom.hide-ui", () => SetInterfaceVisible(false));
        Button(column, _host is null ? "Exit showroom   Esc" : "Back to inspection   Esc", "showroom.close", Close);

        var lowerPanel = new PanelContainer { MouseFilter = Control.MouseFilterEnum.Ignore };
        _interface.AddChild(lowerPanel); lowerPanel.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.BottomWide);
        lowerPanel.OffsetLeft = 30; lowerPanel.OffsetRight = -365; lowerPanel.OffsetTop = -172; lowerPanel.OffsetBottom = -20;
        using var lowerStyle = Style(new Color(.035f, .046f, .053f, .94f), 14, 16);
        lowerPanel.AddThemeStyleboxOverride("panel", lowerStyle);
        var lower = new VBoxContainer { MouseFilter = Control.MouseFilterEnum.Ignore };
        lowerPanel.AddChild(lower);
        _viewLabel = Text(lower, "Exterior", 21, Ink);
        var compartments = new HBoxContainer(); compartments.AddThemeConstantOverride("separation", 8); lower.AddChild(compartments);
        foreach (var view in new[] { "overview", "cockpit", "rear-cabin", "engine", "luggage" })
        {
            var button = Button(compartments, ViewTitle(view), "showroom.view." + view, () => SelectView(view));
            if (view == "overview") _homeButton = button;
        }
        _pointerHelp = Text(lower, "", 18, Ink);
        _controllerHelp = Text(lower, "", 18, Muted);
        _noticePanel = new PanelContainer { MouseFilter = Control.MouseFilterEnum.Ignore, Visible = false };
        _root.AddChild(_noticePanel);
        _noticePanel.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.TopWide);
        _noticePanel.OffsetLeft = 30; _noticePanel.OffsetRight = -365;
        _noticePanel.OffsetTop = 166; _noticePanel.OffsetBottom = 214;
        using var noticeStyle = Style(new Color(.035f, .046f, .053f, .96f), 10, 14);
        _noticePanel.AddThemeStyleboxOverride("panel", noticeStyle);
        _notice = new Label
        {
            MouseFilter = Control.MouseFilterEnum.Pass, ClipText = true,
            TextOverrunBehavior = TextServer.OverrunBehavior.TrimEllipsis,
            SizeFlagsHorizontal = Control.SizeFlags.ExpandFill,
        };
        _notice.AddThemeColorOverride("font_color", Accent); _notice.AddThemeFontSizeOverride("font_size", 18);
        _noticePanel.AddChild(_notice);
    }

    private void UpdateInterface()
    {
        if (_orbitButton is null) return;
        _orbitButton.Text = _autoOrbit ? "Pause turntable" : "Start turntable";
        _pointerHelp.Text = _interior
            ? "Drag / I J K L to look around  ·  Wheel / + / − to zoom"
            : "Drag / I J K L orbit  ·  Wheel / + / − zoom  ·  Right-drag / W A S D pan";
        _controllerHelp.Text = _interior
            ? "Right stick to look  ·  Triggers to zoom  ·  F1 / R3 hides controls for inspection"
            : "Controller: right stick orbit, triggers zoom  ·  R / Y reset  ·  F1 / R3 controls";
        _headlights.SetPressedNoSignal(_presentation?.HeadlightsOn ?? _rig?.HeadlightsOn ?? false);
        _wipers.SetPressedNoSignal(_presentation?.WipersOn ?? false);
        _hazards.SetPressedNoSignal(_presentation?.HazardsOn ?? false);
        foreach (var (name, button) in _openingButtons) button.SetPressedNoSignal(_presentation?.OpeningTarget(name) ?? false);
    }

    private static string ViewTitle(string view) => view switch
    {
        "overview" => "Exterior", "rear-cabin" => "Rear cabin", "luggage" => "Luggage",
        "engine" => "Engine bay", "top" => "Above", "underside" => "Underbody",
        _ => char.ToUpperInvariant(view[0]) + view[1..],
    };
    private static StyleBoxFlat Style(Color color, int radius, int padding)
    {
        var style = new StyleBoxFlat { BgColor = color, ContentMarginLeft = padding, ContentMarginRight = padding, ContentMarginTop = padding / 2f, ContentMarginBottom = padding / 2f };
        style.SetCornerRadiusAll(radius); return style;
    }
    private static Label Text(Node parent, string value, int size, Color color)
    {
        var label = new Label { Text = value, MouseFilter = Control.MouseFilterEnum.Ignore };
        label.AddThemeFontSizeOverride("font_size", size); label.AddThemeColorOverride("font_color", color);
        parent.AddChild(label); return label;
    }
    private static GridContainer Grid(Node parent)
    {
        var grid = new GridContainer { Columns = 2 }; grid.AddThemeConstantOverride("h_separation", 8); grid.AddThemeConstantOverride("v_separation", 6);
        parent.AddChild(grid); return grid;
    }
    private static void Separator(Node parent) => parent.AddChild(new HSeparator());
    private static Button Button(Node parent, string title, string id, Action action)
    {
        var button = new Button { Text = title, CustomMinimumSize = new Vector2(0, 42), SizeFlagsHorizontal = Control.SizeFlags.ExpandFill, FocusMode = Control.FocusModeEnum.All };
        button.SetMeta("automation_id", id); button.Pressed += action; parent.AddChild(button); return button;
    }
    private static CheckButton Toggle(Node parent, string title, string id, Action<bool> action)
    {
        var button = new CheckButton { Text = title, CustomMinimumSize = new Vector2(0, 38), FocusMode = Control.FocusModeEnum.All };
        button.SetMeta("automation_id", id); button.Toggled += value => action(value); parent.AddChild(button); return button;
    }
}
