using System.Security.Cryptography;
using System.Text.Json;
using Cannonball.Core.Runs;
using Cannonball.Core.Simulation.Vehicle;
using Cannonball.Game.Input;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game.Automation;

/// <summary>Actual-engine integration proof. InputMap action injection is a fixture, not a physical device test.</summary>
public sealed class EnduranceSedanScenario : IDisposable
{
    public static readonly string[] ExpectedStages =
    [
        "static-ride", "keyboard-acceleration", "keyboard-braking", "controller-acceleration",
        "controller-braking", "reverse", "steer-left", "steer-right", "suspension",
        "collision", "reset", "cameras", "natural-rebase", "forced-rebase", "save-resume", "starter-policy",
    ];
    private static readonly StringName[] Actions =
    [
        GameInputMap.Accelerate, GameInputMap.Brake, GameInputMap.Reverse, GameInputMap.Handbrake,
        GameInputMap.SteerLeft, GameInputMap.SteerRight, GameInputMap.ResetVehicle, GameInputMap.ToggleCamera,
        GameInputMap.AccelerateController, GameInputMap.BrakeController,
        GameInputMap.SteerLeftController, GameInputMap.SteerRightController,
        GameInputMap.CameraLookLeft, GameInputMap.CameraLookRight,
        GameInputMap.CameraLookUp, GameInputMap.CameraLookDown,
    ];
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private readonly Node3D _course = new() { Name = "EnduranceSedanIntegrationCourse" };
    private readonly StreamWriter _frames;
    private readonly string _evidenceDirectory;
    private readonly string _selectedVehicle;
    private readonly ulong _seed;
    private readonly Node _parent;
    private readonly bool _captureEnabled;
    private readonly bool _nativeDisplay;
    private readonly HashSet<string> _capturedStages = new(StringComparer.Ordinal);
    private readonly List<object> _captures = [];
    private Task? _captureTask;
    private object? _renderedState;
    private string? _renderFailure;
    private readonly Func<(CannonballVehicle, WorldStreamer)> _roundTripSave;
    private readonly List<object> _results = [];
    private readonly string[] _expectedStages;
    private readonly HashSet<int> _drivingLods = [];
    private Camera3D? _lodObserver;
    private CannonballVehicle _vehicle;
    private WorldStreamer _streamer;
    private int _stageIndex;
    private int _stageFrames;
    private long _physicsFrames;
    private bool _begun;
    private bool _collisionObserved;
    private bool _cockpitObserved;
    private readonly Dictionary<string, object> _cameraDirectionChecks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, RebaseObservation> _rebaseObservations = new(StringComparer.Ordinal);
    private bool _fixtureInterpolationResetPending;
    private float? _savedCameraStabilization;
    private bool _resumeComplete;
    private readonly List<ulong> _reconstructionProcessFrames = [];
    private readonly List<ulong> _reconstructionRenderFrames = [];
    private readonly List<object> _reconstructionCameraObservations = [];
    private readonly List<object> _reconstructionCaptures = [];
    private readonly List<Task> _reconstructionCaptureTasks = [];
    private int _contactRenderSamples;
    private int _contactVisibleWheelSamples;
    private int _contactAirborneWheelSamples;
    private float _contactMaximumAlignmentError;
    private float _contactMaximumPlaneError;
    private readonly Dictionary<string, VehicleRuntimeResourceInventory> _runtimeResourceInventories = new(StringComparer.Ordinal);
    private int _initialRebases;
    private int _initialResets;
    private int _vehicleEpoch;
    private Vector3 _stageStart;
    private Vector3 _previousPosition;
    private float _previousWheelAngle;
    private double _signedTravel;
    private double _wheelRotation;
    private float _maximumSpeed;
    private float _maximumCompression;
    private float _minimumCompression = float.MaxValue;
    private float _maximumSteer;
    private int _minimumGrounded = 4;
    private int _teleports;
    private readonly Vector3 _initialRoadPoint;
    private readonly Vector3 _initialRoadForward;
    private bool _disposed;

    public EnduranceSedanScenario(Node parent, CannonballVehicle vehicle, WorldStreamer streamer,
        string selectedVehicle, string evidenceDirectory, Func<(CannonballVehicle, WorldStreamer)> roundTripSave, ulong seed)
    {
        _vehicle = vehicle;
        _parent = parent;
        _seed = seed;
        _captureEnabled = OS.GetCmdlineUserArgs().Contains("--sedan-captures", StringComparer.Ordinal);
        _nativeDisplay = DisplayServer.GetName() != "headless";
        _streamer = streamer;
        _selectedVehicle = selectedVehicle;
        _expectedStages = selectedVehicle == "endurance-sedan" && !OS.GetCmdlineUserArgs().Contains("--sedan-blockout", StringComparer.Ordinal)
            ? [.. ExpectedStages, "lod-driving"] : ExpectedStages;
        _evidenceDirectory = Path.GetFullPath(evidenceDirectory);
        _roundTripSave = roundTripSave;
        Directory.CreateDirectory(_evidenceDirectory);
        _frames = new StreamWriter(Path.Combine(_evidenceDirectory, "frames.jsonl"), false);
        _initialRoadPoint = streamer.InitialVehiclePoint;
        _initialRoadForward = streamer.InitialRoadForward;
        _streamer.ProcessMode = Node.ProcessModeEnum.Disabled;
        _streamer.Visible = false;
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = null;
        _vehicle.SetAssistProfile(AssistProfile.Balanced);
        _vehicle.BodyEntered += ObserveCollision;
        RenderingServer.FramePreDraw += ObserveBeforeDraw;
        if (_captureEnabled)
        {
            World.Environments.SkyLighting.Apply(parent.GetNode<DirectionalLight3D>("MoonLight"),
                parent.GetNode<WorldEnvironment>("NightEnvironment").Environment!, World.Environments.LightingPreset.Day);
        }
        parent.AddChild(_course);
        _course.SetMeta("automation_id", "vehicle.endurance-sedan.integration-course");
        BuildBox("Pad", new Vector3(-300, -0.2f, 0), new Vector3(320, 0.4f, 1200), new Color("59636a"));
        BuildBox("Bump", new Vector3(-280, 0.035f, -12), new Vector3(7, 0.07f, 1.4f), new Color("b5a879"));
        BuildBox("Barrier", new Vector3(-350, 0.65f, -10), new Vector3(9, 1.3f, 0.6f), new Color("d06c47"));
        Place(new Vector3(-250, 0, 60));
        _vehicle.Freeze = true;
        GD.Print($"CANNONBALL_ENDURANCE_SEDAN_BEGIN vehicle={selectedVehicle} stages={_expectedStages.Length} input_source=InputMap-action-fixture");
    }

    public bool Complete { get; private set; }
    public string CurrentStage => _stageIndex < _expectedStages.Length ? _expectedStages[_stageIndex] : "complete";

