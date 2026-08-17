using System.Diagnostics;
using System.Text.Json;
using Cannonball.Game.Vehicle;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game.Automation;

/// <summary>
/// Windowed, rendered reference-performance capture for the ADR-0023 layered budgets.
/// Unlike the headless long-route profile this scenario measures presented-frame time on
/// the native renderer at a fixed resolution, discards warm-up, and separates CPU from GPU
/// frame cost so Q-022 can compare a real capture against the ratified provisional gate.
/// </summary>
public sealed class ReferencePerformanceScenario
{
#if DEBUG
    private const string BuildConfiguration = "Debug";
#else
    private const string BuildConfiguration = "Release";
#endif
    /// <summary>
    /// Frame time above which a frame is recorded as a stall with its work record.
    /// </summary>
    /// <remarks>
    /// ADR-0023 sets the acceptance threshold at 50 ms. That is the pass/fail line,
    /// but it is the wrong line for *diagnosis*: on 2026-08-16 the owner marked 53
    /// visible hitches in 90 seconds and every one landed between 20 and 46 ms, so
    /// the gate reported zero stalls for a run that was visibly stuttering roughly
    /// every 1.7 seconds. Against a 1.05 ms median frame, a 30 ms frame is a 30x
    /// spike and plainly perceptible.
    ///
    /// CANNONBALL_STALL_THRESHOLD_MS lowers the recording threshold so those frames
    /// carry their work record. It does not change acceptance, which is still
    /// judged at 50 ms.
    /// </remarks>
    public static readonly double StallThresholdMilliseconds =
        double.TryParse(
            System.Environment.GetEnvironmentVariable("CANNONBALL_STALL_THRESHOLD_MS"),
            System.Globalization.CultureInfo.InvariantCulture,
            out var configuredThreshold) && configuredThreshold > 0
            ? configuredThreshold
            : StallAcceptanceThresholdMilliseconds;

    /// <summary>Frame time above which a steady-driving frame fails acceptance.</summary>
    /// <remarks>
    /// Lowered from 50 ms to 20 ms by the owner on 2026-08-16. The 50 ms line was
    /// set before anything measured what a player notices. When the owner marked
    /// visible hitches, all 53 in 90 seconds fell between 8 and 46 ms, so the gate
    /// reported zero stalls for a run that was visibly stuttering about twice a
    /// second. Against a median frame near 1 ms, a 20 ms frame is a twentyfold
    /// spike.
    /// </remarks>
    public const double StallAcceptanceThresholdMilliseconds = 20;
    private const int MaximumRecordedStalls = 20_000;
    private const int MaximumFramesPerAggregateRow = 65_536;
    private const double MemorySampleIntervalSeconds = 0.5;
    private const double AggregateRowIntervalSeconds = 1;
    private const double LoopWrapAttributionSeconds = 0.75;
    private const double MinimumMovingSpeedMetersPerSecond = 1;
    private const double MinimumWarmupDistanceMeters = 60;

    private readonly CannonballVehicle _vehicle;
    private readonly WorldStreamer _streamer;
    private readonly DirectionalLight3D _light;
    private readonly Godot.Environment _environment;
    private readonly ReferencePerformanceOptions _options;
    private readonly Process _process = Process.GetCurrentProcess();

    // Sampling must not allocate per frame. An earlier revision accumulated one
    // List<double> entry per frame per series; over a 30-minute run that reached ~1.7M
    // entries per list, repeatedly reallocated multi-megabyte arrays onto the Large Object
    // Heap, and made the harness itself responsible for most of the working-set growth and
    // GC pauses it was supposed to be measuring. Histograms and pre-sized buffers keep the
    // steady-state sampling cost at zero allocations.
    private readonly LatencyHistogram _frameMilliseconds = new();
    private readonly LatencyHistogram _engineDeltaMilliseconds = new();
    private readonly LatencyHistogram _cpuMilliseconds = new();
    private readonly LatencyHistogram _gpuMilliseconds = new();
    private readonly List<StallEvent> _stalls = new(MaximumRecordedStalls);
    private readonly List<MemorySample> _memorySamples = new(4_096);
    private readonly List<double> _loopWrapSeconds = new(64);
    private readonly List<AggregateRow> _aggregateRows = new(4_096);
    private readonly double[] _pendingWindow = new double[MaximumFramesPerAggregateRow];
    private int _pendingWindowCount;
    private long _pendingWindowMaxDrawCalls;
    private long _pendingWindowMaxPrimitives;
    private int _droppedStallCount;

    private Rid _viewport;
    private Viewport? _viewportNode;
    private Vector2 _contentScaleSize;
    private bool _configured;
    private bool _warmupComplete;
    private double _warmupSeconds;
    private double _measuredSeconds;
    private ulong _measureStartTicksUsec;
    private ulong _lastFrameTicksUsec;
    private double _memorySampleAccumulator;
    private double _aggregateAccumulator;
    private double _lastMemorySampleSeconds = -1;
    private int _lastObservedLoopCount;

    private long _peakWorkingSetBytes;
    private long _startingWorkingSetBytes;
    private double _peakVideoMemoryBytes;
    private double _peakTextureMemoryBytes;
    private double _peakBufferMemoryBytes;
    private long _gpuBoundFrames;
    private long _harnessAllocatedBytes;
    private int _startingGen0Collections;
    private int _startingGen1Collections;
    private int _startingGen2Collections;
    private long _startingAllocatedBytes;
    private WorkCounters _previousCounters;
    // Road-holding, because a capture that reports "steady driving" while the car
    // leaves the carriageway and is teleported back is not measuring steady
    // driving. Nothing recorded this until the owner reported watching it happen.
    // Ride height per physics frame, for the speed sweep that separates suspension
    // resonance from road geometry. Peak-to-peak is the quantity the bounce is
    // felt as; std is reported because a single outlier moves p2p and not std.
    private double _rideHeightMinimum = double.MaxValue;
    private double _rideHeightMaximum = double.MinValue;
    private double _rideHeightSum;
    private double _rideHeightSumSquares;
    private int _rideHeightSamples;
    // Operator marks. A person notices a hitch and presses a key roughly a quarter
    // of a second later, so marking the current frame would record the recovery and
    // miss the event. Every measured frame goes into a ring buffer and a mark dumps
    // the window that preceded it.
    private const double MarkLookbackSeconds = 1.5;
    private const int MarkRingCapacity = 8192;
    private readonly FrameTrace[] _markRing = new FrameTrace[MarkRingCapacity];
    private int _markRingCount;
    private int _markRingNext;
    private bool _markKeyWasDown;
    private readonly List<object> _operatorMarks = [];

    private double _maximumAbsoluteLateralOffsetMeters;
    private double _lateralOffsetSum;
    private int _lateralOffsetSamples;
    private int _startingResetCount = -1;
    private SubsystemMilliseconds _subsystemSum;
    private SubsystemMilliseconds _subsystemPeak;
    private int _subsystemSampleCount;
    private bool _countersPrimed;
    private int _stallsWithNoAttributableWork;
    private int _stallsWithCollection;
    private int _stallsWithStreamingWork;
    private long _peakDrawCalls;
    private long _peakPrimitives;
    private long _peakRenderObjects;
    private double _drawCallSum;
    private double _primitiveSum;
    private int _contentSampleCount;

    private int _startingRebaseCount;
    private double _startingRouteDistanceMeters;
    private int _startingLoopCount;
    private RoadVisualSnapshot? _roadSnapshot;
    private EnvironmentStreamSnapshot? _environmentSnapshot;
    private VehicleVisualSnapshot? _vehicleSnapshot;

    public ReferencePerformanceScenario(
        CannonballVehicle vehicle,
        WorldStreamer streamer,
        DirectionalLight3D light,
        WorldEnvironment environment,
        ReferencePerformanceOptions options)
    {
        ArgumentNullException.ThrowIfNull(environment);
        _vehicle = vehicle ?? throw new ArgumentNullException(nameof(vehicle));
        _streamer = streamer ?? throw new ArgumentNullException(nameof(streamer));
        _light = light ?? throw new ArgumentNullException(nameof(light));
        _environment = environment.Environment ??
            throw new InvalidOperationException(
                "Reference performance capture requires a world environment.");
        _options = options ?? throw new ArgumentNullException(nameof(options));
    }

    public bool Complete { get; private set; }
    public bool Measuring => _warmupComplete && !Complete;

