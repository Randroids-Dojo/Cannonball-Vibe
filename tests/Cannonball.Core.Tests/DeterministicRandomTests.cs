using Cannonball.Core.Simulation;

namespace Cannonball.Core.Tests;

public sealed class DeterministicRandomTests
{
    [Fact]
    public void SameSeedProducesSameSequence()
    {
        var first = new SplitMix64Random(8675309);
        var second = new SplitMix64Random(8675309);

        Assert.Equal(
            Enumerable.Range(0, 100).Select(_ => first.NextUInt64()),
            Enumerable.Range(0, 100).Select(_ => second.NextUInt64()));
    }

    [Fact]
    public void NamedStreamsAreStableAndIsolated()
    {
        var first = new RandomStreamSet(42);
        var second = new RandomStreamSet(42);

        Assert.Equal(first.For("traffic", "edge-7").NextUInt64(), second.For("traffic", "edge-7").NextUInt64());
        Assert.NotEqual(first.For("traffic", "edge-7").NextUInt64(), first.For("events", "edge-7").NextUInt64());
    }
}
