using System.Diagnostics;
using Cannonball.Core.Performance;

namespace Cannonball.Core.Tests;

/// <summary>
/// Exclusive-time accounting for ADR-0023 layer-2 attribution (Q-022c).
/// </summary>
/// <remarks>
/// The property that matters is that nesting does not double count. Environment
/// chunks build inside the streamer's road region, so a profiler that charged
/// elapsed time to both would report the same milliseconds twice and inflate
/// every subsystem that contains another.
/// </remarks>
public sealed class SubsystemProfilerTests : IDisposable
{
    public SubsystemProfilerTests()
    {
        SubsystemProfiler.Enabled = true;
        SubsystemProfiler.Drain();
    }

    public void Dispose()
    {
        SubsystemProfiler.Drain();
        SubsystemProfiler.Enabled = false;
    }

    private static void Busy(double milliseconds)
    {
        var started = Stopwatch.GetTimestamp();
        while (Stopwatch.GetElapsedTime(started).TotalMilliseconds < milliseconds)
        {
        }
    }

    [Fact]
    public void DisabledProfilerRecordsNothing()
    {
        SubsystemProfiler.Drain();
        SubsystemProfiler.Enabled = false;
        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Road))
        {
            Busy(5);
        }
        SubsystemProfiler.Enabled = true;

        Assert.Equal(0, SubsystemProfiler.Drain().Total);
    }

    [Fact]
    public void RegionChargesItsOwnSubsystem()
    {
        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Vehicle))
        {
            Busy(10);
        }

        var sample = SubsystemProfiler.Drain();
        Assert.InRange(sample.Vehicle, 8, 60);
        Assert.Equal(0, sample.Road);
        Assert.Equal(0, sample.Environment);
    }

    [Fact]
    public void NestedRegionIsNotChargedToBothSubsystems()
    {
        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Road))
        {
            Busy(10);
            using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Environment))
            {
                Busy(20);
            }
            Busy(10);
        }

        var sample = SubsystemProfiler.Drain();

        // The inner 20 ms belongs to Environment alone; Road keeps only the 20 ms
        // it spent outside it. A profiler that summed elapsed time would report
        // 40 ms of Road and a total of 60 ms for a 40 ms interval.
        Assert.InRange(sample.Environment, 16, 90);
        Assert.InRange(sample.Road, 16, 90);
        Assert.InRange(sample.Total, 32, 150);
        Assert.True(
            sample.Total < sample.Road + sample.Environment + 1,
            $"total {sample.Total} should be the sum of exclusive parts, not of elapsed spans");
    }

    [Fact]
    public void DrainReturnsOnlyTheIntervalSinceTheLastDrain()
    {
        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Ui))
        {
            Busy(10);
        }
        var first = SubsystemProfiler.Drain();

        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Ui))
        {
            Busy(10);
        }
        var second = SubsystemProfiler.Drain();

        Assert.InRange(first.Ui, 8, 60);
        Assert.InRange(second.Ui, 8, 60);
        Assert.Equal(0, SubsystemProfiler.Drain().Ui);
    }

    [Fact]
    public void DrainingInsideARegionSplitsItAcrossIntervals()
    {
        // A frame boundary can fall inside a long region. Its time must land in the
        // interval it was spent in, not all in whichever interval it closes in.
        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Road))
        {
            Busy(15);
            var mid = SubsystemProfiler.Drain();
            Assert.InRange(mid.Road, 12, 90);
            Busy(15);
        }

        Assert.InRange(SubsystemProfiler.Drain().Road, 12, 90);
    }

    [Fact]
    public void TotalIsTheSumOfTheParts()
    {
        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Road))
        {
            Busy(3);
        }
        using (SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Ui))
        {
            Busy(3);
        }

        var sample = SubsystemProfiler.Drain();
        Assert.Equal(
            sample.Road + sample.RouteContext + sample.Environment + sample.Vehicle + sample.Ui,
            sample.Total,
            10);
    }
}
