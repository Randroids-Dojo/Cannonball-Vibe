using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Saves;
using Cannonball.Core.Telemetry;
using Cannonball.Game.UI;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game;

public sealed partial class Main : Node3D
{
    private const string ContentVersion = "graybox-m0-v1";
    private WorldStreamer _streamer = null!;
    private CannonballVehicle _vehicle = null!;
    private PrototypeHud _hud = null!;
    private JsonRunStateRepository _saves = null!;
    private JsonlTelemetrySink _telemetry = null!;
    private bool _smokeTest;
    private bool _stressTest;
    private bool _shutdownStarted;
    private int _smokeFrames;
    private double _telemetryElapsed;
    private double _previousDistance;
    private float _peakSpeedMetersPerSecond;
    private int _smokeTargetFrames = 360;

    public override void _Ready()
    {
        ConfigureInputMap();
        BuildLighting();
        _streamer = new WorldStreamer { Name = "WorldStreamer" };
        AddChild(_streamer);
        _vehicle = new CannonballVehicle { Position = new Vector3(0, 0.78f, 0) };
        AddChild(_vehicle);
        _streamer.Track(_vehicle);
        _hud = new PrototypeHud { Name = "PrototypeHud" };
        AddChild(_hud);

        _saves = new JsonRunStateRepository(
            ProjectSettings.GlobalizePath("user://runs/suspended-run.json"),
            ContentVersion);
        _telemetry = new JsonlTelemetrySink(
            ProjectSettings.GlobalizePath("user://telemetry/prototype.jsonl"));

        var arguments = OS.GetCmdlineUserArgs();
        _smokeTest = arguments.Contains("--smoke-test", StringComparer.Ordinal);
        _stressTest = arguments.Contains("--stress-driver", StringComparer.Ordinal);
        _smokeTargetFrames = _stressTest ? 3_600 : 360;
        _vehicle.AutopilotEnabled = _smokeTest || _stressTest;
        var assistArgument = arguments.FirstOrDefault(value => value.StartsWith("--assist=", StringComparison.Ordinal));
        if (assistArgument is not null &&
            Enum.TryParse<AssistProfile>(assistArgument["--assist=".Length..], ignoreCase: true, out var assist))
        {
            _vehicle.SetAssistProfile(assist);
        }
        GD.Print($"CANNONBALL_READY engine={Engine.GetVersionInfo()["string"]} physics_hz={Engine.PhysicsTicksPerSecond}");
    }

    public override void _Process(double delta)
    {
        _hud.UpdateTelemetry(
            _vehicle.SpeedMetersPerSecond,
            _streamer.RouteDistanceMeters,
            _streamer.LoadedChunkCount,
            _streamer.LocalOriginMeters,
            _vehicle.AssistProfile);
        _peakSpeedMetersPerSecond = Math.Max(_peakSpeedMetersPerSecond, _vehicle.SpeedMetersPerSecond);
        _telemetryElapsed += delta;
        if (_telemetryElapsed >= 5)
        {
            _telemetryElapsed = 0;
            _ = RecordTelemetryAsync("pace_sample");
        }

        if (Godot.Input.IsActionJustPressed("suspend_run"))
        {
            _ = PersistAsync(quitAfterSave: false);
        }

        if (Godot.Input.IsActionJustPressed("cycle_assist"))
        {
            _vehicle.CycleAssistProfile();
        }

        if (!_smokeTest || _shutdownStarted)
        {
            return;
        }

        _smokeFrames++;
        if (_smokeFrames >= _smokeTargetFrames)
        {
            _shutdownStarted = true;
            _ = PersistAsync(quitAfterSave: true);
        }
    }

    public override void _ExitTree()
    {
        if (_telemetry is not null)
        {
            _telemetry.DisposeAsync().AsTask().GetAwaiter().GetResult();
        }
    }

    private async Task PersistAsync(bool quitAfterSave)
    {
        try
        {
            if (quitAfterSave && _stressTest)
            {
                ValidateStressRun();
            }
            var save = CaptureSave();
            await _saves.SaveAsync(save);
            await RecordTelemetryAsync("run_suspended");
            GD.Print($"CANNONBALL_SAVE_OK distance_m={save.Run.Position.DistanceMeters:0.0}");
            if (quitAfterSave)
            {
                GD.Print(
                    $"CANNONBALL_SMOKE_OK chunks={_streamer.LoadedChunkCount} " +
                    $"distance_m={_streamer.RouteDistanceMeters:0.0} " +
                    $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
                    $"rebases={_streamer.RebaseCount}");
                GetTree().Quit();
            }
        }
        catch (Exception exception)
        {
            GD.PushError(exception.ToString());
            if (quitAfterSave)
            {
                GetTree().Quit(1);
            }
        }
    }