    public void AdvancePhysics()
    {
        if (Complete || _disposed) return;
        if (_renderFailure is not null) throw new InvalidOperationException(_renderFailure);
        _physicsFrames++;
        if (!_begun)
        {
            BeginStage();
            _begun = true;
        }
        _stageFrames++;
        if (_vehicle.VisualRig is { } activeRig)
        {
            var key = $"epoch-{_vehicleEpoch}-lod-{activeRig.ActiveLod}";
            if (!_runtimeResourceInventories.ContainsKey(key))
                _runtimeResourceInventories.Add(key, activeRig.CaptureRuntimeResourceInventory());
        }
        Sample();
        if (CurrentStage == "lod-driving") _drivingLods.Add(_vehicle.VisualRig!.ActiveLod);
        if (CurrentStage == "cameras")
        {
            if (_stageFrames is 4 or 220) Godot.Input.ActionPress(GameInputMap.ToggleCamera);
            if (_stageFrames is 6 or 222) Godot.Input.ActionRelease(GameInputMap.ToggleCamera);
            if (_stageFrames == 12)
            {
                Godot.Input.ActionPress(GameInputMap.CameraLookRight);
                Godot.Input.ActionPress(GameInputMap.CameraLookDown);
            }
            if (_stageFrames == 55) ObserveCameraDirection("right-down", 1, -1);
            if (_stageFrames == 60)
            {
                Godot.Input.ActionRelease(GameInputMap.CameraLookRight);
                Godot.Input.ActionRelease(GameInputMap.CameraLookDown);
            }
            if (_stageFrames == 130)
            {
                Godot.Input.ActionPress(GameInputMap.CameraLookLeft);
                Godot.Input.ActionPress(GameInputMap.CameraLookUp);
            }
            if (_stageFrames == 174) ObserveCameraDirection("left-up", -1, 1);
            if (_stageFrames == 178)
            {
                Godot.Input.ActionRelease(GameInputMap.CameraLookLeft);
                Godot.Input.ActionRelease(GameInputMap.CameraLookUp);
            }
            _cockpitObserved |= _vehicle.CurrentCameraMode == "cockpit";
        }
        if (CurrentStage == "reset" && _stageFrames == 5)
        {
            Godot.Input.ActionPress(GameInputMap.ResetVehicle);
        }
        if (CurrentStage == "reset" && _stageFrames == 7)
        {
            Godot.Input.ActionRelease(GameInputMap.ResetVehicle);
        }
        if (CurrentStage == "starter-policy" && _stageFrames == 240)
        {
            // A declared seeded overspeed probes the governor, not acceleration performance.
            _vehicle.LinearVelocity = -_vehicle.GlobalBasis.Z * 65;
            WriteEvent("seeded-overspeed", new { speed_mps = 65 });
        }
        if (!StageFinished() || _captureEnabled && !_capturedStages.Contains(CurrentStage))
        {
            if (_stageFrames > 14400) throw new InvalidOperationException($"Sedan stage timed out: {CurrentStage}");
            return;
        }
        ValidateStage();
        var result = new
        {
            stage = CurrentStage, status = "passed", physics_frames = _stageFrames,
            signed_travel_m = _signedTravel, wheel_rotation_rad = _wheelRotation,
            maximum_speed_mps = _maximumSpeed, final_signed_speed_mps = _vehicle.SignedLongitudinalSpeedMetersPerSecond,
            minimum_grounded = _minimumGrounded, compression_min_m = _minimumCompression,
            compression_max_m = _maximumCompression, maximum_steer_rad = _maximumSteer,
            teleports = _teleports, rebases = _streamer.RebaseCount - _initialRebases,
            resets = _vehicle.ResetToRoadCount - _initialResets,
            vehicle_epoch = _vehicleEpoch,
            observed_driving_lods = CurrentStage == "lod-driving" ? _drivingLods.Order().ToArray() : [],
            camera_direction_checks = CurrentStage == "cameras" ? _cameraDirectionChecks : null,
        };
        _results.Add(result);
        GD.Print($"CANNONBALL_ENDURANCE_SEDAN_STAGE_OK vehicle={_selectedVehicle} stage={CurrentStage} frames={_stageFrames}");
        _frames.Flush();
        ReleaseActions();
        _stageIndex++;
        _stageFrames = 0;
        _begun = false;
        if (_stageIndex == _expectedStages.Length) Finish();
    }

    public void AdvanceRender()
    {
        if (_renderFailure is not null) throw new InvalidOperationException(_renderFailure);
        if (_captureTask is { IsFaulted: true }) _captureTask.GetAwaiter().GetResult();
        foreach (var task in _reconstructionCaptureTasks)
            if (task.IsFaulted) task.GetAwaiter().GetResult();
        ObserveReconstructedCamera(rendered: false);
        if (_fixtureInterpolationResetPending)
        {
            // Place is an explicit fixture teleport. Reset after the ensuing
            // physics updates have refreshed suspension/steering child poses.
            _vehicle.ResetPhysicsInterpolation();
            _fixtureInterpolationResetPending = false;
            WriteEvent("fixture-interpolation-reset", new { render_frame = Engine.GetProcessFrames(),
                operation = "after fixture Place physics updates, before draw" });
        }
        ObserveRebaseFrame(rendered: false);
        if (_captureEnabled && !Complete && _begun && _stageFrames >= CaptureAfterFrames() &&
            (CurrentStage is not ("natural-rebase" or "forced-rebase") || RebaseFramesReady(rendered: true)) &&
            !_capturedStages.Contains(CurrentStage) && (_captureTask is null || _captureTask.IsCompleted))
        {
            _captureTask = CaptureFrameAsync(CurrentStage);
        }
    }

    /// <summary>Called by Main at PhysicsFrame, before native spring-arm collision/placement.</summary>
    public void ApplyPendingReconstruction()
    {
        if (_disposed || Complete) return;
        if (CurrentStage != "save-resume" || _resumeComplete || !_begun) return;
        var previousEpoch = _vehicleEpoch;
        var previousResetCount = _vehicle.ResetToRoadCount;
        var previousRebaseCount = _streamer.RebaseCount;
        var previousPresentation = _vehicle.VisualRig?.Presentation?.CaptureSnapshot();
        _vehicle.BodyEntered -= ObserveCollision;
        (_vehicle, _streamer) = _roundTripSave();
        _vehicleEpoch++;
        // Reset and rebase counters belong to the reconstructed objects, not
        // the persisted run. Never subtract an earlier instance's baseline.
        _initialResets = _vehicle.ResetToRoadCount;
        _initialRebases = _streamer.RebaseCount;
        _vehicle.BodyEntered += ObserveCollision;
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = null;
        _vehicle.Freeze = false;
        _resumeComplete = true;
        _previousPosition = _vehicle.Position;
        _previousWheelAngle = _vehicle.VisualRig?.WheelRotationRadians ?? 0;
        WriteEvent("save-resume-reconstruction", new
        {
            selected_vehicle = _selectedVehicle, loaded_asset = _vehicle.RigSetup.AssetId,
            mass_kg = _vehicle.Mass, speed_policy = _vehicle.Setup.Id,
            equivalence_method = "existing Main.ValidateResumedRuntime plus exact persisted state comparison",
            previous_vehicle_epoch = previousEpoch, vehicle_epoch = _vehicleEpoch,
            previous_reset_count = previousResetCount, reconstructed_reset_count = _initialResets,
            previous_rebase_count = previousRebaseCount, reconstructed_rebase_count = _initialRebases,
            presentation_policy = "Selected asset ID persists separately; lamps, wipers, indicators and openings reconstruct at defaults.",
            previous_presentation = previousPresentation, reconstructed_presentation = _vehicle.VisualRig?.Presentation?.CaptureSnapshot(),
        });
    }

