namespace Cannonball.Game.Input;

public readonly record struct DriveInputState(
    float Throttle,
    float Brake,
    float Reverse,
    float Handbrake,
    float Steering,
    bool StationaryHold,
    bool Reset);
