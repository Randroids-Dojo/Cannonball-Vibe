using System.Security.Cryptography;
using Cannonball.Content;
using Cannonball.Core.Routes;
using Google.FlatBuffers;

namespace Cannonball.Core.Content;

public readonly record struct RouteChunkSample(
    double DistanceMeters,
    float LateralMeters,
    float ElevationMeters,
    float Curvature,
    float Grade,
    double ProjectedXMeters,
    double ProjectedYMeters,
    double ProjectedTangentX,
    double ProjectedTangentY);

public sealed record RouteChunkContent(
    string ContentVersion,
    string Id,
    string EdgeId,
    double StartMeters,
    double EndMeters,
    IReadOnlyList<RouteChunkSample> Samples);

public static class FlatBufferRouteChunkContent
{
    public const int MaximumChunkBytes = 16_000_000;

    public static RouteChunkContent Load(
        ReadOnlyMemory<byte> bytes,
        ChunkManifest manifest,
        string expectedContentVersion)
    {
        if (bytes.Length >= MaximumChunkBytes)
        {
            throw new InvalidDataException("Route chunk exceeds the 16 MB budget.");
        }
        var buffer = new ByteBuffer(bytes.ToArray());
        if (!RouteChunkBuffer.RouteChunkBufferBufferHasIdentifier(buffer) ||
            !RouteChunkBuffer.VerifyRouteChunkBuffer(buffer))
        {
            throw new InvalidDataException("Route chunk is not a valid CBCK FlatBuffer.");
        }
        var root = RouteChunkBuffer.GetRootAsRouteChunkBuffer(buffer);
        if (root.SchemaVersion != 1 ||
            root.ContentVersion != expectedContentVersion ||
            root.Id != manifest.Id ||
            root.EdgeId != manifest.EdgeId ||
            root.StartMeters != manifest.StartMeters ||
            root.EndMeters != manifest.EndMeters)
        {
            throw new InvalidDataException("Route chunk does not match its root manifest.");
        }
        var samples = new RouteChunkSample[root.SamplesLength];
        var previousDistance = double.NegativeInfinity;
        for (var index = 0; index < samples.Length; index++)
        {
            var sample = root.Samples(index)
                ?? throw new InvalidDataException($"Route chunk sample {index} is missing.");
            if (!double.IsFinite(sample.DistanceMeters) ||
                !float.IsFinite(sample.LateralMeters) ||
                !float.IsFinite(sample.ElevationMeters) ||
                !float.IsFinite(sample.Curvature) ||
                !float.IsFinite(sample.Grade) ||
                !double.IsFinite(sample.ProjectedXMeters) ||
                !double.IsFinite(sample.ProjectedYMeters) ||
                !double.IsFinite(sample.ProjectedTangentX) ||
                !double.IsFinite(sample.ProjectedTangentY) ||
                Math.Abs(Math.Sqrt(
                    sample.ProjectedTangentX * sample.ProjectedTangentX +
                    sample.ProjectedTangentY * sample.ProjectedTangentY) - 1) > 1e-6 ||
                sample.DistanceMeters <= previousDistance)
            {
                throw new InvalidDataException(
                    $"Route chunk sample {index} is non-finite or not strictly increasing.");
            }
            samples[index] = new RouteChunkSample(
                sample.DistanceMeters,
                sample.LateralMeters,
                sample.ElevationMeters,
                sample.Curvature,
                sample.Grade,
                sample.ProjectedXMeters,
                sample.ProjectedYMeters,
                sample.ProjectedTangentX,
                sample.ProjectedTangentY);
            previousDistance = sample.DistanceMeters;
        }
        if (samples.Length == 0 ||
            samples[0].DistanceMeters != manifest.StartMeters ||
            samples[^1].DistanceMeters != manifest.EndMeters)
        {
            throw new InvalidDataException("Route chunk samples do not exactly span the manifest range.");
        }
        return new RouteChunkContent(
            expectedContentVersion,
            manifest.Id,
            manifest.EdgeId,
            manifest.StartMeters,
            manifest.EndMeters,
            samples);
    }
}