    /// <summary>
    /// Applies the measurement configuration that must be in force before the first sample:
    /// window size, presentation mode, frame-rate ceiling, and scenario lighting.
    /// </summary>
    public void Configure(Viewport viewport)
    {
        ArgumentNullException.ThrowIfNull(viewport);
        _viewport = viewport.GetViewportRid();
        RenderingServer.ViewportSetMeasureRenderTime(_viewport, true);

        if (!_options.Headless)
        {
            DisplayServer.WindowSetSize(
                new Vector2I(_options.WidthPixels, _options.HeightPixels));
            DisplayServer.WindowSetVsyncMode(
                _options.VsyncEnabled
                    ? DisplayServer.VSyncMode.Enabled
                    : DisplayServer.VSyncMode.Disabled);
        }

        // V-Sync disabled alone does not remove a frame ceiling; Engine.MaxFps must also be
        // unbounded or presented-frame time cannot exceed the refresh interval and headroom
        // stays invisible.
        Engine.MaxFps = _options.MaxFps;
        // Per-subsystem attribution costs a timestamp pair per instrumented
        // region, so it stays off outside a reference capture.
        Cannonball.Core.Performance.SubsystemProfiler.Enabled = true;
        _viewportNode = viewport;
        ApplyLighting(_options.Lighting);
        _vehicle.SetCameraMode(cockpit: _options.Camera == CameraView.Cockpit);
        _vehicle.AutopilotEnabled = true;
        _vehicle.AutopilotSpeedLimitMetersPerSecond = (float)_options.TargetSpeedMetersPerSecond;
        _streamer.ShortCorridorLoopEnabled = _options.LoopCorridor;
        _configured = true;
    }

    public void Advance(double delta)
    {
        if (Complete || !_configured)
        {
            return;
        }

        if (!_warmupComplete)
        {
            AdvanceWarmup(delta);
            return;
        }

        // Presented-frame time is taken from the microsecond monotonic clock, never from the
        // engine `delta`. Godot smooths the reported process delta against the physics step
        // (physics_jitter_fix), which quantises it to exact 120 Hz subdivisions and would turn
        // the percentile distribution into an artefact of the smoother.
        var now = Time.GetTicksUsec();
        var frameMilliseconds = (now - _lastFrameTicksUsec) / 1_000d;
        _lastFrameTicksUsec = now;
        _measuredSeconds = (now - _measureStartTicksUsec) / 1_000_000d;

        RecordLoopWrap();
        RecordFrame(frameMilliseconds, delta);
        if (_measuredSeconds >= _options.MeasureSeconds)
        {
            Complete = true;
        }
    }

    /// <summary>
    /// Warm-up is discarded per ADR-0023. It ends only once the vehicle is actually driving
    /// on settled streaming, so shader/pipeline compilation and the first chunk builds never
    /// enter the steady-state distribution.
    /// </summary>
    private void AdvanceWarmup(double delta)
    {
        var driving = _streamer.RouteDistanceMeters >= MinimumWarmupDistanceMeters &&
            _vehicle.SpeedMetersPerSecond >= MinimumMovingSpeedMetersPerSecond &&
            _streamer.IsStreamingSettled &&
            _streamer.IsEnvironmentStreamingSettled;
        if (!driving)
        {
            return;
        }

        _warmupSeconds += delta;
        if (_warmupSeconds < _options.WarmupSeconds)
        {
            return;
        }

        _warmupComplete = true;

        // Sampled here rather than in Configure(): the window resize issued at configure time
        // has not been applied within that same frame. This is the 2D content-scale
        // reference (canvas_items stretch), NOT the 3D render size — 3D renders at the window
        // resolution, which scripts/capture-reference-performance.sh sets and
        // actual_window_size records.
        if (_viewportNode is not null)
        {
            _contentScaleSize = _viewportNode.GetVisibleRect().Size;
        }
        _process.Refresh();
        _startingWorkingSetBytes = _process.WorkingSet64;
        _peakWorkingSetBytes = _startingWorkingSetBytes;
        _startingGen0Collections = GC.CollectionCount(0);
        _startingGen1Collections = GC.CollectionCount(1);
        _startingGen2Collections = GC.CollectionCount(2);
        _startingAllocatedBytes = GC.GetTotalAllocatedBytes(precise: false);
        _startingRebaseCount = _streamer.RebaseCount;
        _startingRouteDistanceMeters = _streamer.RouteDistanceMeters;
        _startingLoopCount = _streamer.CompletedShortCorridorLoops;
        _lastObservedLoopCount = _streamer.CompletedShortCorridorLoops;
        CaptureContentSnapshots();
        GD.Print(
            "CANNONBALL_REFERENCE_PERFORMANCE_WARMUP_DONE " +
            $"scenario={_options.ScenarioId} warmup_s={_warmupSeconds:0.000} " +
            $"route_distance_m={_streamer.RouteDistanceMeters:0.000}");

        // Start the measurement clock last. Snapshot capture and the marker print above cost
        // tens of milliseconds, and starting the clock before them would charge that setup
        // to the first measured frame and report it as a steady-driving stall.
        _measureStartTicksUsec = Time.GetTicksUsec();
        _lastFrameTicksUsec = _measureStartTicksUsec;
    }

    private void RecordLoopWrap()
    {
        if (_streamer.CompletedShortCorridorLoops == _lastObservedLoopCount)
        {
            return;
        }

        _lastObservedLoopCount = _streamer.CompletedShortCorridorLoops;
        _loopWrapSeconds.Add(_measuredSeconds);
    }

    private void RecordFrame(double frameMilliseconds, double engineDelta)
    {
        // Self-accounting: everything in this method is measurement, not game work. Tracking
        // what the harness allocates lets the audit state how much of the process-wide
        // allocation rate — and therefore the GC pause rate — belongs to the game itself.
        var allocatedBefore = GC.GetTotalAllocatedBytes(precise: false);
        var cpuMilliseconds = RenderingServer.ViewportGetMeasuredRenderTimeCpu(_viewport);
        var gpuMilliseconds = RenderingServer.ViewportGetMeasuredRenderTimeGpu(_viewport);
        _frameMilliseconds.Add(frameMilliseconds);
        _engineDeltaMilliseconds.Add(engineDelta * 1_000);
        _cpuMilliseconds.Add(cpuMilliseconds);
        _gpuMilliseconds.Add(gpuMilliseconds);
        if (gpuMilliseconds > cpuMilliseconds)
        {
            _gpuBoundFrames++;
        }
        if (_pendingWindowCount < _pendingWindow.Length)
        {
            _pendingWindow[_pendingWindowCount++] = frameMilliseconds;
        }

        var drawCalls = (long)Performance.GetMonitor(
            Performance.Monitor.RenderTotalDrawCallsInFrame);
        var primitives = (long)Performance.GetMonitor(
            Performance.Monitor.RenderTotalPrimitivesInFrame);
        var renderObjects = (long)Performance.GetMonitor(
            Performance.Monitor.RenderTotalObjectsInFrame);
        _peakDrawCalls = Math.Max(_peakDrawCalls, drawCalls);
        _peakPrimitives = Math.Max(_peakPrimitives, primitives);
        _peakRenderObjects = Math.Max(_peakRenderObjects, renderObjects);
        _drawCallSum += drawCalls;
        _primitiveSum += primitives;
        _contentSampleCount++;

        var work = SampleWork();
        AccumulateSubsystems(work.Subsystems);
        SampleRoadHolding();
        RecordFrameTrace(frameMilliseconds);
        PollOperatorMark();

        if (frameMilliseconds > StallThresholdMilliseconds)
        {
            if (work.Gen0Collections > 0 || work.Gen1Collections > 0 || work.Gen2Collections > 0)
            {
                _stallsWithCollection++;
            }
            if (work.CollisionBuilds > 0 || work.CollisionRemovals > 0 || work.Rebases > 0 ||
                work.ChunkBuildPeakAdvanced || work.CollisionBuildPeakAdvanced ||
                work.EnvironmentBuildPeakAdvanced)
            {
                _stallsWithStreamingWork++;
            }
            if (!work.HasAttributableWork)
            {
                _stallsWithNoAttributableWork++;
            }

            if (_stalls.Count >= MaximumRecordedStalls)
            {
                _droppedStallCount++;
            }
            else
            {
                _stalls.Add(new StallEvent(
                    _measuredSeconds,
                    frameMilliseconds,
                    cpuMilliseconds,
                    gpuMilliseconds,
                    _streamer.RouteDistanceMeters,
                    _vehicle.SpeedMetersPerSecond,
                    false,
                    work));
            }
        }

        _pendingWindowMaxDrawCalls = Math.Max(_pendingWindowMaxDrawCalls, drawCalls);
        _pendingWindowMaxPrimitives = Math.Max(_pendingWindowMaxPrimitives, primitives);
        var frameSeconds = frameMilliseconds / 1_000d;
        SampleMemory(frameSeconds);
        SampleAggregate(frameSeconds);
        _harnessAllocatedBytes += GC.GetTotalAllocatedBytes(precise: false) - allocatedBefore;
    }

