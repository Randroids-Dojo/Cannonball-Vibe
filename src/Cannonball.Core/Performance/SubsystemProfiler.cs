using System.Diagnostics;

namespace Cannonball.Core.Performance;

/// <summary>
/// Per-frame CPU attribution by ADR-0023 layer-2 subsystem.
/// </summary>
/// <remarks>
/// Q-022b could not ratify layer-2 allocations because the harness measured whole
/// frames: going from the balanced to the High content profile moved no
/// percentile, so any per-subsystem split derived from that comparison would have
/// been derived from noise. The owner answered Q-022c on 2026-08-16 by choosing
/// in-engine timers over an external profiler, so subsystems are timed at their
/// own boundaries rather than inferred.
///
/// What this can and cannot show. It attributes CPU time inside the process to
/// the boundaries ADR-0023's layer 2 is written in terms of. It does not split
/// GPU time, and it cannot see cost outside the process — which is what the
/// 2026-08-13 stall evidence pointed at, where render CPU and GPU were both near
/// 1 ms in a 50-60 ms frame. Attribution here is for budgeting, not for that
/// stall.
///
/// Regions measure <b>exclusive</b> time. Environment chunks build inside the
/// streamer's road region, so charging elapsed time to both would report the same
/// milliseconds twice and inflate every subsystem containing another. A nested
/// region suspends its parent and resumes it on exit, which makes the per-frame
/// total a partition of instrumented time rather than an upper bound.
///
/// Not thread safe, and deliberately so: every instrumented boundary runs on the
/// main thread. Chunk reads happen on task threads, but the attach that builds
/// nodes runs in _Process. A region entered off the main thread would corrupt the
/// stack rather than merely mis-attribute, so instrument accordingly.
///
/// Disabled unless a reference capture turns it on, so ordinary play pays only a
/// predictable branch per region.
/// </remarks>
public static class SubsystemProfiler
{
    /// <summary>
    /// The subsystems ADR-0023 layer 2 names, restricted to those that exist.
    /// </summary>
    /// <remarks>
    /// Traffic, effects and lighting have layer-2 reserves but no implementation,
    /// so timing them would report a confident zero for a system that does not
    /// exist. They are added when they are built.
    /// </remarks>
    public enum Subsystem
    {
        Road,
        RouteContext,
        Environment,
        Vehicle,
        Ui,
        Camera,
        Orchestration,
        Input,
    }

    private const int SubsystemCount = 8;

    // Deeper than any instrumented nesting; overflow drops the region rather than
    // throwing, because a profiler must never be the reason a capture fails.
    private const int MaximumDepth = 16;

    private static readonly double[] FrameTicks = new double[SubsystemCount];
    // Allocation is attributed the same way as time, because a managed pause is
    // caused by whoever produced the garbage, not by whoever happened to be running
    // when the collector ran.
    private static readonly long[] FrameBytes = new long[SubsystemCount];
    private static readonly long[] StackAllocatedAt = new long[MaximumDepth];
    private static readonly Subsystem[] StackSubsystem = new Subsystem[MaximumDepth];
    private static readonly long[] StackResumedAt = new long[MaximumDepth];
    private static readonly double MillisecondsPerTick = 1_000.0 / Stopwatch.Frequency;
    private static int _depth;

    /// <summary>Off unless a reference capture enables it.</summary>
    public static bool Enabled { get; set; }