    private int CaptureAfterFrames() => CurrentStage switch
    {
        "controller-braking" => 35, "natural-rebase" or "forced-rebase" => 3,
        "save-resume" => 8, "starter-policy" => 245, "cameras" => 110,
        "suspension" => 320, "collision" => 240, "keyboard-acceleration" => 180,
        "lod-driving" => 480,
        _ => 90,
    };

    private async Task CaptureFrameAsync(string stage)
    {
        await _parent.ToSignal(RenderingServer.Singleton, RenderingServer.SignalName.FramePostDraw);
        var viewport = _parent.GetViewport();
        using var texture = viewport.GetTexture();
        using var image = texture.GetImage();
        if (image is null || image.IsEmpty()) throw new InvalidOperationException("Rendered sedan capture has no image; headless output is not visual evidence.");
        var path = Path.Combine(_evidenceDirectory, $"{_stageIndex + 1:00}-{stage}.png");
        var error = image.SavePng(path);
        if (error != Error.Ok) throw new IOException($"Could not save actual runtime capture: {error}");
        if (stage is "natural-rebase" or "forced-rebase")
        {
            Require(RebaseFramesReady(rendered: true), "rebase image preceded three actual rendered event observations");
            var observation = _rebaseObservations[stage];
            observation.CapturedRenderFrame = Engine.GetProcessFrames();
            observation.CapturedRebaseCount = _streamer.RebaseCount;
            Require(observation.CapturedRebaseCount == observation.RebaseCount,
                "rebase counter changed before its event image was captured");
            if (stage == "forced-rebase")
            {
                var natural = _rebaseObservations["natural-rebase"];
                Require(natural.CapturedRenderFrame is { } previousFrame && previousFrame < observation.CapturedRenderFrame &&
                    natural.CapturedRebaseCount < observation.CapturedRebaseCount,
                    "natural and forced rebases need separate ordered images and counters");
            }
        }
        _captures.Add(new
        {
            stage, physics_frame = _physicsFrames, render_frame = Engine.GetProcessFrames(),
            camera = _vehicle.CurrentCameraMode, camera_position = Vector(viewport.GetCamera3D().GlobalPosition),
            camera_node = viewport.GetCamera3D().Name.ToString(), camera_fov = viewport.GetCamera3D().Fov,
            frozen = _vehicle.Freeze, renderer = RenderingServer.GetCurrentRenderingMethod().ToString(),
            display_driver = DisplayServer.GetName(), size = new[] { image.GetWidth(), image.GetHeight() },
            render_quality = new
            {
                actual_msaa_3d = viewport.Msaa3D.ToString(),
                applied_tier = viewport.GetMeta("render_quality", "missing").AsString(),
                applied_directional_shadow_size = viewport.GetMeta("directional_shadow_size", -1).AsInt32(),
                global_quality_basis = "Atlas/tier are applied-call metadata; MSAA is a live Viewport property.",
            },
            lighting = _parent.GetNode<WorldEnvironment>("NightEnvironment").Environment!.GetMeta("lighting_preset", "missing").AsString(),
            before_draw = _renderedState, after_draw = CaptureRenderState(),
            path, sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant(),
        });
        _capturedStages.Add(stage);
    }

    private object CaptureRenderState()
    {
        var camera = _parent.GetViewport().GetCamera3D();
        var presentation = _vehicle.VisualRig?.Presentation;
        var displayedBody = _vehicle.GetGlobalTransformInterpolated().Origin;
        return new
        {
            stage = CurrentStage, physics_frame = _physicsFrames, render_frame = Engine.GetProcessFrames(),
            vehicle_epoch = _vehicleEpoch, local_origin = _streamer.CaptureStreamSnapshot(),
            rebase_observation = _rebaseObservations.TryGetValue(CurrentStage, out var observation) ? observation.Snapshot() : null,
            active_lod = _vehicle.VisualRig?.ActiveLod, camera_node = camera?.Name.ToString(),
            body_position = Vector(_vehicle.GlobalPosition), displayed_body_position = Vector(displayedBody),
            camera_position = camera is null ? null : Vector(camera.GlobalPosition),
            displayed_distance_m = camera?.GlobalPosition.DistanceTo(displayedBody),
            contact_shading = _vehicle.ContactShading?.CaptureSnapshot(),
            lod_selection = presentation is null ? null : new
            {
                render_frame = presentation.LodSelectionRenderFrame,
                initialized = presentation.LodSelectionInitialized,
                created_render_frame = presentation.CreatedRenderFrame,
                distance_m = presentation.LodSelectionDistanceMeters,
                camera_position = Vector(presentation.LodSelectionCameraPosition),
                body_position = Vector(presentation.LodSelectionBodyPosition),
            },
        };
    }

    private void ObserveBeforeDraw()
    {
        if (_disposed || Complete) return;
        ObserveContactShading();
        ObserveReconstructedCamera(rendered: true);
        ObserveRebaseFrame(rendered: true);
        _renderedState = CaptureRenderState();
        _frames.WriteLine(JsonSerializer.Serialize(new { kind = "before-draw", state = _renderedState }));
        if (_vehicle.VisualRig?.Presentation is not { AutoLodEnabled: true } presentation ||
            _parent.GetViewport().GetCamera3D() is not { } camera) return;
        // A body reconstructed during this frame's process traversal can
        // first render before its new presenter receives a process callback.
        // Its explicit initial LOD0 is conservative, not a stale selection.
        if (!presentation.LodSelectionInitialized)
        {
            if (_vehicle.VisualRig.ActiveLod != 0 || Engine.GetProcessFrames() - presentation.CreatedRenderFrame > 1)
                _renderFailure = "New sedan presentation did not initialize LOD after its first render frame.";
            return;
        }
        var distance = camera.GlobalPosition.DistanceTo(_vehicle.GetGlobalTransformInterpolated().Origin);
        var expected = presentation.AnyOpeningActive || _vehicle.CurrentCameraMode == "cockpit" || _vehicle.InspectionActive ? 0 :
            distance >= presentation.Setup.Lod2DistanceMeters ? 2 : distance >= presentation.Setup.Lod1DistanceMeters ? 1 : 0;
        if (_vehicle.VisualRig.ActiveLod != expected || Math.Abs(presentation.LodSelectionDistanceMeters - distance) > 0.01f ||
            presentation.LodSelectionRenderFrame != Engine.GetProcessFrames())
            _renderFailure = $"Rendered sedan LOD used stale camera/body state in {CurrentStage}: " +
                $"selected={_vehicle.VisualRig.ActiveLod}, expected={expected}, distance={distance}, " +
                $"selection_distance={presentation.LodSelectionDistanceMeters}.";
    }