    private static object WorkRecord(FrameWork work) => new
    {
        gen0_collections = work.Gen0Collections,
        gen1_collections = work.Gen1Collections,
        gen2_collections = work.Gen2Collections,
        collision_builds = work.CollisionBuilds,
        collision_removals = work.CollisionRemovals,
        rebases = work.Rebases,
        chunk_failures = work.ChunkFailures,
        loaded_chunk_delta = work.LoadedChunks,
        loaded_environment_chunk_delta = work.LoadedEnvironmentChunks,
        chunk_build_peak_advanced = work.ChunkBuildPeakAdvanced,
        collision_build_peak_advanced = work.CollisionBuildPeakAdvanced,
        environment_build_peak_advanced = work.EnvironmentBuildPeakAdvanced,
        physics_process_ms = work.PhysicsProcessMilliseconds,
        process_ms = work.ProcessMilliseconds,
        has_attributable_work = work.HasAttributableWork,
        subsystem_ms = new
        {
            road = work.Subsystems.Road,
            route_context = work.Subsystems.RouteContext,
            environment = work.Subsystems.Environment,
            vehicle = work.Subsystems.Vehicle,
            ui = work.Subsystems.Ui,
            total = work.Subsystems.Total,
            basis = "exclusive CPU time; nested regions suspend their parent",
            status = "measurement only; ADR-0023 layer 2 remains unratified reserves",
        },
    };

    /// <summary>
    /// Reads the cumulative work counters and returns their change since the previous
    /// frame. The first measured frame primes the baseline and reports no work, because
    /// a delta against zero would charge the whole warm-up to it.
    /// </summary>
    private FrameWork SampleWork()
    {
        var current = new WorkCounters(
            GC.CollectionCount(0),
            GC.CollectionCount(1),
            GC.CollectionCount(2),
            _streamer.CollisionBuildCount,
            _streamer.CollisionRemovalCount,
            _streamer.RebaseCount,
            _streamer.ChunkFailureCount,
            _streamer.LoadedChunkCount,
            _streamer.LoadedEnvironmentChunkCount,
            _streamer.MaximumBuildMilliseconds,
            _streamer.MaximumCollisionBuildMilliseconds,
            _streamer.MaximumEnvironmentBuildMilliseconds);

        if (!_countersPrimed)
        {
            _previousCounters = current;
            _countersPrimed = true;
            // Discard what accumulated before measurement began, so the first
            // measured frame is not charged the whole warm-up.
            Cannonball.Core.Performance.SubsystemProfiler.Drain();
            return default;
        }

        var previous = _previousCounters;
        _previousCounters = current;
        var drained = Cannonball.Core.Performance.SubsystemProfiler.Drain();
        _roadBytes += drained.RoadBytes;
        _routeContextBytes += drained.RouteContextBytes;
        _environmentBytes += drained.EnvironmentBytes;
        _vehicleBytes += drained.VehicleBytes;
        _uiBytes += drained.UiBytes;
        _cameraBytes += drained.CameraBytes;
        _orchestrationBytes += drained.OrchestrationBytes;
        _inputBytes += drained.InputBytes;
        var subsystems = new SubsystemMilliseconds(
            drained.Road,
            drained.RouteContext,
            drained.Environment,
            drained.Vehicle,
            drained.Ui,
            drained.Total);

        // A rising maximum means this frame produced the most expensive build seen so
        // far. It cannot show that a build merely occurred, only that a new worst case
        // landed here, which is the case a stall investigation cares about.
        return new FrameWork(
            current.Gen0Collections - previous.Gen0Collections,
            current.Gen1Collections - previous.Gen1Collections,
            current.Gen2Collections - previous.Gen2Collections,
            current.CollisionBuilds - previous.CollisionBuilds,
            current.CollisionRemovals - previous.CollisionRemovals,
            current.Rebases - previous.Rebases,
            current.ChunkFailures - previous.ChunkFailures,
            current.LoadedChunks - previous.LoadedChunks,
            current.LoadedEnvironmentChunks - previous.LoadedEnvironmentChunks,
            current.MaximumChunkBuildMilliseconds > previous.MaximumChunkBuildMilliseconds,
            current.MaximumCollisionBuildMilliseconds >
                previous.MaximumCollisionBuildMilliseconds,
            current.MaximumEnvironmentBuildMilliseconds >
                previous.MaximumEnvironmentBuildMilliseconds,
            Performance.GetMonitor(Performance.Monitor.TimePhysicsProcess) * 1_000,
            Performance.GetMonitor(Performance.Monitor.TimeProcess) * 1_000,
            subsystems);
    }

    /// <summary>
    /// Memory is sampled on an interval rather than per frame: <see cref="Process.Refresh"/>
    /// is a syscall, and paying it every frame would inflate the very frame times being measured.
    /// </summary>
    private void SampleMemory(double delta)
    {
        _memorySampleAccumulator += delta;
        if (_memorySampleAccumulator < MemorySampleIntervalSeconds &&
            _lastMemorySampleSeconds >= 0)
        {
            return;
        }

        _memorySampleAccumulator = 0;
        _lastMemorySampleSeconds = _measuredSeconds;
        _process.Refresh();
        var workingSet = _process.WorkingSet64;
        var videoMemory = Performance.GetMonitor(Performance.Monitor.RenderVideoMemUsed);
        var textureMemory = Performance.GetMonitor(Performance.Monitor.RenderTextureMemUsed);
        var bufferMemory = Performance.GetMonitor(Performance.Monitor.RenderBufferMemUsed);
        _peakWorkingSetBytes = Math.Max(_peakWorkingSetBytes, workingSet);
        _peakVideoMemoryBytes = Math.Max(_peakVideoMemoryBytes, videoMemory);
        _peakTextureMemoryBytes = Math.Max(_peakTextureMemoryBytes, textureMemory);
        _peakBufferMemoryBytes = Math.Max(_peakBufferMemoryBytes, bufferMemory);
        _memorySamples.Add(new MemorySample(
            _measuredSeconds,
            workingSet,
            videoMemory,
            textureMemory,
            bufferMemory,
            GC.GetTotalMemory(forceFullCollection: false),
            GC.CollectionCount(0) - _startingGen0Collections,
            GC.CollectionCount(1) - _startingGen1Collections,
            GC.CollectionCount(2) - _startingGen2Collections));
    }

    private void SampleAggregate(double delta)
    {
        _aggregateAccumulator += delta;
        if (_aggregateAccumulator < AggregateRowIntervalSeconds || _pendingWindowCount == 0)
        {
            return;
        }

        _aggregateAccumulator = 0;
        var window = _pendingWindow.AsSpan(0, _pendingWindowCount);
        window.Sort();
        _aggregateRows.Add(new AggregateRow(
            _measuredSeconds,
            _pendingWindowCount,
            window[_pendingWindowCount / 2],
            window[^1],
            _pendingWindowMaxDrawCalls,
            _pendingWindowMaxPrimitives,
            _streamer.RouteDistanceMeters,
            _vehicle.SpeedMetersPerSecond,
            _streamer.LoadedChunkCount,
            _streamer.RebaseCount));
        _pendingWindowCount = 0;
        _pendingWindowMaxDrawCalls = 0;
        _pendingWindowMaxPrimitives = 0;
    }

    private void CaptureContentSnapshots()
    {
        _roadSnapshot = _streamer.CaptureRoadVisualSnapshot();
        _environmentSnapshot = _streamer.CaptureEnvironmentSnapshot();
        _vehicleSnapshot = _vehicle.VisualRig?.CaptureSnapshot();
    }

    private bool NearLoopWrap(double seconds) =>
        _loopWrapSeconds.Exists(wrap => Math.Abs(seconds - wrap) <= LoopWrapAttributionSeconds);

    /// <summary>
    /// Mirrors the daylight and night values in <see cref="EnvironmentVisualScenario"/> so a
    /// performance capture and a visual review describe the same lighting states.
    /// </summary>
    private void ApplyLighting(LightingMode lighting)
    {
        var values = lighting switch
        {
            LightingMode.Daylight => new LightingState(
                new Color("fff2d6"), 1.8f, -48, new Color("78a7d8"), new Color("dbe8f6"), 0.8f),
            LightingMode.Night => new LightingState(
                new Color("a9c4ff"), 1.3f, -24, new Color("060912"), new Color("425072"), 0.45f),
            _ => throw new ArgumentOutOfRangeException(nameof(lighting)),
        };
        _light.LightColor = values.Light;
        _light.LightEnergy = values.Energy;
        _light.RotationDegrees = new Vector3(values.PitchDegrees, -28, 0);
        _environment.BackgroundColor = values.Background;
        _environment.AmbientLightColor = values.Ambient;
        _environment.AmbientLightEnergy = values.AmbientEnergy;
    }

