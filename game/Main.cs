using Cannonball.Core.Content;
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
    private const int MaximumTransportProbeReads = 10_000;
    private const int MaximumRenderIntegrityUnsupportedPhysicsFrames = 30;
    private const double MinimumRenderIntegrityWellGroundedRatio = 0.90;
    private WorldStreamer _streamer = null!;
    private CannonballVehicle _vehicle = null!;
    private PrototypeHud _hud = null!;
    private JsonRunStateRepository _saves = null!;
    private JsonlTelemetrySink _telemetry = null!;
    private RouteContentPackage _package = null!;
    private VerifiedFileChunkSource _chunkSource = null!;
    private Task<TransportProbeResult>? _transportProbe;
    private bool _transportProbeReported;
    private bool _smokeTest;
    private bool _stressTest;
    private bool _shortCorridorSoak;
    private bool _renderIntegrity;
    private bool _shutdownStarted;
    private int _smokeFrames;
    private double _telemetryElapsed;
    private double _previousDistance;
    private float _peakSpeedMetersPerSecond;
    private int _smokeTargetFrames = 360;
    private bool _renderTraversalStarted;
    private int _minimumLoadedChunksDuringRenderTraversal = int.MaxValue;

    public override void _Ready()
    {
        try
        {
            var arguments = OS.GetCmdlineUserArgs();
            var routePath = RequiredArgument(arguments, "--route-package");
            var requestedProbeMiles = OptionalPositiveDouble(arguments, "--distance-miles");
            _smokeTest = arguments.Contains("--smoke-test", StringComparer.Ordinal) || requestedProbeMiles > 0;
            _stressTest = arguments.Contains("--stress-driver", StringComparer.Ordinal);
            _shortCorridorSoak = arguments.Contains("--short-corridor-soak", StringComparer.Ordinal);
            _renderIntegrity = arguments.Contains("--render-integrity", StringComparer.Ordinal);
            _smokeTest = _smokeTest || _stressTest || _shortCorridorSoak || _renderIntegrity;
            _smokeTargetFrames = _stressTest || _shortCorridorSoak ? 3_600 : 360;
            if (_renderIntegrity)
            {
                _smokeTargetFrames = 4_800;
            }

            var absoluteRoutePath = Path.GetFullPath(routePath);
            _package = FlatBufferRouteContent.Load(absoluteRoutePath);
            _chunkSource = new VerifiedFileChunkSource(
                _package,
                Path.GetDirectoryName(absoluteRoutePath)
                    ?? throw new InvalidDataException("Route package has no parent directory."));
            var initialManifest = _package.Chunks.Values
                .OrderBy(manifest => manifest.EdgeId, StringComparer.Ordinal)
                .ThenBy(manifest => manifest.StartMeters)
                .FirstOrDefault()
                ?? throw new InvalidDataException("Route package has no runtime chunks.");
            var initialChunk = _chunkSource.LoadChunk(initialManifest.Id);

            ConfigureInputMap();
            BuildLighting();
            _streamer = new WorldStreamer { Name = "WorldStreamer" };
            _streamer.Configure(_package, _chunkSource, initialChunk);
            _streamer.ShortCorridorLoopEnabled = _shortCorridorSoak;
            AddChild(_streamer);
            _vehicle = new CannonballVehicle
            {
                Transform = new Transform3D(
                    Basis.LookingAt(_streamer.InitialRoadForward, Vector3.Up),
                    _streamer.InitialRoadPoint + Vector3.Up * 0.78f),
            };
            AddChild(_vehicle);
            _streamer.Track(_vehicle);
            _hud = new PrototypeHud { Name = "PrototypeHud" };
            AddChild(_hud);

            _saves = new JsonRunStateRepository(
                ProjectSettings.GlobalizePath("user://runs/suspended-run.json"),
                _package.Graph.ContentVersion);
            _telemetry = new JsonlTelemetrySink(
                ProjectSettings.GlobalizePath("user://telemetry/prototype.jsonl"));

            _vehicle.AutopilotEnabled = _smokeTest && !_renderIntegrity;
            if (_renderIntegrity)
            {
                _vehicle.AutopilotSpeedLimitMetersPerSecond = 12;
            }
            var assistArgument = arguments.FirstOrDefault(value => value.StartsWith("--assist=", StringComparison.Ordinal));
            if (assistArgument is not null &&
                Enum.TryParse<AssistProfile>(assistArgument["--assist=".Length..], ignoreCase: true, out var assist))
            {
                _vehicle.SetAssistProfile(assist);
            }
            if (requestedProbeMiles > 0)
            {
                _transportProbe = RunTransportProbeAsync(requestedProbeMiles);
            }

            GD.Print(
                $"CANNONBALL_READY engine={Engine.GetVersionInfo()["string"]} " +
                $"physics_hz={Engine.PhysicsTicksPerSecond} " +
                $"content_source=packaged content_version={_package.Graph.ContentVersion}");
        }
        catch (Exception exception)
        {
            GD.PushError(exception.ToString());
            GetTree().Quit(1);
        }
    }

    public override void _Process(double delta)
    {
        if (_streamer is null || _vehicle is null || _hud is null)
        {
            return;
        }

        if (!ReportTransportProbeWhenComplete())
        {
            return;
        }

        _hud.UpdateTelemetry(
            _vehicle.SpeedMetersPerSecond,
            _streamer.RouteDistanceMeters,
            _streamer.LoadedChunkCount,
            _streamer.LocalOriginMeters,
            _vehicle.AssistProfile);
        _peakSpeedMetersPerSecond = Math.Max(_peakSpeedMetersPerSecond, _vehicle.SpeedMetersPerSecond);
        if (_renderIntegrity)
        {
            if (!_renderTraversalStarted &&
                _streamer.LoadedChunkCount == _streamer.ExpectedChunkCount &&
                _streamer.ReviewReadyChunkCount == _streamer.ExpectedChunkCount)
            {
                _renderTraversalStarted = true;
                _vehicle.ResetGroundingTelemetry();
                _vehicle.AutopilotEnabled = true;
            }
            if (_renderTraversalStarted)
            {
                _minimumLoadedChunksDuringRenderTraversal = Math.Min(
                    _minimumLoadedChunksDuringRenderTraversal,
                    _streamer.LoadedChunkCount);
            }
        }
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
        var renderTraversalComplete = _renderIntegrity &&
            _streamer.RouteDistanceMeters >= Math.Min(300, _streamer.TotalRouteLengthMeters - 35);
        if (_smokeFrames >= _smokeTargetFrames || renderTraversalComplete)
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

    private bool ReportTransportProbeWhenComplete()
    {
        if (_transportProbe is null || _transportProbeReported)
        {
            return true;
        }
        if (!_transportProbe.IsCompleted)
        {
            return false;
        }
        _transportProbeReported = true;
        if (!_transportProbe.IsCompletedSuccessfully)
        {
            GD.PushError($"Packaged route transport probe failed: {_transportProbe.Exception?.GetBaseException()}");
            GetTree().Quit(1);
            return false;
        }
        var result = _transportProbe.Result;
        GD.Print(
            $"CANNONBALL_OFFICIAL_CORRIDOR_OK content_source=packaged " +
            $"unique_route_miles={result.UniqueRouteMiles:0.000000} " +
            $"requested_probe_miles={result.RequestedMiles:0.######} " +
            $"route_repetitions={result.Repetitions} " +
            $"verified_chunk_reads={result.VerifiedChunkReads} chunk_failures=0");
        return true;
    }

    private async Task<TransportProbeResult> RunTransportProbeAsync(double requestedMiles)
    {
        var uniqueMeters = _package.Chunks.Values
            .GroupBy(manifest => manifest.EdgeId, StringComparer.Ordinal)
            .Sum(group => group.Max(manifest => manifest.EndMeters));
        var uniqueMiles = uniqueMeters / 1_609.344;
        if (!double.IsFinite(uniqueMeters) || !double.IsFinite(uniqueMiles) || uniqueMiles <= 0)
        {
            throw new InvalidDataException("Route package has no positive traversal distance.");
        }
        var manifests = _package.Chunks.Values.OrderBy(manifest => manifest.Id, StringComparer.Ordinal).ToArray();
        var repetitionValue = Math.Ceiling(requestedMiles / uniqueMiles);
        if (!double.IsFinite(repetitionValue) || repetitionValue < 1 || repetitionValue > int.MaxValue)
        {
            throw new ArgumentOutOfRangeException(
                nameof(requestedMiles),
                "Requested transport probe requires too many route repetitions.");
        }
        var repetitions = checked((int)repetitionValue);
        var expectedReads = checked((long)repetitions * manifests.Length);
        if (expectedReads > MaximumTransportProbeReads)
        {
            throw new ArgumentOutOfRangeException(
                nameof(requestedMiles),
                $"Requested transport probe exceeds the {MaximumTransportProbeReads} read budget.");
        }
        var reads = 0;
        for (var repetition = 0; repetition < repetitions; repetition++)
        {
            foreach (var manifest in manifests)
            {
                _ = await _chunkSource.LoadChunkAsync(manifest.Id);
                reads++;
            }
        }
        return new TransportProbeResult(requestedMiles, uniqueMiles, repetitions, reads);
    }

    private async Task PersistAsync(bool quitAfterSave)
    {
        try
        {
            if (quitAfterSave && _stressTest)
            {
                ValidateStressRun();
            }
            if (quitAfterSave && _shortCorridorSoak)
            {
                ValidateShortCorridorSoak();
            }
            if (quitAfterSave && _renderIntegrity)
            {
                ValidateRenderIntegrity();
            }
            var save = CaptureSave();
            await _saves.SaveAsync(save);
            await RecordTelemetryAsync("run_suspended");
            GD.Print($"CANNONBALL_SAVE_OK distance_m={save.Run.Position.DistanceMeters:0.0}");
            if (quitAfterSave)
            {
                if (_streamer.ChunkFailureCount > 0)
                {
                    throw new InvalidOperationException(
                        $"Streaming encountered {_streamer.ChunkFailureCount} verified chunk failures.");
                }
                GD.Print(
                    $"CANNONBALL_SMOKE_OK chunks={_streamer.LoadedChunkCount} " +
                    $"distance_m={_streamer.RouteDistanceMeters:0.0} " +
                    $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
                    $"rebases={_streamer.RebaseCount} " +
                    $"max_chunk_build_ms={_streamer.MaximumBuildMilliseconds:0.000} " +
                    $"content_source=packaged");
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
        var edge = _package.Graph.GetEdge(_streamer.CurrentEdgeId);
        var position = new RoutePosition(
            edge.Id,
            routeDistance,
            Math.Min(1, edge.LaneCount - 1),
            _streamer.CurrentLateralOffsetMeters,
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
            _package.Graph.ContentVersion,
            RunSave.ComputeContentChecksum(_package.Graph.ContentVersion),
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
            ["contentSource"] = "packaged",
            ["chunkFailures"] = _streamer.ChunkFailureCount,
            ["maximumChunkBuildMilliseconds"] = _streamer.MaximumBuildMilliseconds,
            ["shortCorridorLoops"] = _streamer.CompletedShortCorridorLoops,
        };
        _previousDistance = distance;
        await _telemetry.WriteAsync(new TelemetryEvent(
            name,
            DateTimeOffset.UtcNow,
            20_260_714,
            _streamer.CurrentEdgeId,
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
        if (_streamer.ChunkFailureCount > 0)
        {
            throw new InvalidOperationException("Stress driver encountered a route chunk failure.");
        }
    }

    private void ValidateShortCorridorSoak()
    {
        if (_peakSpeedMetersPerSecond < 70)
        {
            throw new InvalidOperationException(
                $"Short-corridor soak only reached {_peakSpeedMetersPerSecond * 2.236936f:0.0} mph.");
        }
        if (_streamer.ChunkFailureCount > 0)
        {
            throw new InvalidOperationException("Short-corridor soak encountered a route chunk failure.");
        }
        if (_streamer.CompletedShortCorridorLoops < 1)
        {
            throw new InvalidOperationException("Short-corridor soak did not complete a route loop.");
        }
        GD.Print(
            $"CANNONBALL_SHORT_CORRIDOR_SOAK_OK chunks={_streamer.LoadedChunkCount} " +
            $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
            $"route_loops={_streamer.CompletedShortCorridorLoops} chunk_failures=0");
    }

    private void ValidateRenderIntegrity()
    {
        const double requiredDistance = 300;
        if (_streamer.TotalRouteLengthMeters < requiredDistance + 35)
        {
            throw new InvalidOperationException(
                $"Render-integrity route is only {_streamer.TotalRouteLengthMeters:0.0} m; " +
                $"required at least {requiredDistance + 35:0.0} m.");
        }
        if (_streamer.RouteDistanceMeters < requiredDistance)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal only reached {_streamer.RouteDistanceMeters:0.0} m; " +
                $"required {requiredDistance:0.0} m.");
        }
        if (_streamer.LoadedChunkCount != _streamer.ExpectedChunkCount)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal loaded {_streamer.LoadedChunkCount} of " +
                $"{_streamer.ExpectedChunkCount} route chunks.");
        }
        if (!_renderTraversalStarted ||
            _minimumLoadedChunksDuringRenderTraversal != _streamer.ExpectedChunkCount)
        {
            throw new InvalidOperationException(
                "Render-integrity traversal did not retain every expected chunk after visual readiness.");
        }
        if (_streamer.ReviewReadyChunkCount != _streamer.ExpectedChunkCount)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal has review geometry for " +
                $"{_streamer.ReviewReadyChunkCount} of {_streamer.ExpectedChunkCount} chunks.");
        }
        if (_streamer.CrossedReviewDistanceThresholdCount != 3)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal crossed " +
                $"{_streamer.CrossedReviewDistanceThresholdCount} of 3 distance thresholds.");
        }
        if (_streamer.ChunkFailureCount > 0)
        {
            throw new InvalidOperationException("Render-integrity traversal encountered a route chunk failure.");
        }
        if (_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames >
            MaximumRenderIntegrityUnsupportedPhysicsFrames)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal was unsupported for " +
                $"{_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} consecutive physics frames.");
        }
        if (!_vehicle.HasBeenGrounded || _vehicle.PostGroundingPhysicsFrames == 0)
        {
            throw new InvalidOperationException("Render-integrity traversal never established road contact.");
        }
        var wellGroundedRatio =
            (double)_vehicle.WellGroundedPhysicsFrames / _vehicle.PostGroundingPhysicsFrames;
        if (wellGroundedRatio < MinimumRenderIntegrityWellGroundedRatio)
        {
            throw new InvalidOperationException(
                $"Render-integrity traversal had at least three grounded wheels for only " +
                $"{wellGroundedRatio:P2} of post-contact physics frames.");
        }
        GD.Print(
            $"CANNONBALL_RENDER_INTEGRITY_OK chunks={_streamer.LoadedChunkCount} " +
            $"distance_m={_streamer.RouteDistanceMeters:0.0} " +
            $"peak_mph={_peakSpeedMetersPerSecond * 2.236936f:0.0} " +
            $"distance_thresholds={_streamer.CrossedReviewDistanceThresholdCount} " +
            $"review_chunks={_streamer.ReviewReadyChunkCount} " +
            $"well_grounded_ratio={wellGroundedRatio:0.0000} " +
            $"max_unsupported_frames={_vehicle.MaximumConsecutiveUnsupportedPhysicsFrames} " +
            $"chunk_failures=0");
    }

    private static string RequiredArgument(IReadOnlyList<string> arguments, string name)
    {
        var prefix = name + "=";
        var inline = arguments.FirstOrDefault(value => value.StartsWith(prefix, StringComparison.Ordinal));
        if (inline is not null && inline.Length > prefix.Length)
        {
            return inline[prefix.Length..];
        }
        var index = ArgumentIndex(arguments, name);
        if (index >= 0 && index + 1 < arguments.Count)
        {
            return arguments[index + 1];
        }
        throw new ArgumentException($"Missing required game argument '{name}=<path>'.");
    }

    private static double OptionalPositiveDouble(IReadOnlyList<string> arguments, string name)
    {
        var prefix = name + "=";
        var raw = arguments.FirstOrDefault(value => value.StartsWith(prefix, StringComparison.Ordinal));
        raw = raw is null ? null : raw[prefix.Length..];
        if (raw is null)
        {
            var index = ArgumentIndex(arguments, name);
            raw = index >= 0 && index + 1 < arguments.Count ? arguments[index + 1] : null;
        }
        if (raw is null)
        {
            return 0;
        }
        if (!double.TryParse(raw, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out var value) ||
            !double.IsFinite(value) || value <= 0)
        {
            throw new ArgumentException($"Game argument '{name}' must be a positive finite number.");
        }
        return value;
    }

    private static int ArgumentIndex(IReadOnlyList<string> arguments, string value)
    {
        for (var index = 0; index < arguments.Count; index++)
        {
            if (string.Equals(arguments[index], value, StringComparison.Ordinal))
            {
                return index;
            }
        }
        return -1;
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

    private sealed record TransportProbeResult(
        double RequestedMiles,
        double UniqueRouteMiles,
        int Repetitions,
        int VerifiedChunkReads);
}
