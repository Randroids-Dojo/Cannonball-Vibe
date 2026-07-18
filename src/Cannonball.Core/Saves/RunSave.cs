using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Nodes;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;

namespace Cannonball.Core.Saves;

public sealed record LocalVehicleState(
    double PositionX,
    double PositionY,
    double PositionZ,
    double VelocityX,
    double VelocityY,
    double VelocityZ,
    double AngularVelocityX,
    double AngularVelocityY,
    double AngularVelocityZ);

public sealed record ReplayMarker(double ElapsedSeconds, RoutePosition Position, string Kind);

public sealed record RunSave(
    int SchemaVersion,
    string ContentVersion,
    string ContentChecksum,
    DateTimeOffset SavedAtUtc,
    RunState Run,
    LocalVehicleState LocalVehicle,
    IReadOnlyList<ReplayMarker> ReplayMarkers)
{
    public const int CurrentSchemaVersion = 2;

    public static string ComputeContentChecksum(string contentVersion)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(contentVersion));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}

public interface IRunStateRepository
{
    ValueTask SaveAsync(RunSave save, CancellationToken cancellationToken = default);

    ValueTask<RunSave?> LoadAsync(CancellationToken cancellationToken = default);
}

public sealed class JsonRunStateRepository : IRunStateRepository
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
    };

    private readonly string _path;
    private readonly string _expectedContentVersion;
    private readonly RunSaveMigrationPipeline _migrations;

    public JsonRunStateRepository(
        string path,
        string expectedContentVersion,
        IEnumerable<IRunSaveMigrator>? migrators = null)
    {
        _path = path;
        _expectedContentVersion = expectedContentVersion;
        _migrations = new RunSaveMigrationPipeline(migrators);
    }

    public async ValueTask SaveAsync(RunSave save, CancellationToken cancellationToken = default)
    {
        Validate(save);
        var directory = Path.GetDirectoryName(_path);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var temporaryPath = $"{_path}.{Guid.NewGuid():N}.tmp";
        try
        {
            await using (var stream = new FileStream(
                temporaryPath,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 16 * 1024,
                FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await JsonSerializer.SerializeAsync(stream, save, SerializerOptions, cancellationToken);
                await stream.FlushAsync(cancellationToken);
                stream.Flush(flushToDisk: true);
            }

            File.Move(temporaryPath, _path, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                File.Delete(temporaryPath);
            }
        }
    }

    public async ValueTask<RunSave?> LoadAsync(CancellationToken cancellationToken = default)
    {
        if (!File.Exists(_path))
        {
            return null;
        }

        await using var stream = File.OpenRead(_path);
        var document = await JsonNode.ParseAsync(
            stream,
            documentOptions: default,
            cancellationToken: cancellationToken)
            ?? throw new InvalidDataException("The run save was empty.");
        var root = document as JsonObject
            ?? throw new InvalidDataException("The run save root must be an object.");
        var save = _migrations.Apply(root).Deserialize<RunSave>(SerializerOptions)
            ?? throw new InvalidDataException("The run save was empty.");
        Validate(save);
        return save;
    }

    private void Validate(RunSave save)
    {
        if (save.SchemaVersion != RunSave.CurrentSchemaVersion)
        {
            throw new InvalidDataException(
                $"Unsupported save schema {save.SchemaVersion}; expected {RunSave.CurrentSchemaVersion}.");
        }

        if (!string.Equals(save.ContentVersion, _expectedContentVersion, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Save content version '{save.ContentVersion}' does not match '{_expectedContentVersion}'.");
        }

        var expectedChecksum = RunSave.ComputeContentChecksum(save.ContentVersion);
        if (!string.Equals(save.ContentChecksum, expectedChecksum, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("Save content checksum is invalid.");
        }
    }
}