    public void ValidateComplete()
    {
        if (!Complete)
        {
            throw new InvalidOperationException(
                $"Reference performance scenario '{_options.ScenarioId}' did not reach its " +
                $"measured duration (warmup_complete={_warmupComplete}, " +
                $"measured_s={_measuredSeconds:0.000} of {_options.MeasureSeconds:0.000}).");
        }
        if (_frameMilliseconds.Count == 0)
        {
            throw new InvalidOperationException(
                $"Reference performance scenario '{_options.ScenarioId}' recorded no frames.");
        }
    }

    public void WriteArtifacts()
    {
        ValidateComplete();
        for (var index = 0; index < _stalls.Count; index++)
        {
            var stall = _stalls[index];
            _stalls[index] = stall with { NearLoopWrap = NearLoopWrap(stall.Seconds) };
        }
        WriteSamples();
        WriteSummary();
    }

    private void WriteSamples()
    {
        EnsureDirectory(_options.SamplesPath);
        using var writer = new StreamWriter(_options.SamplesPath, append: false);
        var options = new JsonSerializerOptions { WriteIndented = false };
        writer.WriteLine(JsonSerializer.Serialize(new
        {
            row = "header",
            scenario = _options.ScenarioId,
            recorded_at_utc = DateTimeOffset.UtcNow,
            warmup_seconds = _warmupSeconds,
            measure_seconds_requested = _options.MeasureSeconds,
            configuration = Configuration(),
        }, options));
        foreach (var aggregate in _aggregateRows)
        {
            writer.WriteLine(JsonSerializer.Serialize(new
            {
                row = "second",
                t_s = aggregate.Seconds,
                frames = aggregate.FrameCount,
                median_frame_ms = aggregate.MedianMilliseconds,
                max_frame_ms = aggregate.MaximumMilliseconds,
                max_draw_calls = aggregate.MaxDrawCalls,
                max_primitives = aggregate.MaxPrimitives,
                route_distance_m = aggregate.RouteDistanceMeters,
                speed_mps = aggregate.SpeedMetersPerSecond,
                loaded_chunks = aggregate.LoadedChunkCount,
                rebases = aggregate.RebaseCount,
            }, options));
        }
        foreach (var sample in _memorySamples)
        {
            writer.WriteLine(JsonSerializer.Serialize(new
            {
                row = "memory",
                t_s = sample.Seconds,
                working_set_bytes = sample.WorkingSetBytes,
                video_memory_bytes = sample.VideoMemoryBytes,
                texture_memory_bytes = sample.TextureMemoryBytes,
                buffer_memory_bytes = sample.BufferMemoryBytes,
                managed_heap_bytes = sample.ManagedHeapBytes,
                gen0 = sample.Gen0Collections,
                gen1 = sample.Gen1Collections,
                gen2 = sample.Gen2Collections,
            }, options));
        }
        foreach (var stall in _stalls)
        {
            writer.WriteLine(JsonSerializer.Serialize(new
            {
                row = "stall",
                t_s = stall.Seconds,
                frame_ms = stall.FrameMilliseconds,
                render_cpu_ms = stall.CpuMilliseconds,
                render_gpu_ms = stall.GpuMilliseconds,
                route_distance_m = stall.RouteDistanceMeters,
                speed_mps = stall.SpeedMetersPerSecond,
                attributed_to_loop_wrap = stall.NearLoopWrap,
                work = WorkRecord(stall.Work),
            }, options));
        }
        foreach (var wrap in _loopWrapSeconds)
        {
            writer.WriteLine(JsonSerializer.Serialize(new
            {
                row = "loop_wrap",
                t_s = wrap,
            }, options));
        }
    }

    private void WriteSummary()
    {
        var steadyStalls = _stalls.FindAll(stall => !stall.NearLoopWrap);
        var workingSetGrowth = MemoryTrend(sample => sample.WorkingSetBytes);
        var videoMemoryGrowth = MemoryTrend(sample => sample.VideoMemoryBytes);
        var frame = _frameMilliseconds.Describe();
        var totalAllocatedBytes = TotalAllocatedBytes();
        var gameAllocatedBytes = Math.Max(0, totalAllocatedBytes - _harnessAllocatedBytes);
        var summary = new
        {
            schema_version = 1,
            scenario = _options.ScenarioId,
            recorded_at_utc = DateTimeOffset.UtcNow,
            configuration = Configuration(),
            warmup = new
            {
                requested_seconds = _options.WarmupSeconds,
                observed_seconds = _warmupSeconds,
                discarded = true,
            },
            measurement = new
            {
                measured_seconds = _measuredSeconds,
                frames = _frameMilliseconds.Count,
                mean_fps = _measuredSeconds > 0
                    ? _frameMilliseconds.Count / _measuredSeconds
                    : 0,
            },
            frame_time_ms = frame,
            // Reported for transparency only. The engine delta is smoothed against the
            // physics step and must not be used for the acceptance comparison.
            engine_reported_delta_ms = _engineDeltaMilliseconds.Describe(),
            render_cpu_ms = _cpuMilliseconds.Describe(),
            render_gpu_ms = _gpuMilliseconds.Describe(),
            attribution = Attribution(),
            stalls = new
            {
                threshold_ms = StallThresholdMilliseconds,
                total_count = _stalls.Count,
                steady_driving_count = steadyStalls.Count,
                loop_wrap_attributed_count = _stalls.Count - steadyStalls.Count,
                loop_wrap_count = _loopWrapSeconds.Count,
                dropped_beyond_record_cap = _droppedStallCount,
                events = _stalls.ConvertAll(stall => new
                {
                    t_s = stall.Seconds,
                    frame_ms = stall.FrameMilliseconds,
                    render_cpu_ms = stall.CpuMilliseconds,
                    render_gpu_ms = stall.GpuMilliseconds,
                    route_distance_m = stall.RouteDistanceMeters,
                    speed_mps = stall.SpeedMetersPerSecond,
                    attributed_to_loop_wrap = stall.NearLoopWrap,
                    work = WorkRecord(stall.Work),
                }),
                attribution = new
                {
                    with_a_garbage_collection = _stallsWithCollection,
                    with_streaming_work = _stallsWithStreamingWork,
                    with_no_attributable_work = _stallsWithNoAttributableWork,
                    counters = "GC generation counts and WorldStreamer cumulative counters, "
                        + "differenced frame to frame",
                    boundary = "These counters show what work coincided with a stall. They "
                        + "do not time that work, so a coincidence is not a cause.",
                },
            },
            memory = new
            {
                starting_working_set_bytes = _startingWorkingSetBytes,
                peak_working_set_bytes = _peakWorkingSetBytes,
                peak_video_memory_bytes = (long)_peakVideoMemoryBytes,
                peak_texture_memory_bytes = (long)_peakTextureMemoryBytes,
                peak_buffer_memory_bytes = (long)_peakBufferMemoryBytes,
                sample_count = _memorySamples.Count,
                working_set_trend = workingSetGrowth,
                video_memory_trend = videoMemoryGrowth,
                managed_heap_trend = MemoryTrend(sample => sample.ManagedHeapBytes),
            },
            // Managed-allocation accounting exists so a reader can tell whether a stall or a
            // working-set trend belongs to the game or to the measurement harness.
            garbage_collection = new
            {
                gen0_collections = _memorySamples.Count > 0
                    ? _memorySamples[^1].Gen0Collections : 0,
                gen1_collections = _memorySamples.Count > 0
                    ? _memorySamples[^1].Gen1Collections : 0,
                gen2_collections = _memorySamples.Count > 0
                    ? _memorySamples[^1].Gen2Collections : 0,
                allocated_bytes_during_measurement = totalAllocatedBytes,
                harness_allocated_bytes = _harnessAllocatedBytes,
                game_allocated_bytes = gameAllocatedBytes,
                harness_share_of_allocation = totalAllocatedBytes > 0
                    ? (double)_harnessAllocatedBytes / totalAllocatedBytes
                    : 0,
                game_allocated_bytes_per_frame = _frameMilliseconds.Count > 0
                    ? (double)gameAllocatedBytes / _frameMilliseconds.Count
                    : 0,
                gen0_collections_per_second = _measuredSeconds > 0 && _memorySamples.Count > 0
                    ? _memorySamples[^1].Gen0Collections / _measuredSeconds
                    : 0,
            },
            streaming = new
            {
                cumulative_route_distance_m = CumulativeRouteDistanceMeters(),
                final_route_position_m = _streamer.RouteDistanceMeters,
                starting_route_position_m = _startingRouteDistanceMeters,
                maximum_chunk_build_ms = _streamer.MaximumBuildMilliseconds,
                maximum_collision_build_ms = _streamer.MaximumCollisionBuildMilliseconds,
                maximum_environment_build_ms = _streamer.MaximumEnvironmentBuildMilliseconds,
                loaded_chunks = _streamer.LoadedChunkCount,
                maximum_visual_chunks = _streamer.MaximumVisualChunkCount,
                maximum_collision_chunks = _streamer.MaximumCollisionChunkCount,
                chunk_failures = _streamer.ChunkFailureCount,
                rebases = _streamer.RebaseCount - _startingRebaseCount,
                corridor_loops = _streamer.CompletedShortCorridorLoops,
                collision_builds = _streamer.CollisionBuildCount,
                collision_removals = _streamer.CollisionRemovalCount,
            },
            content_class = ContentClass(),
            acceptance = Acceptance(steadyStalls),
        };

        EnsureDirectory(_options.SummaryPath);
        File.WriteAllText(
            _options.SummaryPath,
            JsonSerializer.Serialize(summary, new JsonSerializerOptions
            {
                WriteIndented = true,
            }) + System.Environment.NewLine);
    }

