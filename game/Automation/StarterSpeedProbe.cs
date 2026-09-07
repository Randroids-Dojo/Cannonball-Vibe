using Cannonball.Core.Runs;
using Cannonball.Core.Simulation.Vehicle;
using Cannonball.Game.Input;
using Cannonball.Game.Vehicle;
using Godot;
using System.Text.Json;

namespace Cannonball.Game.Automation;

/// <summary>Actual Jolt driving fixtures for the stock vehicle's speed governor.</summary>
public sealed partial class StarterSpeedProbe : Node3D
{
    private const int PhysicsHz = 120;
    private const int SettleFrames = 120;
    private const float SpeedTolerance = 0.1f;
    private readonly List<ProbeCase> _cases = [];
    private readonly List<object> _results = [];
    private CannonballVehicle _vehicle = null!;
    private StaticBody3D _road = null!;
    private Vector3 _forward;
    private int _caseIndex;
    private int _frame;
    private float _peakSpeed;
    private float _minimumSteadySpeed;
    private int _groundedSamples;
    private bool _finished;

    public override void _Ready()
    {
        GameInputMap.Configure();
        Engine.PhysicsTicksPerSecond = PhysicsHz;
        foreach (var assist in Enum.GetValues<AssistProfile>())
        {
            _cases.Add(new("level", assist, VehicleSetup.Starter, 0, 30));
            _cases.Add(new("downhill", assist, VehicleSetup.Starter, -0.08f, 30));
        }
        _cases.Add(new("configured-150", AssistProfile.Balanced, new("tuning-fixture", 150), 0, 30));
        _cases.Add(new("downhill-coast", AssistProfile.Balanced, VehicleSetup.Starter, -0.20f, 30));
        _cases.Add(new("braking", AssistProfile.Balanced, VehicleSetup.Starter, 0, 4));
        _cases.Add(new("reverse", AssistProfile.Balanced, VehicleSetup.Starter, 0, 2));
        _cases.Add(new("resume-overspeed", AssistProfile.Balanced, VehicleSetup.Starter, 0, 2));
        _cases.Add(new("airborne", AssistProfile.Balanced, VehicleSetup.Starter, 0, 0.25f));
        _cases.Add(new("lateral-impact", AssistProfile.Balanced, VehicleSetup.Starter, 0, 2f / PhysicsHz));
        _road = new StaticBody3D { CollisionLayer = 1 };
        _road.AddChild(new CollisionShape3D
        {
            Position = new Vector3(0, -0.5f, 0),
            Shape = new BoxShape3D { Size = new Vector3(2_000, 1, 8_000) },
        });
        AddChild(_road);
        BeginCase();
    }

    public override void _PhysicsProcess(double delta)
    {
        if (_finished)
        {
            return;
        }
        try
        {
            Advance();
        }
        catch (Exception error)
        {
            _finished = true;
            GD.PushError($"CANNONBALL_STARTER_SPEED_FAILED {Current.Name}: {error.Message}");
            WriteReport("failed", error.Message);
            GetTree().Quit(1);
        }
    }

    private ProbeCase Current => _cases[_caseIndex];

    private void BeginCase()
    {
        if (_vehicle is not null)
        {
            RemoveChild(_vehicle);
            _vehicle.Free();
        }
        var basis = Basis.FromEuler(new Vector3(Mathf.Atan(Current.Grade), 0, 0));
        _road.Basis = basis;
        _forward = -basis.Z;
        _vehicle = new CannonballVehicle
        {
            // The level/downhill cases deliberately exercise the constructor's
            // normal starter default before selecting any different setup.
            ForceGrayboxVisual = true,
            Basis = basis,
            Position = basis.Y * CannonballVehicle.VisualRigMountHeightMeters,
            TargetRoadPoint = Vector3.Zero,
            TargetRoadForward = _forward,
            AutomationInputOverride = new(0, 0, 0, 0, 0, true, false),
        };
        Require(_vehicle.Setup == VehicleSetup.Starter, "new vehicle must select the starter");
        _vehicle.Setup = Current.Setup;
        _vehicle.SetAssistProfile(Current.Assist);
        AddChild(_vehicle);
        _frame = 0;
        _peakSpeed = 0;
        _minimumSteadySpeed = float.PositiveInfinity;
        _groundedSamples = 0;
    }

