using Godot;

namespace Cannonball.Game.Vehicle.Showroom;

/// <summary>Debug observer only: monotonic intervals, private draw costs, whole-process memory.</summary>
internal sealed class ShowroomMetrics : IDisposable
{
    private const int Capacity = 32768;
    private readonly double[] _frames = new double[Capacity], _sorted = new double[Capacity];
    private readonly System.Diagnostics.Process _process = System.Diagnostics.Process.GetCurrentProcess();
    private ulong _started, _previous, _published;
    private int _count;
    private bool _overflow;
    private string _case = "";
    private long _workingSetHigh;
    private double _videoHigh, _staticHigh, _drawHigh, _shadowDrawHigh, _triangleHigh;

    public void BeginCase(string view, string lighting)
    {
        _case = view + ":" + lighting;
        _started = Time.GetTicksUsec(); _previous = _published = 0;
        _count = 0; _overflow = false; _workingSetHigh = 0;
        _videoHigh = _staticHigh = _drawHigh = _shadowDrawHigh = _triangleHigh = 0;
    }

    public void RecordFrame(SubViewport viewport)
    {
        var now = Time.GetTicksUsec();
        if (_previous != 0 && now - _started >= 2_000_000)
        {
            if (_count < Capacity) _frames[_count++] = (now - _previous) / 1_000.0;
            else _overflow = true;
            _videoHigh = Math.Max(_videoHigh, Performance.GetMonitor(Performance.Monitor.RenderVideoMemUsed));
            _staticHigh = Math.Max(_staticHigh, Performance.GetMonitor(Performance.Monitor.MemoryStatic));
            _drawHigh = Math.Max(_drawHigh, viewport.GetRenderInfo(Viewport.RenderInfoType.Visible, Viewport.RenderInfo.DrawCallsInFrame));
            _shadowDrawHigh = Math.Max(_shadowDrawHigh, viewport.GetRenderInfo(Viewport.RenderInfoType.Shadow, Viewport.RenderInfo.DrawCallsInFrame));
            _triangleHigh = Math.Max(_triangleHigh, viewport.GetRenderInfo(Viewport.RenderInfoType.Visible, Viewport.RenderInfo.PrimitivesInFrame));
        }
        _previous = now;
    }

    public void Publish(Godot.Collections.Dictionary state)
    {
        var now = Time.GetTicksUsec();
        if (_published != 0 && now - _published < 1_000_000) return;
        _published = now;
        state["metrics_case"] = _case;
        state["metrics_samples"] = _count; state["metrics_overflow"] = _overflow;
        state["metrics_warmup_seconds"] = 2;
        state["metrics_elapsed_seconds"] = Math.Max(0, (now - _started) / 1_000_000.0 - 2);
        Array.Copy(_frames, _sorted, _count);
        Array.Sort(_sorted, 0, _count);
        _process.Refresh(); _workingSetHigh = Math.Max(_workingSetHigh, _process.WorkingSet64);
        state["frame_p50_ms"] = Quantile(.5); state["frame_p95_ms"] = Quantile(.95);
        state["frame_p99_ms"] = Quantile(.99); state["frame_max_ms"] = _count == 0 ? 0 : _sorted[_count - 1];
        state["process_working_set_high_mib"] = _workingSetHigh / 1048576.0;
        state["engine_static_high_mib"] = _staticHigh / 1048576.0;
        state["render_video_high_mib"] = _videoHigh / 1048576.0;
        state["viewport_draw_calls_high"] = _drawHigh; state["viewport_shadow_draw_calls_high"] = _shadowDrawHigh;
        state["viewport_primitives_high"] = _triangleHigh;
    }

    private double Quantile(double percentile)
    {
        if (_count == 0) return 0;
        var index = (_count - 1) * percentile;
        var lower = (int)index;
        return _sorted[lower] + (_sorted[Math.Min(lower + 1, _count - 1)] - _sorted[lower]) * (index - lower);
    }

    public void Dispose() => _process.Dispose();
}