    private object Configuration() => new
    {
        width_pixels = _options.WidthPixels,
        height_pixels = _options.HeightPixels,
        actual_window_size = _options.Headless
            ? "headless"
            : $"{DisplayServer.WindowGetSize().X}x{DisplayServer.WindowGetSize().Y}",
        content_scale_size_2d = $"{_contentScaleSize.X:0}x{_contentScaleSize.Y:0}",
        three_d_render_size = _options.Headless
            ? "headless"
            : $"{DisplayServer.WindowGetSize().X}x{DisplayServer.WindowGetSize().Y}",
        three_d_render_size_basis =
            "canvas_items stretch scales 2D only; 3D renders at window resolution.",
        rendering_method = _options.Headless
            ? "headless"
            : (string)ProjectSettings.GetSetting("rendering/renderer/rendering_method"),
        build_configuration = BuildConfiguration,
        headless = _options.Headless,
        vsync_enabled = _options.VsyncEnabled,
        engine_max_fps = Engine.MaxFps,
        frame_time_source = "Time.GetTicksUsec monotonic clock (not the smoothed engine delta)",
        physics_jitter_fix =
            ProjectSettings.GetSetting("physics/common/physics_jitter_fix").AsDouble(),
        physics_ticks_per_second = Engine.PhysicsTicksPerSecond,
        lighting = _options.Lighting.ToString().ToLowerInvariant(),
        camera = _options.Camera.ToString().ToLowerInvariant(),
        environment_quality = _environmentSnapshot?.ProfileId ?? "unmeasured",
        road_profile = _roadSnapshot?.ProfileId ?? "unmeasured",
        target_speed_mps = _options.TargetSpeedMetersPerSecond,
        corridor_loop_enabled = _options.LoopCorridor,
        video_adapter = _options.Headless ? "headless" : RenderingServer.GetVideoAdapterName(),
        video_adapter_api_version = _options.Headless
            ? "headless"
            : RenderingServer.GetVideoAdapterApiVersion(),
        screen_refresh_hz = _options.Headless ? -1 : DisplayServer.ScreenGetRefreshRate(),
    };

    private object Attribution()
    {
        // Godot reports render CPU and GPU time for the viewport. A frame whose GPU time
        // dominates is GPU bound; the remainder of the presented frame beyond both is
        // simulation, physics, scripting, garbage collection, and present overhead.
        var gpuMean = _gpuMilliseconds.Mean;
        var cpuMean = _cpuMilliseconds.Mean;
        var frameMean = _frameMilliseconds.Mean;
        return new
        {
            mean_frame_ms = frameMean,
            mean_render_cpu_ms = cpuMean,
            mean_render_gpu_ms = gpuMean,
            mean_non_render_ms = Math.Max(0, frameMean - Math.Max(cpuMean, gpuMean)),
            gpu_bound_frame_ratio = _frameMilliseconds.Count > 0
                ? (double)_gpuBoundFrames / _frameMilliseconds.Count
                : 0,
            bound_by = gpuMean > cpuMean ? "gpu" : "cpu",
            subsystem_cpu_ms = SubsystemAttribution(),
            subsystem_allocation = SubsystemAllocation(),
            road_holding = RoadHolding(),
            ride_height = RideHeight(),
            operator_marks = _operatorMarks,
        };
    }

    private void RecordFrameTrace(double frameMilliseconds)
    {
        _markRing[_markRingNext] = new FrameTrace(
            _measuredSeconds,
            frameMilliseconds,
            _vehicle.RideHeightMeters,
            _streamer.RouteDistanceMeters,
            _vehicle.SpeedMetersPerSecond,
            _streamer.RebaseCount,
            _vehicle.ResetToRoadCount);
        _markRingNext = (_markRingNext + 1) % MarkRingCapacity;
        _markRingCount = Math.Min(_markRingCount + 1, MarkRingCapacity);
    }

    /// <summary>
    /// Records the window before an operator keypress, so a felt hitch can be
    /// correlated against what the run was doing when it happened.
    /// </summary>
    /// <remarks>
    /// Polled rather than driven by an input action, because the capture registers
    /// no action for it and adding one would change the input map the driving tests
    /// assert against. F8 is used because every letter key near the driving controls
    /// is taken - M, the obvious choice, toggles the trip map.
    /// </remarks>
    private void PollOperatorMark()
    {
        var down = Godot.Input.IsPhysicalKeyPressed(Key.F8);
        if (!down || _markKeyWasDown)
        {
            _markKeyWasDown = down;
            return;
        }
        _markKeyWasDown = true;

        var window = new List<object>();
        var worstFrame = 0.0;
        var rebasesInWindow = 0;
        var firstRebase = -1;
        for (var offset = 0; offset < _markRingCount; offset++)
        {
            var index = (_markRingNext - _markRingCount + offset + MarkRingCapacity)
                % MarkRingCapacity;
            var trace = _markRing[index];
            if (_measuredSeconds - trace.Seconds > MarkLookbackSeconds)
            {
                continue;
            }
            if (firstRebase < 0)
            {
                firstRebase = trace.RebaseCount;
            }
            rebasesInWindow = trace.RebaseCount - firstRebase;
            worstFrame = Math.Max(worstFrame, trace.FrameMilliseconds);
            window.Add(new
            {
                t_s = trace.Seconds,
                frame_ms = trace.FrameMilliseconds,
                // Null rather than NaN: ride height is undefined on an airborne
                // frame, and System.Text.Json refuses non-finite numbers outright.
                ride_height_m = double.IsFinite(trace.RideHeightMeters)
                    ? trace.RideHeightMeters
                    : (double?)null,
                route_distance_m = trace.RouteDistanceMeters,
                speed_mps = trace.SpeedMetersPerSecond,
                rebases = trace.RebaseCount,
                resets = trace.ResetCount,
            });
        }

        _operatorMarks.Add(new
        {
            marked_at_s = _measuredSeconds,
            lookback_s = MarkLookbackSeconds,
            frames_in_window = window.Count,
            worst_frame_ms_in_window = worstFrame,
            rebases_in_window = rebasesInWindow,
            note =
                "the operator presses after noticing, so the cause is earlier in this " +
                "window than the mark time",
            window,
        });
        GD.Print(
            $"CANNONBALL_OPERATOR_MARK index={_operatorMarks.Count} t_s={_measuredSeconds:0.000} " +
            $"worst_frame_ms={worstFrame:0.000} rebases_in_window={rebasesInWindow} " +
            $"frames={window.Count}");
    }

    private void SampleRoadHolding()
    {
        if (_startingResetCount < 0)
        {
            _startingResetCount = _vehicle.ResetToRoadCount;
        }
        var rideHeight = _vehicle.RideHeightMeters;
        if (double.IsFinite(rideHeight))
        {
            _rideHeightMinimum = Math.Min(_rideHeightMinimum, rideHeight);
            _rideHeightMaximum = Math.Max(_rideHeightMaximum, rideHeight);
            _rideHeightSum += rideHeight;
            _rideHeightSumSquares += rideHeight * rideHeight;
            _rideHeightSamples++;
        }
        var lateral = Math.Abs(_vehicle.CrossTrackErrorMeters);
        _maximumAbsoluteLateralOffsetMeters = Math.Max(
            _maximumAbsoluteLateralOffsetMeters, lateral);
        _lateralOffsetSum += lateral;
        _lateralOffsetSamples++;
    }