    /// <summary>
    /// Returns exclusive milliseconds accumulated since the previous drain, and
    /// resets the accumulators.
    /// </summary>
    /// <remarks>
    /// Drain-on-read rather than reset-at-frame-start, deliberately. A reset that
    /// had to run before every instrumented subsystem would depend on Godot's node
    /// processing order, and a subsystem processed earlier in the tree than the
    /// resetter would have its time discarded. Draining makes the reading
    /// self-contained: whatever accumulated between two reads belongs to that
    /// interval, whoever ran first.
    /// </remarks>
    public static Sample Drain()
    {
        if (!Enabled)
        {
            return default;
        }
        // Charge the running region before snapshotting. Only the innermost is
        // accruing — outer ones were suspended when their child opened — and its
        // time so far belongs to this interval, not to whichever interval it
        // happens to close in. Without this, draining inside a long region
        // reports zero for it and then attributes the whole span to the next read.
        var now = Stopwatch.GetTimestamp();
        var allocated = GC.GetAllocatedBytesForCurrentThread();
        if (_depth > 0)
        {
            FrameTicks[(int)StackSubsystem[_depth - 1]] += now - StackResumedAt[_depth - 1];
            FrameBytes[(int)StackSubsystem[_depth - 1]] +=
                allocated - StackAllocatedAt[_depth - 1];
            StackResumedAt[_depth - 1] = now;
            StackAllocatedAt[_depth - 1] = allocated;
        }
        var sample = new Sample(
            FrameTicks[(int)Subsystem.Road] * MillisecondsPerTick,
            FrameTicks[(int)Subsystem.RouteContext] * MillisecondsPerTick,
            FrameTicks[(int)Subsystem.Environment] * MillisecondsPerTick,
            FrameTicks[(int)Subsystem.Vehicle] * MillisecondsPerTick,
            FrameTicks[(int)Subsystem.Ui] * MillisecondsPerTick,
            FrameTicks[(int)Subsystem.Camera] * MillisecondsPerTick,
            FrameTicks[(int)Subsystem.Orchestration] * MillisecondsPerTick,
            FrameTicks[(int)Subsystem.Input] * MillisecondsPerTick,
            FrameBytes[(int)Subsystem.Road],
            FrameBytes[(int)Subsystem.RouteContext],
            FrameBytes[(int)Subsystem.Environment],
            FrameBytes[(int)Subsystem.Vehicle],
            FrameBytes[(int)Subsystem.Ui],
            FrameBytes[(int)Subsystem.Camera],
            FrameBytes[(int)Subsystem.Orchestration],
            FrameBytes[(int)Subsystem.Input]);
        Array.Clear(FrameTicks);
        Array.Clear(FrameBytes);
        return sample;
    }

    /// <summary>One interval's exclusive milliseconds, by subsystem.</summary>
    public readonly record struct Sample(
        double Road,
        double RouteContext,
        double Environment,
        double Vehicle,
        double Ui,
        double Camera = 0,
        double Orchestration = 0,
        double InputHandling = 0,
        long RoadBytes = 0,
        long RouteContextBytes = 0,
        long EnvironmentBytes = 0,
        long VehicleBytes = 0,
        long UiBytes = 0,
        long CameraBytes = 0,
        long OrchestrationBytes = 0,
        long InputBytes = 0)
    {
        public double Total => Road + RouteContext + Environment + Vehicle + Ui;

        public long TotalBytes =>
            RoadBytes + RouteContextBytes + EnvironmentBytes + VehicleBytes + UiBytes
            + CameraBytes + OrchestrationBytes + InputBytes;
    }

    /// <summary>Times a region, charging it exclusively to one subsystem.</summary>
    public static Region Measure(Subsystem subsystem)
    {
        if (!Enabled || _depth >= MaximumDepth)
        {
            return default;
        }
        var now = Stopwatch.GetTimestamp();
        var allocated = GC.GetAllocatedBytesForCurrentThread();
        if (_depth > 0)
        {
            // Suspend the parent: it is charged up to here, and resumes when this
            // region closes.
            FrameTicks[(int)StackSubsystem[_depth - 1]] += now - StackResumedAt[_depth - 1];
            FrameBytes[(int)StackSubsystem[_depth - 1]] +=
                allocated - StackAllocatedAt[_depth - 1];
        }
        StackSubsystem[_depth] = subsystem;
        StackResumedAt[_depth] = now;
        StackAllocatedAt[_depth] = allocated;
        _depth++;
        return new Region(true);
    }

    public readonly ref struct Region
    {
        private readonly bool _open;

        internal Region(bool open) => _open = open;

        public void Dispose()
        {
            // A closed region whose frame was reset mid-flight has nothing to
            // charge; _depth is the authority, not this instance.
            if (!_open || _depth == 0)
            {
                return;
            }
            var now = Stopwatch.GetTimestamp();
            var allocated = GC.GetAllocatedBytesForCurrentThread();
            _depth--;
            FrameTicks[(int)StackSubsystem[_depth]] += now - StackResumedAt[_depth];
            FrameBytes[(int)StackSubsystem[_depth]] += allocated - StackAllocatedAt[_depth];
            if (_depth > 0)
            {
                StackResumedAt[_depth - 1] = now;
                StackAllocatedAt[_depth - 1] = allocated;
            }
        }
    }
}