    private void ObserveContactShading()
    {
        if (_vehicle.ContactShading is not { SupportedRenderer: true } contact) return;
        _contactRenderSamples++;
        for (var i = 0; i < 4; i++)
        {
            var state = contact.ReadWheel(i);
            if (!state.Supported) _contactAirborneWheelSamples++;
            if (state.Visible != (state.Supported && state.EligibleReceiver))
                _renderFailure = "Contact shading visibility disagrees with actual contact/receiver eligibility.";
            if (!state.Visible) continue;
            _contactVisibleWheelSamples++;
            _contactMaximumAlignmentError = Math.Max(_contactMaximumAlignmentError,
                Math.Max(state.DerivedDisplayErrorMeters, state.WheelTangentialErrorMeters));
            _contactMaximumPlaneError = Math.Max(_contactMaximumPlaneError, state.ContactPlaneErrorMeters);
            if (state.DerivedDisplayErrorMeters > .001f || state.WheelTangentialErrorMeters > .001f ||
                state.ContactPlaneErrorMeters > .001f)
                _renderFailure = $"Rendered contact shading lost wheel/contact-plane alignment in {CurrentStage}.";
        }
    }

    private void BeginStage()
    {
        ReleaseActions();
        _maximumSpeed = _maximumSteer = _maximumCompression = 0;
        _minimumCompression = float.MaxValue;
        _minimumGrounded = 4;
        _signedTravel = _wheelRotation = 0;
        _teleports = 0;
        _initialRebases = _streamer.RebaseCount;
        _initialResets = _vehicle.ResetToRoadCount;
        _vehicle.Freeze = false;
        switch (CurrentStage)
        {
            case "static-ride":
                Require(_vehicle.RigSetup.AssetId == (_selectedVehicle == "graybox" ? "hero-gt" : _selectedVehicle), "loaded vehicle identity mismatch");
                Require(_selectedVehicle != "graybox" || _vehicle.UsesGrayboxVisual, "graybox fallback not selected");
                Require(_vehicle.UsesGrayboxVisual || _vehicle.VisualRig?.ContractResolved == true, "visual contract unresolved");
                break;
            case "keyboard-acceleration": Godot.Input.ActionPress(GameInputMap.Accelerate); break;
            case "keyboard-braking": Godot.Input.ActionPress(GameInputMap.Brake); break;
            case "controller-acceleration": Godot.Input.ActionPress(GameInputMap.AccelerateController, 0.65f); break;
            case "controller-braking": Godot.Input.ActionPress(GameInputMap.BrakeController); break;
            case "reverse": Godot.Input.ActionPress(GameInputMap.Reverse); break;
            case "steer-left":
            case "steer-right":
                Place(new Vector3(-250, 0, 60));
                _vehicle.LinearVelocity = Vector3.Forward * 10;
                Godot.Input.ActionPress(GameInputMap.Accelerate, 0.25f);
                Godot.Input.ActionPress(CurrentStage == "steer-left" ? GameInputMap.SteerLeft : GameInputMap.SteerRight, 0.65f);
                break;
            case "suspension":
                Place(new Vector3(-280, 0, 15));
                _vehicle.LinearVelocity = Vector3.Forward * 10;
                break;
            case "collision":
                Place(new Vector3(-350, 0, 12));
                _collisionObserved = false;
                Godot.Input.ActionPress(GameInputMap.Accelerate);
                break;
            case "reset":
                Place(new Vector3(-250, 0, 60));
                _vehicle.Position += new Vector3(12, 5, 9);
                _vehicle.Rotation = new Vector3(0.3f, 0.8f, 0.4f);
                _vehicle.LinearVelocity = new Vector3(6, -2, 4);
                _vehicle.AngularVelocity = Vector3.One;
                _vehicle.TargetRoadPoint = new Vector3(-250, 0, 60);
                if (_vehicle.VisualRig?.Presentation is { } resetPresentation)
                {
                    resetPresentation.SetHeadlampMode(1);
                    resetPresentation.SetWipers(true);
                    resetPresentation.SetIndicator(-1);
                }
                WriteEvent("reset-setup-teleport", new { destination = Vector(_vehicle.Position) });
                _teleports++;
                break;
            case "cameras":
                _vehicle.SetCameraMode(false);
                _savedCameraStabilization = _vehicle.CockpitCameraRig.MaximumStabilizationDegrees;
                _vehicle.CockpitCameraRig.MaximumStabilizationDegrees = 0;
                break;
            case "natural-rebase":
                _course.Visible = false;
                _course.ProcessMode = Node.ProcessModeEnum.Disabled;
                _streamer.ProcessMode = Node.ProcessModeEnum.Inherit;
                _streamer.Visible = true;
                Place(_initialRoadPoint, _initialRoadForward);
                _vehicle.AutopilotEnabled = true;
                _vehicle.AutopilotSpeedLimitMetersPerSecond = 32;
                if (_vehicle.VisualRig?.Presentation is { } rebasePresentation)
                {
                    rebasePresentation.SetIndicator(0);
                    rebasePresentation.SetHazards(true);
                }
                break;
            case "forced-rebase":
                _vehicle.AutopilotEnabled = false;
                _vehicle.Freeze = true;
                var target = Math.Min(_streamer.TotalRouteLengthMeters - 100, _streamer.RouteDistanceMeters + 1800);
                Require(target > _streamer.RouteDistanceMeters + 1100, "fixture lacks route length for a distinct forced rebase");
                _streamer.SetReviewDistance(target);
                WriteEvent("forced-route-review-placement", new { distance_m = target });
                _teleports++;
                break;
            case "save-resume": _vehicle.Freeze = true; break;
            case "starter-policy":
                _streamer.ProcessMode = Node.ProcessModeEnum.Disabled;
                _streamer.Visible = false;
                _course.Visible = true;
                _course.ProcessMode = Node.ProcessModeEnum.Inherit;
                Place(new Vector3(-250, 0, 400));
                _vehicle.Setup = VehicleSetup.Starter;
                break;
            case "lod-driving":
                Place(new Vector3(-250, 0, 60));
                _vehicle.LinearVelocity = Vector3.Forward * 8;
                Godot.Input.ActionPress(GameInputMap.Accelerate, 0.25f);
                _vehicle.SetCameraMode(false);
                _lodObserver = new Camera3D { Name = "LodDrivingObserver", Position = new Vector3(-248, 1.6f, 80), Fov = 38, Far = 500 };
                _parent.AddChild(_lodObserver);
                _lodObserver.LookAt(new Vector3(-250, 0.85f, -50), Vector3.Up);
                _lodObserver.MakeCurrent();
                _drivingLods.Clear();
                break;
        }
        _stageStart = _previousPosition = _vehicle.Position;
        _previousWheelAngle = _vehicle.VisualRig?.WheelRotationRadians ?? 0;
        WriteEvent("stage-begin", new
        {
            stage = CurrentStage, frozen = _vehicle.Freeze, body = Vector(_vehicle.Position),
            fixture_visible = _course.Visible, route_geometry_visible = _streamer.Visible,
            fixture_physics_enabled = _course.ProcessMode != Node.ProcessModeEnum.Disabled,
            route_physics_enabled = _streamer.ProcessMode != Node.ProcessModeEnum.Disabled,
        });
    }