    /// <summary>
    /// Whether the vehicle actually stayed on the route while being measured.
    /// </summary>
    /// <remarks>
    /// Reported, not gated. What counts as leaving the carriageway depends on the
    /// paved width at each station, which this does not read, so a threshold here
    /// would be invented. A reset count above zero is unambiguous, though: the car
    /// fell through the world and was teleported back, and the run is not a steady
    /// drive.
    /// </remarks>
    /// <summary>Ride-height oscillation over the measured window.</summary>
    /// <remarks>
    /// Airborne frames are excluded rather than counted as zero, because a wheel
    /// off the ground has no ride height and averaging one in would understate the
    /// oscillation that put it there.
    /// </remarks>
    private object RideHeight()
    {
        if (_rideHeightSamples == 0)
        {
            return new { sample_count = 0, note = "no grounded frame was measured" };
        }
        var mean = _rideHeightSum / _rideHeightSamples;
        var variance = Math.Max(0, _rideHeightSumSquares / _rideHeightSamples - mean * mean);
        return new
        {
            sample_count = _rideHeightSamples,
            mean_m = mean,
            minimum_m = double.IsFinite(_rideHeightMinimum) ? _rideHeightMinimum : (double?)null,
            maximum_m = double.IsFinite(_rideHeightMaximum) ? _rideHeightMaximum : (double?)null,
            peak_to_peak_m = double.IsFinite(_rideHeightMaximum - _rideHeightMinimum)
                ? _rideHeightMaximum - _rideHeightMinimum
                : (double?)null,
            standard_deviation_m = Math.Sqrt(variance),
            basis = "chassis height above the mean tyre contact point, per physics frame",
        };
    }

    private object RoadHolding() => new
    {
        reset_to_road_count = Math.Max(0, _vehicle.ResetToRoadCount - Math.Max(0, _startingResetCount)),
        maximum_absolute_lateral_offset_m = _maximumAbsoluteLateralOffsetMeters,
        mean_absolute_lateral_offset_m = _lateralOffsetSamples > 0
            ? _lateralOffsetSum / _lateralOffsetSamples
            : 0,
        sample_count = _lateralOffsetSamples,
        basis =
            "cross-track error, the distance from the vehicle to the route centreline " +
            "it is tracking, sampled per measured frame; a reset is a teleport back " +
            "onto the route after falling through the world",
        status =
            "reported, not gated; a run with a non-zero reset count is not the steady " +
            "drive its other metrics describe",
    };

    private long _roadBytes;
    private long _routeContextBytes;
    private long _environmentBytes;
    private long _vehicleBytes;
    private long _uiBytes;
    private long _cameraBytes;
    private long _orchestrationBytes;
    private long _inputBytes;

    /// <summary>Allocation attributed to each subsystem over the measured window.</summary>
    /// <remarks>
    /// A managed pause is caused by whoever produced the garbage, not by whoever was
    /// running when the collector fired, so allocation is attributed at the same
    /// region boundaries as time. Anything not covered by a region shows up as the
    /// gap between these totals and the run's own allocation counter.
    /// </remarks>
    private object SubsystemAllocation()
    {
        var frames = Math.Max(1, _subsystemSampleCount);
        var covered = _roadBytes + _routeContextBytes + _environmentBytes
            + _vehicleBytes + _uiBytes + _cameraBytes + _orchestrationBytes + _inputBytes;
        return new
        {
            road_bytes_per_frame = (double)_roadBytes / frames,
            route_context_bytes_per_frame = (double)_routeContextBytes / frames,
            environment_bytes_per_frame = (double)_environmentBytes / frames,
            vehicle_bytes_per_frame = (double)_vehicleBytes / frames,
            ui_bytes_per_frame = (double)_uiBytes / frames,
            camera_bytes_per_frame = (double)_cameraBytes / frames,
            orchestration_bytes_per_frame = (double)_orchestrationBytes / frames,
            input_bytes_per_frame = (double)_inputBytes / frames,
            attributed_bytes_per_frame = (double)covered / frames,
            note = "anything above this per frame is allocated outside an instrumented region",
        };
    }

    private void AccumulateSubsystems(SubsystemMilliseconds sample)
    {
        _subsystemSum = new SubsystemMilliseconds(
            _subsystemSum.Road + sample.Road,
            _subsystemSum.RouteContext + sample.RouteContext,
            _subsystemSum.Environment + sample.Environment,
            _subsystemSum.Vehicle + sample.Vehicle,
            _subsystemSum.Ui + sample.Ui,
            _subsystemSum.Total + sample.Total);
        _subsystemPeak = new SubsystemMilliseconds(
            Math.Max(_subsystemPeak.Road, sample.Road),
            Math.Max(_subsystemPeak.RouteContext, sample.RouteContext),
            Math.Max(_subsystemPeak.Environment, sample.Environment),
            Math.Max(_subsystemPeak.Vehicle, sample.Vehicle),
            Math.Max(_subsystemPeak.Ui, sample.Ui),
            Math.Max(_subsystemPeak.Total, sample.Total));
        _subsystemSampleCount++;
    }

    /// <summary>
    /// Mean and worst-frame exclusive CPU time per ADR-0023 layer-2 subsystem.
    /// </summary>
    /// <remarks>
    /// Reported as measurement, not as a budget verdict. Q-022b keeps layer 2 as
    /// unmeasured reserves, and nothing here ratifies them; that is a decision for
    /// the owner once enough of these captures exist to say what the split is.
    ///
    /// The subsystems named here are those that exist. Traffic, effects and
    /// lighting hold layer-2 reserves with no implementation behind them, so they
    /// are absent rather than reported as zero.
    /// </remarks>
    private object SubsystemAttribution()
    {
        var samples = Math.Max(1, _subsystemSampleCount);
        return new
        {
            sample_count = _subsystemSampleCount,
            basis = "exclusive CPU time; a nested region suspends its parent",
            status = "measurement only; ADR-0023 layer 2 remains unratified reserves",
            covers = "road, route context, environment, vehicle, UI",
            excludes = "GPU time, and any cost outside the process",
            mean = new
            {
                road = _subsystemSum.Road / samples,
                route_context = _subsystemSum.RouteContext / samples,
                environment = _subsystemSum.Environment / samples,
                vehicle = _subsystemSum.Vehicle / samples,
                ui = _subsystemSum.Ui / samples,
                total = _subsystemSum.Total / samples,
            },
            worst_frame = new
            {
                road = _subsystemPeak.Road,
                route_context = _subsystemPeak.RouteContext,
                environment = _subsystemPeak.Environment,
                vehicle = _subsystemPeak.Vehicle,
                ui = _subsystemPeak.Ui,
                total = _subsystemPeak.Total,
            },
        };
    }

    private long TotalAllocatedBytes() =>
        GC.GetTotalAllocatedBytes(precise: false) - _startingAllocatedBytes;

    private double CumulativeRouteDistanceMeters()
    {
        var completedLoops = _streamer.CompletedShortCorridorLoops - _startingLoopCount;
        var loopTraversalMeters = Math.Max(
            0,
            _streamer.TotalRouteLengthMeters - WorldStreamer.ShortCorridorLoopResetLeadMeters);
        return (completedLoops * loopTraversalMeters) +
            _streamer.RouteDistanceMeters - _startingRouteDistanceMeters;
    }

    private object ContentClass() => new
    {
        peak_draw_calls = _peakDrawCalls,
        mean_draw_calls = _contentSampleCount > 0 ? _drawCallSum / _contentSampleCount : 0,
        peak_primitives = _peakPrimitives,
        mean_primitives = _contentSampleCount > 0 ? _primitiveSum / _contentSampleCount : 0,
        peak_render_objects = _peakRenderObjects,
        road = _roadSnapshot is null ? null : new
        {
            profile = _roadSnapshot.ProfileId,
            chunks = _roadSnapshot.ChunkCount,
            shared_materials = _roadSnapshot.SharedMaterialCount,
            shared_meshes = _roadSnapshot.SharedMeshCount,
            retroreflective_materials = _roadSnapshot.RetroreflectiveMaterialCount,
            guide_signs = _roadSnapshot.GuideSignCount,
            route_shields = _roadSnapshot.RouteShieldCount,
            reflectors = _roadSnapshot.ReflectorCount,
            barrier_segments = _roadSnapshot.BarrierSegmentCount,
            guardrail_segments = _roadSnapshot.GuardrailSegmentCount,
            structures = _roadSnapshot.StructureCount,
        },
        environment = _environmentSnapshot is null ? null : new
        {
            profile = _environmentSnapshot.ProfileId,
            loaded_chunks = _environmentSnapshot.LoadedChunks.Count,
            near_instances = _environmentSnapshot.NearInstanceCount,
            mid_instances = _environmentSnapshot.MidInstanceCount,
            distant_instances = _environmentSnapshot.DistantInstanceCount,
            terrain_ribbons = _environmentSnapshot.TerrainRibbonCount,
            terrain_triangles = _environmentSnapshot.TerrainTriangleCount,
            shared_materials = _environmentSnapshot.SharedMaterialCount,
            shared_meshes = _environmentSnapshot.SharedMeshCount,
            near_visibility_m = _environmentSnapshot.NearVisibilityMeters,
            mid_visibility_m = _environmentSnapshot.MidVisibilityMeters,
            distant_visibility_m = _environmentSnapshot.DistantVisibilityMeters,
        },
        vehicle = _vehicleSnapshot is null ? null : new
        {
            semantic_nodes = _vehicleSnapshot.SemanticNodeCount,
            damage_zones = _vehicleSnapshot.DamageZoneCount,
            contract_resolved = _vehicleSnapshot.ContractResolved,
        },
    };

