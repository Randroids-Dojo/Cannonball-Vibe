using Godot;

namespace Cannonball.Game.Automation;

/// <summary>
/// Whether anything is going to read the per-node automation state this frame.
/// </summary>
/// <remarks>
/// Nodes publish an "automation_state" dictionary for PlayGodot to inspect, and
/// several rebuilt it every rendered frame. Each entry boxes a Variant and
/// marshals a string key, and the chase camera alone cost 3,072 bytes a frame -
/// 40% of the game's total allocation, measured at over 800 frames a second. That
/// churn filled gen0 roughly every two seconds and each collection stalled a frame
/// for 30-40 ms, which is the stutter the owner reported.
///
/// addons/playgodot/server.gd is the only reader, and it only exists when the
/// process was launched for PlayGodot. When it is absent the work is pure waste,
/// so it is skipped. Under PlayGodot the behaviour is unchanged, which keeps the
/// semantic UI tests measuring what they measured before.
/// </remarks>
public static class AutomationInspection
{
    public static readonly bool Enabled =
        OS.GetCmdlineUserArgs().Contains("--playgodot", System.StringComparer.Ordinal);
}