public sealed class VerifiedFileChunkSource : IChunkSource
{
    private readonly RouteContentPackage _package;
    private readonly string _packageDirectory;

    public VerifiedFileChunkSource(RouteContentPackage package, string packageDirectory)
    {
        _package = package;
        _packageDirectory = Path.GetFullPath(packageDirectory);
    }

    public ValueTask<ChunkManifest> GetManifestAsync(
        string chunkId,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(
            _package.Chunks.TryGetValue(chunkId, out var manifest)
                ? manifest
                : throw new KeyNotFoundException($"Unknown route chunk '{chunkId}'."));
    }

    public async ValueTask<ReadOnlyMemory<byte>> ReadChunkAsync(
        string chunkId,
        CancellationToken cancellationToken = default)
    {
        var result = await ReadAndValidateChunkAsync(chunkId, cancellationToken);
        return result.Bytes;
    }

    public async ValueTask<RouteChunkContent> LoadChunkAsync(
        string chunkId,
        CancellationToken cancellationToken = default)
    {
        var result = await ReadAndValidateChunkAsync(chunkId, cancellationToken);
        return result.Content;
    }

    private async ValueTask<(ReadOnlyMemory<byte> Bytes, RouteChunkContent Content)>
        ReadAndValidateChunkAsync(string chunkId, CancellationToken cancellationToken)
    {
        var manifest = await GetManifestAsync(chunkId, cancellationToken);
        var path = ResolvePath(manifest.RelativePath);
        byte[] bytes;
        try
        {
            await using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 1,
                FileOptions.Asynchronous | FileOptions.SequentialScan);
            if (stream.Length >= FlatBufferRouteChunkContent.MaximumChunkBytes ||
                manifest.ByteCount == 0 ||
                (ulong)stream.Length != manifest.ByteCount)
            {
                throw new InvalidDataException($"Route chunk '{chunkId}' has an invalid byte count.");
            }
            bytes = new byte[checked((int)stream.Length)];
            await stream.ReadExactlyAsync(bytes, cancellationToken);
            var trailingByte = new byte[1];
            if (await stream.ReadAsync(trailingByte, cancellationToken) != 0)
            {
                throw new InvalidDataException(
                    $"Route chunk '{chunkId}' changed while it was being read.");
            }
        }
        catch (FileNotFoundException)
        {
            throw new FileNotFoundException($"Route chunk '{chunkId}' is missing.", path);
        }

        var digest = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        if (!string.Equals(digest, manifest.ContentHash, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Route chunk '{chunkId}' failed SHA-256 verification.");
        }
        var content = FlatBufferRouteChunkContent.Load(
            bytes,
            manifest,
            _package.Graph.ContentVersion);
        return (bytes, content);
    }

    private string ResolvePath(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathRooted(relativePath) ||
            relativePath.Contains('\\') || relativePath.Contains(':') ||
            relativePath.Split('/').Any(segment =>
                string.IsNullOrEmpty(segment) || segment is "." or ".."))
        {
            throw new InvalidDataException("Route chunk path is unsafe.");
        }
        var fullPath = Path.GetFullPath(Path.Combine(_packageDirectory, relativePath));
        var prefix = _packageDirectory.EndsWith(Path.DirectorySeparatorChar)
            ? _packageDirectory
            : _packageDirectory + Path.DirectorySeparatorChar;
        var comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!fullPath.StartsWith(prefix, comparison))
        {
            throw new InvalidDataException("Route chunk path escapes the package directory.");
        }
        var current = _packageDirectory;
        foreach (var segment in relativePath.Split('/'))
        {
            current = Path.Combine(current, segment);
            if (!File.Exists(current) && !Directory.Exists(current))
            {
                break;
            }
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException("Route chunk path contains a symbolic link or junction.");
            }
        }
        return fullPath;
    }
}