    private object Acceptance(List<StallEvent> steadyStalls)
    {
        var p95 = _frameMilliseconds.Quantile(0.95);
        var p99 = _frameMilliseconds.Quantile(0.99);
        var seconds = _memorySamples.ConvertAll(sample => sample.Seconds);
        var workingSet = _memorySamples.ConvertAll(sample => (double)sample.WorkingSetBytes);
        var slopeBytesPerMinute = Slope(seconds, workingSet) * 60;
        var rSquared = RSquared(seconds, workingSet);
        var evaluatedForGrowth = _options.MeasureSeconds >= 1_800;
        // ADR-0023 (2026-08-14 addendum): a frame-capped run is judged on whether it
        // holds the cap, not against the uncapped p95 limit. The 16.67 ms limit sits
        // 3.3 microseconds above a 60 FPS cap period of 16.6667 ms, so passing it
        // would need 95% of frames within 3.3 us of the cap against roughly 241 us of
        // ordinary pacing jitter. Applying it to a capped run marks a build that is
        // holding the cap exactly as failing.
        var capped = _options.MaxFps > 0;
        var capPeriodMilliseconds = capped ? 1_000.0 / _options.MaxFps : 0.0;
        var meanFps = _frameMilliseconds.Count > 0 && _frameMilliseconds.Mean > 0
            ? 1_000.0 / _frameMilliseconds.Mean
            : 0.0;
        var p50 = _frameMilliseconds.Quantile(0.50);
        return new
        {
            // No `passed` key at all on a capped run. Emitting one, even a true one,
            // would let a consumer that does not check `applicable` report a capped
            // run as having passed a limit that was never evaluated.
            p95_frame_ms = capped
                ? (object)new
                {
                    measured = p95,
                    limit = 16.67,
                    applicable = false,
                    note = "Not applicable to a frame-capped run; see cap_adherence.",
                }
                : new
                {
                    measured = p95,
                    limit = 16.67,
                    applicable = true,
                    passed = p95 <= 16.67,
                    note = "Uncapped run judged against the ADR-0023 p95 limit.",
                },
            cap_adherence = capped
                ? (object)new
                {
                    engine_max_fps = _options.MaxFps,
                    cap_period_ms = capPeriodMilliseconds,
                    mean_fps = meanFps,
                    p50_frame_ms = p50,
                    mean_fps_tolerance = 0.1,
                    p50_frame_ms_tolerance = 0.1,
                    criterion =
                        "mean FPS within 0.1 of the cap AND p50 within 0.1 ms of the " +
                        "cap period AND no steady-driving stall over 50 ms",
                    criterion_status = "ratified 2026-08-14 (ADR-0023 Q-022e)",
                    passed = Math.Abs(meanFps - _options.MaxFps) <= 0.1 &&
                        Math.Abs(p50 - capPeriodMilliseconds) <= 0.1 &&
                        steadyStalls.Count == 0,
                }
                : new
                {
                    applicable = false,
                    note = "Uncapped run; judged on the percentile limits above.",
                },
            p99_frame_ms = new
            {
                measured = p99,
                limit = 20.0,
                passed = p99 <= 20.0,
            },
            steady_driving_stalls_over_threshold = new
            {
                // Counted at the ADR-0023 acceptance threshold, not at the recording
                // threshold. Lowering recording for diagnosis must not silently
                // tighten the gate.
                measured = steadyStalls.Count(stall =>
                    stall.FrameMilliseconds > StallAcceptanceThresholdMilliseconds),
                limit = 0,
                passed = !steadyStalls.Any(stall =>
                    stall.FrameMilliseconds > StallAcceptanceThresholdMilliseconds),
                acceptance_threshold_ms = StallAcceptanceThresholdMilliseconds,
                recording_threshold_ms = StallThresholdMilliseconds,
            },
            gpu_memory_bytes = new
            {
                measured = (long)_peakVideoMemoryBytes,
                limit = 9_500_000_000L,
                passed = _peakVideoMemoryBytes <= 9_500_000_000d,
            },
            working_set_bytes = new
            {
                measured = _peakWorkingSetBytes,
                limit = 16_000_000_000L,
                passed = _peakWorkingSetBytes <= 16_000_000_000L,
            },
            sustained_memory_growth = new
            {
                working_set_slope_bytes_per_minute = slopeBytesPerMinute,
                working_set_r_squared = rSquared,
                evaluated = evaluatedForGrowth,
                // ADR-0023 requires "no sustained positive growth"; the 2026-08-14
                // addendum quantifies it. A trend counts as sustained only when it both
                // rises faster than 1 MiB/min and explains at least half the variance.
                // The R^2 term is load-bearing: without it the rule fires on ordinary
                // allocate-and-collect sawtooth, where a run ending where it started can
                // still show a positive fitted slope.
                criterion = "slope > 1 MiB/min AND R^2 >= 0.5 over the measured window",
                criterion_status = "ratified 2026-08-14 (ADR-0023 Q-022d)",
                passed = !evaluatedForGrowth ||
                    !(slopeBytesPerMinute > 1_048_576d && rSquared >= 0.5),
                note = evaluatedForGrowth
                    ? "Evaluated against the 30-minute steady-state threshold."
                    : "Run shorter than 30 minutes; slope is reported but the ADR-0023 " +
                        "sustained-growth threshold is not evaluated by this run.",
            },
        };
    }

    private object MemoryTrend(Func<MemorySample, double> selector)
    {
        if (_memorySamples.Count < 2)
        {
            return new
            {
                sample_count = _memorySamples.Count,
                slope_bytes_per_minute = 0d,
                r_squared = 0d,
                first_bytes = 0d,
                last_bytes = 0d,
            };
        }
        var seconds = _memorySamples.ConvertAll(sample => sample.Seconds);
        var values = _memorySamples.ConvertAll(new Converter<MemorySample, double>(selector));
        return new
        {
            sample_count = _memorySamples.Count,
            slope_bytes_per_minute = Slope(seconds, values) * 60,
            r_squared = RSquared(seconds, values),
            first_bytes = values[0],
            last_bytes = values[^1],
        };
    }

