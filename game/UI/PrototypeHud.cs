using Godot;
using Cannonball.Core.Runs;

namespace Cannonball.Game.UI;

public sealed partial class PrototypeHud : CanvasLayer
{
    private Label _speed = null!;
    private Label _distance = null!;
    private Label _streaming = null!;

    public override void _Ready()
    {
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
        help.Text = "W / RT accelerate   S / LT brake   A D / stick steer   R reset   TAB assist   F5 suspend";
    }

    public void UpdateTelemetry(
        float metersPerSecond,
        double distanceMeters,
        int chunks,
        double originMeters,
        AssistProfile assistProfile)
    {
        _speed.Text = $"{metersPerSecond * 2.236936f,3:0} MPH";
        _distance.Text = $"{distanceMeters / 1609.344:0.00} / 25.00 MILES";
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
}