    private bool StageFinished() => CurrentStage switch
    {
        "static-ride" => _stageFrames >= 240,
        "keyboard-acceleration" => _stageFrames >= 360,
        "keyboard-braking" => _stageFrames >= 480,
        "controller-acceleration" or "reverse" => _stageFrames >= 240,
        // Holding LT after the car stops intentionally requests reverse under
        // the existing controller contract. Release at the observed stop.
        "controller-braking" => _stageFrames >= 4 && Math.Abs(_vehicle.SignedLongitudinalSpeedMetersPerSecond) < 0.5f,
        "steer-left" or "steer-right" => _stageFrames >= 180,
        "suspension" => _stageFrames >= 420,
        "collision" => _stageFrames >= 420,
        "reset" => _stageFrames >= 120,
        "cameras" => _stageFrames >= 280,
        "natural-rebase" => _streamer.RebaseCount > _initialRebases && _stageFrames > 240 && RebaseFramesReady(rendered: false),
        "forced-rebase" => _streamer.ReviewTargetReady && _streamer.RebaseCount > _initialRebases && _stageFrames > 4 && RebaseFramesReady(rendered: false),
        "save-resume" => _resumeComplete && _stageFrames >= 12 &&
            _reconstructionProcessFrames.Count >= 3 && (!_nativeDisplay || _reconstructionRenderFrames.Count >= 3) &&
            _reconstructionCaptureTasks.All(task => task.IsCompleted),
        "starter-policy" => _stageFrames >= 250,
        "lod-driving" => _stageFrames >= 1440,
        _ => throw new InvalidOperationException($"Unknown sedan stage {CurrentStage}"),
    };

    private void ValidateStage()
    {
        var speed = _vehicle.SignedLongitudinalSpeedMetersPerSecond;
        switch (CurrentStage)
        {
            case "static-ride":
                Require((_vehicle.ContactShading is not null) == (_vehicle.RigSetup.ContactShadingEnabled && !_vehicle.UsesGrayboxVisual),
                    "contact-shading setup selection mismatch");
                if (_vehicle.ContactShading is { SupportedRenderer: true })
                    Require(_contactVisibleWheelSamples > 0, "native contact shading never reached a contacted receiver");
                Require(_vehicle.GroundedWheelCount == 4, "static ride lacks four contacts");
                Require(Math.Abs(_vehicle.RideHeightMeters - _vehicle.RigSetup.ChassisOriginHeightMeters) <= 0.02, "static ride height differs by more than20mm");
                var collisionShapes = _vehicle.GetChildren().OfType<CollisionShape3D>().ToArray();
                Require(collisionShapes.Length == (_vehicle.RigSetup.AssetId == "endurance-sedan" ? 2 : 1), "unexpected rigid-body collision-shape count");
                foreach (var collision in collisionShapes)
                {
                    using var shape = collision.Shape;
                    Require(shape is BoxShape3D, "vehicle collision must use convex boxes, not imported triangle geometry");
                    var expectedSize = collision.Name == "CabinCollision" ? _vehicle.RigSetup.CabinCollisionBoxSize : _vehicle.RigSetup.CollisionBoxSize;
                    Require(((BoxShape3D)shape).Size.IsEqualApprox(expectedSize), "actual collision shape differs from setup dimensions");
                }
                break;
            case "keyboard-acceleration":
            case "controller-acceleration":
                Require(speed > 8 && _signedTravel > 5 && _vehicle.LastDriveInput.Throttle > 0.1, "input-driven acceleration missing");
                if (_vehicle.VisualRig is not null)
                    Require(Math.Sign(_wheelRotation) == Math.Sign(_vehicle.RigSetup.WheelRollingSign), "forward wheel rolling direction mismatch");
                break;
            case "keyboard-braking":
            case "controller-braking":
                Require(Math.Abs(speed) < 0.6 && _maximumSpeed > 8, "input-driven braking did not stop vehicle");
                break;
            case "reverse":
                Require(speed < -5 && _signedTravel < -2 && _vehicle.LastDriveInput.Reverse > 0.1, "reverse input did not move vehicle backward");
                if (_vehicle.VisualRig is not null)
                    Require(Math.Sign(_wheelRotation) == -Math.Sign(_vehicle.RigSetup.WheelRollingSign), "reverse wheel rolling direction mismatch");
                break;
            case "steer-left":
                Require(_maximumSteer > 0.05 && _vehicle.Position.X < _stageStart.X - 0.3f, "left steering did not change physical trajectory");
                break;
            case "steer-right":
                Require(_maximumSteer > 0.05 && _vehicle.Position.X > _stageStart.X + 0.3f, "right steering did not change physical trajectory");
                break;
            case "suspension":
                Require(_maximumCompression - _minimumCompression > 0.035, "bump did not exercise suspension state");
                Require(_vehicle.Position.Z < -13, "vehicle did not traverse bump");
                break;
            case "collision":
                Require(_collisionObserved && _vehicle.Position.Z > -10, "barrier contact missing or vehicle tunneled through");
                break;
            case "reset":
                Require(_vehicle.ResetToRoadCount == _initialResets + 1, "InputMap reset action did not reset exactly once");
                // Reuse the existing actual-engine reset contract, which is
                // measured after suspension settling (VehicleDynamicsScenario).
                Require(new Vector2(_vehicle.Position.X + 250, _vehicle.Position.Z - 60).Length() <= 0.1 &&
                    _vehicle.SpeedMetersPerSecond <= 0.1 && _vehicle.AngularVelocity.Length() <= 0.1 &&
                    _vehicle.GroundedWheelCount >= 3 && _vehicle.Position.Y is >= 0.5f and <= 1.5f,
                    "reset did not restore supported local pose and clear motion under the existing reset contract");
                RequirePresentationRetained(hazards: false, indicator: -1);
                break;
            case "cameras":
                Require(_cockpitObserved && _vehicle.CurrentCameraMode == "chase", "camera switch did not visit cockpit and return");
                Require(_cameraDirectionChecks.Count == 2, "actual camera look direction checks missing");
                _vehicle.CockpitCameraRig.MaximumStabilizationDegrees = _savedCameraStabilization!.Value;
                _savedCameraStabilization = null;
                RequirePresentationRetained(hazards: false, indicator: -1);
                break;
            case "natural-rebase":
                Require(_vehicle.ResetToRoadCount == _initialResets, "natural rebase traversal included recovery reset");
                Require(_streamer.RebaseCount > _initialRebases && _streamer.RouteDistanceMeters > 900, "drive did not cross natural rebase threshold");
                Require(new Vector2(_vehicle.Position.X, _vehicle.Position.Z).Length() < 1000, "natural rebase failed to bound local coordinates");
                RequirePresentationRetained(hazards: true, indicator: 0);
                break;
            case "forced-rebase":
                Require(_streamer.RebaseCount > _initialRebases && _streamer.ReviewTargetReady, "forced rebase placement incomplete");
                RequirePresentationRetained(hazards: true, indicator: 0);
                break;
            case "save-resume":
                Require(_resumeComplete, "save/resume callback incomplete");
                var cameraFrames = _nativeDisplay ? _reconstructionRenderFrames : _reconstructionProcessFrames;
                Require(_renderFailure is null && cameraFrames.Count == 3 &&
                    cameraFrames[1] == cameraFrames[0] + 1 && cameraFrames[2] == cameraFrames[1] + 1,
                    "first reconstructed chase-camera frames are invalid or not consecutive");
                if (_vehicle.VisualRig?.Presentation is { } resumedPresentation)
                    Require(resumedPresentation.HeadlampMode == 0 && !resumedPresentation.WipersOn &&
                        !resumedPresentation.HazardsOn && resumedPresentation.IndicatorDirection == 0 &&
                        !resumedPresentation.AnyOpeningActive, "reconstructed presentation does not match the explicit default-state policy");
                break;
            case "starter-policy":
                Require(_vehicle.Setup == VehicleSetup.Starter && speed <= 125 * 0.44704 + 0.02 && speed > 40,
                    "starter125mph policy failed on the selected physical setup");
                _vehicle.Setup = VehicleSetup.HighSpeedValidation;
                Require(_vehicle.Setup.ForwardTopSpeedMph == 250, "validation250mph policy changed");
                break;
            case "lod-driving":
                Require(!_vehicle.Freeze && _signedTravel > 65 && Math.Abs(_wheelRotation) > 1 && _drivingLods.SetEquals([0, 1, 2]),
                    "unfrozen driving did not cross both LOD thresholds with visible rolling state");
                break;
        }
    }