    private static void EnsureDirectory(string path)
    {
        var directory = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }
    }

    private static double Mean(IReadOnlyList<double> samples)
    {
        if (samples.Count == 0)
        {
            return 0;
        }
        var total = 0d;
        foreach (var value in samples)
        {
            total += value;
        }
        return total / samples.Count;
    }

    private static double Slope(IReadOnlyList<double> x, IReadOnlyList<double> y)
    {
        if (x.Count < 2 || x.Count != y.Count)
        {
            return 0;
        }
        var meanX = Mean(x);
        var meanY = Mean(y);
        var numerator = 0d;
        var denominator = 0d;
        for (var index = 0; index < x.Count; index++)
        {
            var deltaX = x[index] - meanX;
            numerator += deltaX * (y[index] - meanY);
            denominator += deltaX * deltaX;
        }
        return denominator == 0 ? 0 : numerator / denominator;
    }

    private static double RSquared(IReadOnlyList<double> x, IReadOnlyList<double> y)
    {
        if (x.Count < 2 || x.Count != y.Count)
        {
            return 0;
        }
        var slope = Slope(x, y);
        var meanX = Mean(x);
        var meanY = Mean(y);
        var intercept = meanY - (slope * meanX);
        var residual = 0d;
        var total = 0d;
        for (var index = 0; index < x.Count; index++)
        {
            var predicted = intercept + (slope * x[index]);
            residual += Math.Pow(y[index] - predicted, 2);
            total += Math.Pow(y[index] - meanY, 2);
        }
        return total == 0 ? 0 : 1 - (residual / total);
    }

    public string CompletionMarker()
    {
        var steadyStalls = _stalls.FindAll(stall => !stall.NearLoopWrap).Count;
        return "CANNONBALL_REFERENCE_PERFORMANCE_OK " +
            $"scenario={_options.ScenarioId} " +
            $"resolution={_options.WidthPixels}x{_options.HeightPixels} " +
            $"headless={_options.Headless.ToString().ToLowerInvariant()} " +
            $"vsync={(_options.VsyncEnabled ? "on" : "off")} " +
            $"lighting={_options.Lighting.ToString().ToLowerInvariant()} " +
            $"environment_quality={_environmentSnapshot?.ProfileId ?? "unmeasured"} " +
            $"road={_roadSnapshot?.ProfileId ?? "unmeasured"} " +
            $"measured_s={_measuredSeconds:0.000} frames={_frameMilliseconds.Count} " +
            $"p50_ms={_frameMilliseconds.Quantile(0.50):0.000} " +
            $"p95_ms={_frameMilliseconds.Quantile(0.95):0.000} " +
            $"p99_ms={_frameMilliseconds.Quantile(0.99):0.000} " +
            $"max_ms={_frameMilliseconds.Maximum:0.000} " +
            $"steady_stalls_over_50ms={steadyStalls} " +
            $"peak_gpu_mem_bytes={(long)_peakVideoMemoryBytes} " +
            $"peak_working_set_bytes={_peakWorkingSetBytes} " +
            $"peak_draw_calls={_peakDrawCalls} " +
            $"summary={_options.SummaryPath}";
    }

    /// <summary>
    /// Fixed-width latency histogram with exact count, sum, minimum, and maximum. Buckets are
    /// allocated once so recording a sample never allocates and never triggers a collection.
    /// </summary>
    private sealed class LatencyHistogram
    {
        public const double BucketMilliseconds = 0.005;
        private const int BucketCount = 200_000; // 0 ms .. 1000 ms

        private readonly int[] _buckets = new int[BucketCount];
        private long _count;
        private double _sum;
        private double _minimum = double.MaxValue;

        public long Count => _count;
        public double Maximum { get; private set; }
        public double Minimum => _count == 0 ? 0 : _minimum;
        public double Mean => _count == 0 ? 0 : _sum / _count;
        public long OverflowCount { get; private set; }

        public void Add(double milliseconds)
        {
            if (!double.IsFinite(milliseconds) || milliseconds < 0)
            {
                return;
            }
            _count++;
            _sum += milliseconds;
            if (milliseconds > Maximum)
            {
                Maximum = milliseconds;
            }
            if (milliseconds < _minimum)
            {
                _minimum = milliseconds;
            }
            var index = (int)(milliseconds / BucketMilliseconds);
            if (index >= BucketCount)
            {
                OverflowCount++;
                index = BucketCount - 1;
            }
            _buckets[index]++;
        }

        /// <summary>
        /// Bucket-resolution quantile. Values beyond the histogram range saturate at the
        /// exact recorded maximum rather than at the top bucket edge.
        /// </summary>
        public double Quantile(double percentile)
        {
            if (_count == 0)
            {
                return 0;
            }
            var target = percentile * _count;
            long cumulative = 0;
            for (var index = 0; index < BucketCount; index++)
            {
                cumulative += _buckets[index];
                if (cumulative >= target)
                {
                    if (index == BucketCount - 1 && OverflowCount > 0)
                    {
                        return Maximum;
                    }
                    return Math.Min(Maximum, (index + 0.5) * BucketMilliseconds);
                }
            }
            return Maximum;
        }

        public object Describe() => new
        {
            sample_count = _count,
            p50 = Quantile(0.50),
            p95 = Quantile(0.95),
            p99 = Quantile(0.99),
            minimum = Minimum,
            maximum = Maximum,
            mean = Mean,
            bucket_resolution_ms = BucketMilliseconds,
            above_histogram_range_count = OverflowCount,
        };
    }

    private sealed record StallEvent(
        double Seconds,
        double FrameMilliseconds,
        double CpuMilliseconds,
        double GpuMilliseconds,
        double RouteDistanceMeters,
        double SpeedMetersPerSecond,
        bool NearLoopWrap,
        FrameWork Work);

    /// <summary>
    /// Work the process performed during a single frame, expressed as deltas of
    /// cumulative counters the streamer and runtime already maintain.
    ///
    /// The balanced and High captures both recorded steady-driving stalls whose
    /// render CPU and GPU components were near 1 ms, so the cost was outside the
    /// measured render path and nothing in the harness could localise it. These
    /// deltas answer the first attribution question a stall raises: did the
    /// process collect garbage, build or drop a chunk, rebase the origin, or
    /// spend the frame somewhere the render timers never see?
    ///
    /// This is a struct of value fields sampled from counters that already exist.
    /// Nothing here allocates, so the harness self-accounting stays honest.
    /// </summary>
    private readonly record struct FrameWork(
        int Gen0Collections,
        int Gen1Collections,
        int Gen2Collections,
        int CollisionBuilds,
        int CollisionRemovals,
        int Rebases,
        int ChunkFailures,
        int LoadedChunks,
        int LoadedEnvironmentChunks,
        bool ChunkBuildPeakAdvanced,
        bool CollisionBuildPeakAdvanced,
        bool EnvironmentBuildPeakAdvanced,
        double PhysicsProcessMilliseconds,
        double ProcessMilliseconds,
        SubsystemMilliseconds Subsystems)
    {
        /// <summary>
        /// True when the frame did any work this record can name. A stall with
        /// <c>false</c> here is one none of these counters explains.
        /// </summary>
        public bool HasAttributableWork =>
            Gen0Collections > 0 ||
            Gen1Collections > 0 ||
            Gen2Collections > 0 ||
            CollisionBuilds > 0 ||
            CollisionRemovals > 0 ||
            Rebases > 0 ||
            ChunkFailures > 0 ||
            LoadedChunks != 0 ||
            LoadedEnvironmentChunks != 0 ||
            ChunkBuildPeakAdvanced ||
            CollisionBuildPeakAdvanced ||
            EnvironmentBuildPeakAdvanced;
    }

    /// <summary>
    /// Exclusive CPU milliseconds per ADR-0023 layer-2 subsystem for one frame.
    /// </summary>
    /// <remarks>
    /// Layer 2 remains unmeasured reserves under the Q-022b answer. These values
    /// are what would let it be ratified as measurements; until that happens they
    /// are evidence, not budget.
    /// </remarks>
    /// <summary>One measured frame, kept only long enough to serve an operator mark.</summary>
    private readonly record struct FrameTrace(
        double Seconds,
        double FrameMilliseconds,
        double RideHeightMeters,
        double RouteDistanceMeters,
        double SpeedMetersPerSecond,
        int RebaseCount,
        int ResetCount);

    private readonly record struct SubsystemMilliseconds(
        double Road,
        double RouteContext,
        double Environment,
        double Vehicle,
        double Ui,
        double Total);

    /// <summary>
    /// Absolute counter values, differenced frame to frame to produce a
    /// <see cref="FrameWork"/>.
    /// </summary>
    private readonly record struct WorkCounters(
        int Gen0Collections,
        int Gen1Collections,
        int Gen2Collections,
        int CollisionBuilds,
        int CollisionRemovals,
        int Rebases,
        int ChunkFailures,
        int LoadedChunks,
        int LoadedEnvironmentChunks,
        double MaximumChunkBuildMilliseconds,
        double MaximumCollisionBuildMilliseconds,
        double MaximumEnvironmentBuildMilliseconds);

    private sealed record MemorySample(
        double Seconds,
        long WorkingSetBytes,
        double VideoMemoryBytes,
        double TextureMemoryBytes,
        double BufferMemoryBytes,
        long ManagedHeapBytes,
        int Gen0Collections,
        int Gen1Collections,
        int Gen2Collections);

    private sealed record AggregateRow(
        double Seconds,
        int FrameCount,
        double MedianMilliseconds,
        double MaximumMilliseconds,
        long MaxDrawCalls,
        long MaxPrimitives,
        double RouteDistanceMeters,
        double SpeedMetersPerSecond,
        int LoadedChunkCount,
        int RebaseCount);

    private sealed record LightingState(
        Color Light,
        float Energy,
        float PitchDegrees,
        Color Background,
        Color Ambient,
        float AmbientEnergy);
}

public enum LightingMode
{
    Daylight,
    Night,
}

public sealed record ReferencePerformanceOptions(
    string ScenarioId,
    int WidthPixels,
    int HeightPixels,
    bool Headless,
    bool VsyncEnabled,
    int MaxFps,
    LightingMode Lighting,
    double TargetSpeedMetersPerSecond,
    double WarmupSeconds,
    double MeasureSeconds,
    bool LoopCorridor,
    string SummaryPath,
    string SamplesPath,
    CameraView Camera = CameraView.Chase);

/// <summary>
/// Which camera the reference run drives from. Cockpit exists so a daylight
/// cockpit capture is reachable from the command line; the camera-handling
/// contract scenario is the only other path that reaches cockpit view and it
/// takes no lighting argument.
/// </summary>
public enum CameraView
{
    Chase,
    Cockpit,
}
