namespace Cannonball.Core.Simulation;

public interface IRandomStream
{
    ulong NextUInt64();

    double NextDouble();

    int NextInt32(int exclusiveMaximum);
}

public sealed class SplitMix64Random : IRandomStream
{
    private ulong _state;

    public SplitMix64Random(ulong seed)
    {
        _state = seed;
    }

    public ulong NextUInt64()
    {
        _state += 0x9E3779B97F4A7C15UL;
        var value = _state;
        value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9UL;
        value = (value ^ (value >> 27)) * 0x94D049BB133111EBUL;
        return value ^ (value >> 31);
    }

    public double NextDouble() => (NextUInt64() >> 11) * (1.0 / (1UL << 53));

    public int NextInt32(int exclusiveMaximum)
    {
        if (exclusiveMaximum <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(exclusiveMaximum));
        }

        return (int)(NextUInt64() % (uint)exclusiveMaximum);
    }
}

public sealed class RandomStreamSet
{
    private const ulong FnvOffsetBasis = 14_695_981_039_346_656_037UL;
    private const ulong FnvPrime = 1_099_511_628_211UL;
    private readonly ulong _runSeed;

    public RandomStreamSet(ulong runSeed)
    {
        _runSeed = runSeed;
    }

    public IRandomStream For(string systemName, string stableEntityId = "")
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(systemName);
        var hash = FnvOffsetBasis ^ _runSeed;
        hash = HashCharacters(hash, systemName);
        hash = (hash ^ 0xff) * FnvPrime;
        hash = HashCharacters(hash, stableEntityId);
        return new SplitMix64Random(hash);
    }

    private static ulong HashCharacters(ulong hash, string value)
    {
        foreach (var character in value)
        {
            hash = (hash ^ (byte)character) * FnvPrime;
            hash = (hash ^ (byte)(character >> 8)) * FnvPrime;
        }
        return hash;
    }
}