    private void Sample()
    {
        var forward = -_vehicle.GlobalBasis.Z.Normalized();
        var displacement = _vehicle.Position - _previousPosition;
        // Origin changes are recorded separately; their coordinate translation is not travel.
        if (displacement.Length() < 5) _signedTravel += displacement.Dot(forward);
        var angle = _vehicle.VisualRig?.WheelRotationRadians ?? 0;
        var angleDelta = Mathf.Wrap(angle - _previousWheelAngle, -Mathf.Pi, Mathf.Pi);
        _wheelRotation += angleDelta;
        _previousWheelAngle = angle;
        _previousPosition = _vehicle.Position;
        _maximumSpeed = Math.Max(_maximumSpeed, _vehicle.SpeedMetersPerSecond);
        _maximumSteer = Math.Max(_maximumSteer, Math.Abs(_vehicle.CurrentSteeringRadians));
        _minimumGrounded = Math.Min(_minimumGrounded, _vehicle.GroundedWheelCount);
        var wheels = new object[4];
        for (var index = 0; index < 4; index++)
        {
            var ray = _vehicle.SuspensionRay(index);
            var compression = _vehicle.SuspensionCompressionMeters(index);
            _maximumCompression = Math.Max(_maximumCompression, compression);
            _minimumCompression = Math.Min(_minimumCompression, compression);
            var colliding = ray.IsColliding();
            wheels[index] = new
            {
                index, contact = colliding,
                body = colliding ? (ray.GetCollider() as Node)?.Name.ToString() : null,
                position = colliding ? Vector(ray.GetCollisionPoint()) : null,
                compression_m = compression,
                displacement_from_static_m = compression - _vehicle.RigSetup.StaticCompressionMeters,
            };
        }
        _frames.WriteLine(JsonSerializer.Serialize(new
        {
            kind = "physics-frame", frame = _physicsFrames, stage = CurrentStage, stage_frame = _stageFrames,
            vehicle_epoch = _vehicleEpoch,
            input_source = _vehicle.AutopilotEnabled ? "route-autopilot" : "InputMap-action-fixture",
            frozen = _vehicle.Freeze, position = Vector(_vehicle.Position), velocity = Vector(_vehicle.LinearVelocity),
            basis = new[] { Vector(_vehicle.GlobalBasis.X), Vector(_vehicle.GlobalBasis.Y), Vector(_vehicle.GlobalBasis.Z) },
            angular_velocity = Vector(_vehicle.AngularVelocity), input = _vehicle.LastDriveInput,
            input_device = _vehicle.DrivingInputController.Current.Device.ToString(),
            signed_speed_mps = _vehicle.SignedLongitudinalSpeedMetersPerSecond,
            signed_travel_m = _signedTravel, wheel_angle_rad = angle, wheel_delta_rad = angleDelta,
            tire_radius_m = _vehicle.RigSetup.TireRadiusMeters, wheels,
            steering_rad = _vehicle.CurrentSteeringRadians, camera = _vehicle.CurrentCameraMode,
            camera_node = _parent.GetViewport().GetCamera3D()?.Name.ToString(),
            camera_forward = Vector(-_vehicle.CockpitCameraRig.Camera.GlobalBasis.Z.Normalized()),
            camera_look_actions = new
            {
                left = Godot.Input.GetActionStrength(GameInputMap.CameraLookLeft),
                right = Godot.Input.GetActionStrength(GameInputMap.CameraLookRight),
                up = Godot.Input.GetActionStrength(GameInputMap.CameraLookUp),
                down = Godot.Input.GetActionStrength(GameInputMap.CameraLookDown),
            },
            presentation_lifecycle = _vehicle.VisualRig?.Presentation is { } presentation ? new
            {
                headlamp_mode = presentation.HeadlampMode, wipers_on = presentation.WipersOn,
                hazards_on = presentation.HazardsOn, indicator = presentation.IndicatorDirection,
                openings_active = presentation.AnyOpeningActive,
            } : null,
            route_distance_m = _streamer.RouteDistanceMeters, local_origin = _streamer.CaptureStreamSnapshot(),
            resets = _vehicle.ResetToRoadCount, contacts = _vehicle.GetContactCount(), lod = _vehicle.VisualRig?.ActiveLod,
        }));
    }

