using Godot;

namespace Cannonball.Game.Input;

public readonly record struct DriveInputState(float Throttle, float Brake, float Steering, bool Reset);

public interface IDriveInput
{
    DriveInputState Read();
}
public sealed class GodotDriveInput : IDriveInput
{
    public DriveInputState Read() => new(
        Godot.Input.GetActionStrength("accelerate"),
        Godot.Input.GetActionStrength("brake"),
        Godot.Input.GetAxis("steer_left", "steer_right"),
        Godot.Input.IsActionJustPressed("reset_vehicle"));
}