    private void Advance()
    {
        _frame++;
        // Track road elevation so a long downhill fixture never invokes recovery
        // merely because its world position is below the starting elevation.
        _vehicle.TargetRoadPoint = _vehicle.Position.Slide(_road.Basis.Y);
        if (_frame < SettleFrames)
        {
            return;
        }
        if (_frame == SettleFrames)
        {
            Require(_vehicle.GroundedWheelCount >= 3, "fixture did not settle on its tires");
            var cap = (float)Current.Setup.ForwardTopSpeedMetersPerSecond;
            _vehicle.AutomationInputOverride = Current.Name switch
            {
                "braking" => new(0, 1, 0, 0, 0, false, false),
                "reverse" => new(0, 0, 1, 0, 0, false, false),
                "airborne" or "lateral-impact" or "downhill-coast" => new(0, 0, 0, 0, 0, false, false),
                _ => new(1, 0, 0, 0, 0, false, false),
            };
            if (Current.Name is "braking" or "resume-overspeed" or "lateral-impact" or "airborne" or "downhill-coast")
            {
                _vehicle.LinearVelocity = _forward *
                    (Current.Name == "braking" ? cap : cap + 10);
            }
            if (Current.Name == "airborne")
            {
                _vehicle.Position += Vector3.Up * 100;
                _vehicle.LinearVelocity += Vector3.Up * 12;
                _vehicle.ResetGroundingTelemetry();
            }
            if (Current.Name == "lateral-impact")
            {
                _vehicle.LinearVelocity += Vector3.Right * 10 + Vector3.Up * 3;
            }
            return;
        }
        var runFrames = _frame - SettleFrames;
        var forward = (-_vehicle.Basis.Z).Slide(_road.Basis.Y).Normalized();
        var speed = _vehicle.LinearVelocity.Dot(forward);
        _peakSpeed = Math.Max(_peakSpeed, speed);
        _groundedSamples += _vehicle.GroundedWheelCount > 0 ? 1 : 0;
        if (runFrames > 25 * PhysicsHz)
        {
            _minimumSteadySpeed = Math.Min(_minimumSteadySpeed, speed);
        }
        if (runFrames < Current.Seconds * PhysicsHz)
        {
            return;
        }

        var maximum = (float)Current.Setup.ForwardTopSpeedMetersPerSecond;
        GD.Print($"STARTER_PROBE_SAMPLE case={Current.Name} grounded={_groundedSamples}/{runFrames} " +
            $"position={_vehicle.Position} velocity={_vehicle.LinearVelocity} " +
            $"peak={_peakSpeed} final={speed} resets={_vehicle.ResetToRoadCount}");
        switch (Current.Name)
        {
            case "braking":
                Require(Math.Abs(speed) < 0.75f, $"brakes did not stop the car: {speed}");
                break;
            case "reverse":
                Require(speed < -10, $"reverse drive was inhibited: {speed}");
                break;
            case "airborne":
                Require(_groundedSamples == 0, "airborne fixture contacted the road");
                Require(speed > maximum + 5, $"airborne forward speed was clamped: {speed}");
                Require(_vehicle.LinearVelocity.Y > 2, "airborne vertical motion was lost");
                break;
            case "lateral-impact":
                Require(speed <= maximum + SpeedTolerance, $"forward overspeed was retained: {speed}");
                Require(_vehicle.LinearVelocity.X > 9, "governor removed lateral motion");
                Require(_vehicle.LinearVelocity.Y > 2, "governor removed vertical motion");
                break;
            default:
                Require(_groundedSamples >= runFrames * 0.99f, "fixture lost road contact");
                Require(_peakSpeed <= maximum + SpeedTolerance,
                    $"peak {_peakSpeed} exceeded cap {maximum} + {SpeedTolerance} m/s");
                Require(speed >= maximum - 0.25f, $"car could not reach its cap: {speed}");
                if (Current.Seconds >= 30)
                {
                    Require(_minimumSteadySpeed >= maximum - 0.25f,
                        $"speed did not hold near the cap: {_minimumSteadySpeed}");
                }
                break;
        }
        Require(_vehicle.ResetToRoadCount == 0, "unexpected recovery invalidated measurement");
        _results.Add(new
        {
            scenario = Current.Name, assist = Current.Assist.ToString(), setup = Current.Setup.Id,
            cap_mph = Current.Setup.ForwardTopSpeedMph, grade = Current.Grade,
            physics_frames = runFrames, peak_forward_mps = _peakSpeed, final_forward_mps = speed,
            minimum_steady_mps = float.IsFinite(_minimumSteadySpeed) ? (float?)_minimumSteadySpeed : null,
            final_lateral_mps = _vehicle.LinearVelocity.X, final_vertical_mps = _vehicle.LinearVelocity.Y,
            grounded_samples = _groundedSamples, resets = _vehicle.ResetToRoadCount, passed = true,
        });
        GD.Print($"CANNONBALL_STARTER_SPEED_CASE_OK case={Current.Name} assist={Current.Assist} " +
            $"cap_mph={Current.Setup.ForwardTopSpeedMph} peak_mph={_peakSpeed / 0.44704:0.000} " +
            $"final_mph={speed / 0.44704:0.000}");
        _caseIndex++;
        if (_caseIndex < _cases.Count)
        {
            BeginCase();
            return;
        }
        _finished = true;
        WriteReport("passed", null);
        GD.Print($"CANNONBALL_STARTER_SPEED_OK cases={_results.Count} physics_hz={PhysicsHz}");
        GetTree().Quit();
    }

    private void WriteReport(string status, string? failure)
    {
        var output = System.Environment.GetEnvironmentVariable("CANNONBALL_STARTER_SPEED_RESULT") ??
            ProjectSettings.GlobalizePath("res://reports/starter-speed/probe.json");
        System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(output)!);
        System.IO.File.WriteAllText(output, JsonSerializer.Serialize(new
        {
            status, failure, engine = Engine.GetVersionInfo()["string"].AsString(),
            utc = DateTimeOffset.UtcNow, physics_hz = PhysicsHz, seed = 0,
            overspeed_tolerance_mps = SpeedTolerance, results = _results,
        }, new JsonSerializerOptions { WriteIndented = true }) + "\n");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private sealed record ProbeCase(string Name, AssistProfile Assist, VehicleSetup Setup, float Grade, float Seconds);
}