    private void Place(Vector3 point, Vector3? forward = null)
    {
        _vehicle.Freeze = true;
        _vehicle.GlobalTransform = new Transform3D(Basis.LookingAt(forward ?? Vector3.Forward, Vector3.Up),
            point + Vector3.Up * _vehicle.RigSetup.ChassisOriginHeightMeters);
        _vehicle.LinearVelocity = Vector3.Zero;
        _vehicle.AngularVelocity = Vector3.Zero;
        _vehicle.TargetRoadPoint = point;
        _vehicle.TargetRoadForward = forward ?? Vector3.Forward;
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = null;
        _vehicle.ResetPhysicsInterpolation();
        _fixtureInterpolationResetPending = true;
        _vehicle.ChaseCameraRig.SnapToTarget();
        _vehicle.Freeze = false;
        _teleports++;
        WriteEvent("fixture-placement", new { destination = Vector(_vehicle.Position) });
    }

    private void BuildBox(string name, Vector3 center, Vector3 size, Color color)
    {
        using var shape = new BoxShape3D { Size = size };
        using var material = new StandardMaterial3D { AlbedoColor = color, Roughness = 0.82f };
        using var mesh = new BoxMesh { Size = size, Material = material };
        var body = new StaticBody3D { Name = $"Endurance{name}", Position = center, CollisionLayer = 1, CollisionMask = 2 };
        body.AddChild(new CollisionShape3D { Shape = shape });
        body.AddChild(new MeshInstance3D { Mesh = mesh });
        _course.AddChild(body);
    }

    private void ObserveCollision(Node body) => _collisionObserved |= body.Name == "EnduranceBarrier";

    private void RequirePresentationRetained(bool hazards, int indicator)
    {
        if (_vehicle.VisualRig?.Presentation is not { } presentation) return;
        Require(presentation.HeadlampMode == 1 && presentation.HeadlightsOn && presentation.WipersOn &&
            presentation.HazardsOn == hazards && presentation.IndicatorDirection == indicator,
            "live presentation settings changed across a reset, camera transition or rebase");
        WriteEvent("presentation-lifecycle", new { operation = CurrentStage, expected_headlamp_mode = 1,
            expected_wipers_on = true, expected_hazards_on = hazards, expected_indicator = indicator,
            observed = presentation.CaptureSnapshot() });
    }