    private RunSave CaptureSave()
    {
        var routeDistance = _streamer.RouteDistanceMeters;
        var position = new RoutePosition(
            "graybox-25mi",
            routeDistance,
            1,
            _vehicle.GlobalPosition.X - RoadMath.CenterX(routeDistance),
            0);
        var runState = new RunState(
            Seed: 20_260_714,
            Position: position,
            RoutePlan: [position.EdgeId],
            ElapsedSeconds: Time.GetTicksMsec() / 1000.0,
            Cash: 25_000,
            Vehicle: new VehicleCondition(82, 1, 1, 1, 0),
            Enforcement: new EnforcementState(0, 0, "clear", 0),
            AssistProfile: _vehicle.AssistProfile);
        var localVehicle = new LocalVehicleState(
            _vehicle.Position.X,
            _vehicle.Position.Y,
            _vehicle.Position.Z,
            _vehicle.LinearVelocity.X,
            _vehicle.LinearVelocity.Y,
            _vehicle.LinearVelocity.Z,
            _vehicle.AngularVelocity.X,
            _vehicle.AngularVelocity.Y,
            _vehicle.AngularVelocity.Z);
        return new RunSave(
            RunSave.CurrentSchemaVersion,
            ContentVersion,
            RunSave.ComputeContentChecksum(ContentVersion),
            DateTimeOffset.UtcNow,
            runState,
            localVehicle,
            [new ReplayMarker(runState.ElapsedSeconds, position, "suspend")]);
    }

    private async Task RecordTelemetryAsync(string name)
    {
        var distance = _streamer.RouteDistanceMeters;
        var properties = new Dictionary<string, object?>
        {
            ["speedMetersPerSecond"] = _vehicle.SpeedMetersPerSecond,
            ["loadedChunks"] = _streamer.LoadedChunkCount,
            ["lookAheadMeters"] = _streamer.CurrentLookAheadMeters,
            ["distanceDeltaMeters"] = distance - _previousDistance,
        };
        _previousDistance = distance;
        await _telemetry.WriteAsync(new TelemetryEvent(
            name,
            DateTimeOffset.UtcNow,
            20_260_714,
            "graybox-25mi",
            distance,
            properties));
    }

    private void ValidateStressRun()
    {
        if (_peakSpeedMetersPerSecond < 80)
        {
            throw new InvalidOperationException(
                $"Stress driver only reached {_peakSpeedMetersPerSecond * 2.236936f:0.0} mph.");
        }
        if (_streamer.RebaseCount < 1)
        {
            throw new InvalidOperationException("Stress driver did not cross a local-origin rebase.");
        }
        if (_streamer.LoadedChunkCount is < 5 or > 8)
        {
            throw new InvalidOperationException(
                $"Streaming window escaped its bound: {_streamer.LoadedChunkCount} chunks.");
        }
    }

    private void BuildLighting()
    {
        AddChild(new DirectionalLight3D
        {
            Name = "MoonLight",
            RotationDegrees = new Vector3(-48, -28, 0),
            LightColor = new Color("a9c4ff"),
            LightEnergy = 1.3f,
            ShadowEnabled = true,
        });
        AddChild(new WorldEnvironment
        {
            Name = "NightEnvironment",
            Environment = new Godot.Environment
            {
                BackgroundMode = Godot.Environment.BGMode.Color,
                BackgroundColor = new Color("060912"),
                AmbientLightSource = Godot.Environment.AmbientSource.Color,
                AmbientLightColor = new Color("425072"),
                AmbientLightEnergy = 0.45f,
            },
        });
    }

    private static void ConfigureInputMap()
    {
        AddKeyAction("accelerate", Key.W);
        AddKeyAction("brake", Key.S);
        AddKeyAction("steer_left", Key.A);
        AddKeyAction("steer_right", Key.D);
        AddKeyAction("reset_vehicle", Key.R);
        AddKeyAction("suspend_run", Key.F5);
        AddKeyAction("cycle_assist", Key.Tab);
        AddJoyAxisAction("accelerate", JoyAxis.TriggerRight, 1);
        AddJoyAxisAction("brake", JoyAxis.TriggerLeft, 1);
        AddJoyAxisAction("steer_left", JoyAxis.LeftX, -1);
        AddJoyAxisAction("steer_right", JoyAxis.LeftX, 1);
    }

    private static void AddKeyAction(StringName action, Key key)
    {
        if (!InputMap.HasAction(action))
        {
            InputMap.AddAction(action, 0.12f);
        }
        InputMap.ActionAddEvent(action, new InputEventKey { PhysicalKeycode = key });
    }

    private static void AddJoyAxisAction(StringName action, JoyAxis axis, float axisValue)
    {
        if (!InputMap.HasAction(action))
        {
            InputMap.AddAction(action, 0.12f);
        }
        InputMap.ActionAddEvent(action, new InputEventJoypadMotion { Axis = axis, AxisValue = axisValue });
    }
}
