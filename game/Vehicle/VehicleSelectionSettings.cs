using Godot;

namespace Cannonball.Game.Vehicle;

/// <summary>Presentation selection is separate from the versioned authoritative run save.</summary>
public static class VehicleSelectionSettings
{
    private const string Path = "user://vehicle-presentation.cfg";
    public static bool IsKnown(string id) => id is "hero-gt" or "endurance-sedan" or "graybox";

    public static string Load()
    {
        using var settings = new ConfigFile();
        if (settings.Load(Path) != Error.Ok) return "hero-gt";
        var id = settings.GetValue("vehicle", "asset_id", "hero-gt").AsString();
        return IsKnown(id) ? id : "hero-gt";
    }

    public static void Save(string id)
    {
        if (!IsKnown(id)) throw new ArgumentException($"Unknown vehicle selection '{id}'.");
        using var settings = new ConfigFile();
        settings.SetValue("vehicle", "asset_id", id);
        var error = settings.Save(Path);
        if (error != Error.Ok) throw new IOException($"Vehicle selection could not be saved: {error}");
    }
}