    private void ObserveCameraDirection(string direction, int rightSign, int upSign)
    {
        var cameraForward = -_vehicle.CockpitCameraRig.Camera.GlobalBasis.Z.Normalized();
        var chassisBasis = _vehicle.GetGlobalTransformInterpolated().Basis.Orthonormalized();
        var rightDot = cameraForward.Dot(chassisBasis.X);
        var upDot = cameraForward.Dot(chassisBasis.Y);
        var state = new
        {
            input = direction, camera_forward = Vector(cameraForward),
            chassis_right = Vector(chassisBasis.X), chassis_up = Vector(chassisBasis.Y),
            right_dot = rightDot, up_dot = upDot, stabilization_degrees = _vehicle.CockpitCameraRig.MaximumStabilizationDegrees,
            input_space_angles = _vehicle.CockpitCameraRig.CaptureSnapshot(),
        };
        WriteEvent("camera-direction", state);
        Require(_vehicle.CockpitCameraRig.IsActive && rightDot * rightSign > 0.1f && upDot * upSign > 0.1f,
            $"actual camera forward vector points against {direction}: chassis-right dot={rightDot}, chassis-up dot={upDot}");
        _cameraDirectionChecks.Add(direction, state);
    }
    private static double[] Vector(Vector3 value) => [value.X, value.Y, value.Z];
    private void WriteEvent(string kind, object state) =>
        _frames.WriteLine(JsonSerializer.Serialize(new { kind, stage = CurrentStage, frame = _physicsFrames, state }));
    private static void ReleaseActions() { foreach (var action in Actions) Godot.Input.ActionRelease(action); }
    private void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException($"Sedan integration '{CurrentStage}' failed: {message}");
    }

    private void Finish()
    {
        _vehicle.AutopilotEnabled = false;
        _vehicle.AutomationInputOverride = null;
        _vehicle.Freeze = true;
        _frames.Flush();
        _frames.Dispose();
        var inputs = new Dictionary<string, string>();
        var unavailableInputs = new List<string>();
        foreach (var path in new[]
        {
            "game/Vehicle/CannonballVehicle.cs", "game/Vehicle/VehicleVisualRig.cs", "game/Vehicle/VehicleRigSetup.cs",
            "game/Vehicle/VehicleContactShading.cs", "game/Vehicle/VehicleContactShading.cs.uid",
            "game/Vehicle/Setups/HeroGt.tres", "game/Vehicle/Setups/EnduranceSedan.tres",
            "game/Automation/EnduranceSedanScenario.cs", "game/Main.cs", "game/Camera/CockpitCameraRig.cs",
            "game/Input/GameInputMap.cs", "scripts/verify-endurance-sedan.sh",
            "docs/vehicles/endurance-sedan/specification.json", "tools/vehicles/vehicle_contract.json", "tools/assets/toolchain.json",
            $"data/assets/vehicles/sources/{_vehicle.RigSetup.AssetId}.blend",
            $"data/assets/vehicles/derived/{_vehicle.RigSetup.AssetId}.glb",
            $"assets/vehicles/{_vehicle.RigSetup.AssetId}/{_vehicle.RigSetup.AssetId}.generated.tscn",
        })
        {
            var absolute = ProjectSettings.GlobalizePath("res://" + path);
            if (File.Exists(absolute)) inputs[path] = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(absolute))).ToLowerInvariant();
            else unavailableInputs.Add(path);
        }
        var framePath = Path.Combine(_evidenceDirectory, "frames.jsonl");
        File.WriteAllText(Path.Combine(_evidenceDirectory, "summary.json"), JsonSerializer.Serialize(new
        {
            schema_version = 1, task_id = "P1-018", milestone = "M5", status = "passed",
            stage_scope = OS.GetCmdlineUserArgs().Contains("--sedan-blockout", StringComparer.Ordinal) ? "blockout-functional-integration" : "vehicle-functional-integration", expected_stages = _expectedStages,
            blockout_presentation_omitted = OS.GetCmdlineUserArgs().Contains("--sedan-blockout", StringComparer.Ordinal),
            completed_stages = _results, vehicle = _selectedVehicle, loaded_asset = _vehicle.RigSetup.AssetId,
            rebase_observations = _rebaseObservations.ToDictionary(pair => pair.Key, pair => pair.Value.Snapshot(), StringComparer.Ordinal),
            git_revision = OS.GetEnvironment("CANNONBALL_GIT_REVISION"), utc = DateTimeOffset.UtcNow,
            platform = OS.GetName(), engine = Engine.GetVersionInfo()["string"].AsString(),
            dotnet = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            scenario_arguments = OS.GetCmdlineUserArgs(), deterministic_seed = _seed,
            physics_hz = Engine.PhysicsTicksPerSecond, physics_frames = _physicsFrames,
            input_hashes = inputs, human_approval = (string?)null,
            input_hash_scope = "physically available repository files; packaged PCK/assembly hashes are bound by the external package verifier",
            unavailable_input_paths = unavailableInputs, user_data_directory = OS.GetUserDataDir(),
            executable_path = OS.GetExecutablePath(), runtime_is_debug_build = OS.IsDebugBuild(),
            modeled_fuel_capacity_l = _vehicle.RigSetup.AssetId == "endurance-sedan" ? 175 : 82,
            fixed_running_mass_kg = _vehicle.Mass, fuel_mass_simulated = false,
            rendered_captures = _captures,
            runtime_resource_inventory = _runtimeResourceInventories,
            contact_shading = new
            {
                enabled_by_setup = _vehicle.RigSetup.ContactShadingEnabled,
                supported_renderer = _vehicle.ContactShading?.SupportedRenderer ?? false,
                render_samples = _contactRenderSamples, visible_wheel_samples = _contactVisibleWheelSamples,
                airborne_wheel_samples = _contactAirborneWheelSamples,
                maximum_alignment_error_m = _contactMaximumAlignmentError,
                maximum_plane_error_m = _contactMaximumPlaneError,
                final_component = _vehicle.ContactShading?.CaptureMetrics(),
                scope = "Actual per-render contact/alignment readback across instance epochs; no performance or human visual approval.",
            },
            reconstruction_camera = new
            {
                process_frames = _reconstructionProcessFrames, render_frames = _reconstructionRenderFrames,
                observations = _reconstructionCameraObservations, captures = _reconstructionCaptures,
                native_display = _nativeDisplay,
                scope = "First three consecutive renders after actual save reconstruction on the unobstructed road fixture; native spring-arm collision remains authoritative.",
            },
            frames = new { path = framePath, sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(framePath))).ToLowerInvariant() },
            limitations = new[] { "InputMap action fixture is not a physical keyboard/controller usability session", "Functional JSONL capture is not a performance measurement", "Human visual/handling/usability/rights approval remains open" },
        }, JsonOptions));
        Complete = true;
        GD.Print($"CANNONBALL_ENDURANCE_SEDAN_OK vehicle={_selectedVehicle} stages={_results.Count} unfrozen_driving=true natural_rebase=true forced_rebase=true save_resume=true");
    }

    private bool RebaseFramesReady(bool rendered) => _rebaseObservations.TryGetValue(CurrentStage, out var observation) &&
        (rendered ? observation.RenderedFrames.Count : observation.ProcessFrames.Count) >= 3;

    private void ObserveReconstructedCamera(bool rendered)
    {
        if (!_resumeComplete || CurrentStage != "save-resume") return;
        var frames = rendered ? _reconstructionRenderFrames : _reconstructionProcessFrames;
        var frame = Engine.GetProcessFrames();
        if (frames.Count == 3 || frames.Count != 0 && frames[^1] == frame) return;
        frames.Add(frame);
        if (!rendered && _nativeDisplay) return;
        var camera = _vehicle.ChaseCameraRig.Camera;
        var arm = _vehicle.ChaseCameraRig.Arm;
        var hitLength = arm.GetHitLength();
        var localError = camera.Position.DistanceTo(Vector3.Back * hitLength);
        var valid = _parent.GetViewport().GetCamera3D()?.GetInstanceId() == camera.GetInstanceId() &&
            hitLength >= arm.SpringLength - 0.01f && localError <= 0.001f;
        var observation = new
        {
            render_frame = frame, physics_frame = Engine.GetPhysicsFrames(), vehicle_epoch = _vehicleEpoch,
            observation_boundary = rendered ? "native-before-draw" : "headless-process-no-image",
            camera_position = Vector(camera.GlobalPosition), camera_local_position = Vector(camera.Position),
            displayed_body_position = Vector(_vehicle.GetGlobalTransformInterpolated().Origin),
            displayed_distance_m = camera.GlobalPosition.DistanceTo(_vehicle.GetGlobalTransformInterpolated().Origin),
            spring_length_m = arm.SpringLength, hit_length_m = hitLength,
            native_arm_child_error_m = localError, valid,
        };
        _reconstructionCameraObservations.Add(observation);
        if (!valid)
            _renderFailure = "First reconstructed chase-camera draw preceded native spring-arm collision/placement.";
        if (_captureEnabled)
            _reconstructionCaptureTasks.Add(CaptureReconstructedCameraFrameAsync(frames.Count, observation));
    }

    private async Task CaptureReconstructedCameraFrameAsync(int index, object observation)
    {
        await _parent.ToSignal(RenderingServer.Singleton, RenderingServer.SignalName.FramePostDraw);
        using var texture = _parent.GetViewport().GetTexture();
        using var image = texture.GetImage();
        if (image is null || image.IsEmpty()) throw new InvalidOperationException("Missing first reconstructed camera image.");
        var path = Path.Combine(_evidenceDirectory, $"resume-frame-{index:00}.png");
        if (image.SavePng(path) != Error.Ok) throw new IOException("Could not retain first reconstructed camera image.");
        _reconstructionCaptures.Add(new
        {
            index, render_frame = Engine.GetProcessFrames(), before_draw = observation, path,
            size = new[] { image.GetWidth(), image.GetHeight() },
            sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant(),
        });
    }

    private void ObserveRebaseFrame(bool rendered)
    {
        if (_disposed || Complete || !_begun || CurrentStage is not ("natural-rebase" or "forced-rebase") ||
            _streamer.RebaseCount <= _initialRebases) return;
        if (!_rebaseObservations.TryGetValue(CurrentStage, out var observation))
        {
            observation = new RebaseObservation(_initialRebases, _streamer.RebaseCount, _physicsFrames);
            _rebaseObservations.Add(CurrentStage, observation);
        }
        Require(observation.RebaseCount == _streamer.RebaseCount, "multiple rebases happened before an event was separately observed");
        var frames = rendered ? observation.RenderedFrames : observation.ProcessFrames;
        var frame = Engine.GetProcessFrames();
        if (frames.Count == 0 || frames[^1] != frame) frames.Add(frame);
    }

    private sealed class RebaseObservation(int baseline, int count, long firstPhysicsFrame)
    {
        public int RebaseCount { get; } = count;
        public List<ulong> ProcessFrames { get; } = [];
        public List<ulong> RenderedFrames { get; } = [];
        public ulong? CapturedRenderFrame { get; set; }
        public int? CapturedRebaseCount { get; set; }
        public object Snapshot() => new { baseline_rebase_count = baseline, rebase_count = RebaseCount,
            first_observed_physics_frame = firstPhysicsFrame, process_frames = ProcessFrames.ToArray(),
            rendered_frames = RenderedFrames.ToArray(), captured_render_frame = CapturedRenderFrame,
            captured_rebase_count = CapturedRebaseCount, native_display = DisplayServer.GetName() != "headless" };
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        RenderingServer.FramePreDraw -= ObserveBeforeDraw;
        ReleaseActions();
        if (GodotObject.IsInstanceValid(_vehicle))
        {
            _vehicle.BodyEntered -= ObserveCollision;
            if (_savedCameraStabilization is { } stabilization)
                _vehicle.CockpitCameraRig.MaximumStabilizationDegrees = stabilization;
        }
        _frames.Dispose();
    }
}
