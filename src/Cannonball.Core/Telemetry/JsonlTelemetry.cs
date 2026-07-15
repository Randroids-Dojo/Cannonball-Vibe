using System.Text.Json;

namespace Cannonball.Core.Telemetry;

public sealed record TelemetryEvent(
    string Name,
    DateTimeOffset TimestampUtc,
    ulong RunSeed,
    string EdgeId,
    double DistanceMeters,
    IReadOnlyDictionary<string, object?> Properties);

public interface ITelemetrySink : IAsyncDisposable
{
    ValueTask WriteAsync(TelemetryEvent telemetryEvent, CancellationToken cancellationToken = default);
}

public sealed class JsonlTelemetrySink : ITelemetrySink
{
    private static readonly JsonSerializerOptions SerializerOptions = new(JsonSerializerDefaults.Web);
    private readonly StreamWriter _writer;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public JsonlTelemetrySink(string path)
    {
        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        _writer = new StreamWriter(new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.Read));
    }

    public async ValueTask WriteAsync(TelemetryEvent telemetryEvent, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(telemetryEvent.Name);
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            await _writer.WriteLineAsync(
                    JsonSerializer.Serialize(telemetryEvent, SerializerOptions).AsMemory(),
                    cancellationToken)
                .ConfigureAwait(false);
            await _writer.FlushAsync(cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            await _writer.DisposeAsync().ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
            _gate.Dispose();
        }
    }
}
