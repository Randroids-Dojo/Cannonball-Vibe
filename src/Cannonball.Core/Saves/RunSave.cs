using System.Security.Cryptography;
using System.Buffers.Binary;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Nodes;
using Cannonball.Core.Content;
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
    double AngularVelocityZ)
{
    public double RotationX { get; init; }
    public double RotationY { get; init; }
    public double RotationZ { get; init; }
    public double RotationW { get; init; } = 1;
}

public sealed record ReplayMarker(double ElapsedSeconds, RoutePosition Position, string Kind);

public sealed record RoutePackageIdentity(string ContentVersion, string PackageChecksum);

public sealed record RunSaveLoadRecovery(
    bool UsedBackup,
    string SourcePath,
    string? PrimaryFailure)
{
    public static RunSaveLoadRecovery None(string sourcePath) =>
        new(false, sourcePath, null);
}

public sealed record RunSave(
    int SchemaVersion,
    string ContentVersion,
    string ContentChecksum,
    DateTimeOffset SavedAtUtc,
    RunState Run,
    LocalVehicleState LocalVehicle,
    IReadOnlyList<ReplayMarker> ReplayMarkers)
{
    public const int CurrentSchemaVersion = 3;

    public static string ComputeContentChecksum(string contentVersion)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(contentVersion));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }

    public static RoutePackageIdentity ComputePackageIdentity(RouteContentPackage package)
    {
        ArgumentNullException.ThrowIfNull(package);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        Append(hash, "cannonball-route-package-v1");
        Append(hash, package.Graph.ContentVersion);
        Append(hash, package.RootContentHash);
        if (package.Metadata is { } metadata)
        {
            Append(hash, metadata.SourceArtifactSha256);
            Append(hash, metadata.AcquisitionLockSha256);
            Append(hash, metadata.ElevationArtifactSha256);
        }
        foreach (var manifest in package.Chunks.Values
                     .OrderBy(value => value.Id, StringComparer.Ordinal))
        {
            Append(hash, manifest.Id);
            Append(hash, manifest.EdgeId);
            Append(hash, manifest.RelativePath);
            Append(hash, manifest.ContentHash);
            Append(hash, manifest.ByteCount.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }
        return new RoutePackageIdentity(
            package.Graph.ContentVersion,
            Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant());
    }

    private static void Append(IncrementalHash hash, string value)
    {
        var bytes = Encoding.UTF8.GetBytes(value ?? string.Empty);
        Span<byte> length = stackalloc byte[sizeof(int)];
        BinaryPrimitives.WriteInt32LittleEndian(length, bytes.Length);
        hash.AppendData(length);
        hash.AppendData(bytes);
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
    private readonly string _backupPath;
    private readonly RoutePackageIdentity _expectedPackage;
    private readonly RunSaveMigrationPipeline _migrations;

    public RunSaveLoadRecovery? LastLoadRecovery { get; private set; }

    public JsonRunStateRepository(
        string path,
        string expectedContentVersion,
        IEnumerable<IRunSaveMigrator>? migrators = null)
        : this(
            path,
            new RoutePackageIdentity(
                expectedContentVersion,
                RunSave.ComputeContentChecksum(expectedContentVersion)),
            migrators)
    {
    }

    public JsonRunStateRepository(
        string path,
        RoutePackageIdentity expectedPackage,
        IEnumerable<IRunSaveMigrator>? migrators = null)
    {
        _path = path;
        _backupPath = $"{path}.bak";
        _expectedPackage = expectedPackage;
        _migrations = new RunSaveMigrationPipeline(expectedPackage, migrators);
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

            if (File.Exists(_path))
            {
                try
                {
                    _ = await LoadFileAsync(_path, cancellationToken);
                    File.Copy(_path, _backupPath, overwrite: true);
                }
                catch (Exception error) when (
                    error is JsonException or InvalidDataException or IOException)
                {
                    // Preserve the last known-good backup when the primary is not durable.
                }
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
        LastLoadRecovery = null;
        if (!File.Exists(_path) && !File.Exists(_backupPath))
        {
            return null;
        }

        Exception? primaryFailure = null;
        if (File.Exists(_path))
        {
            try
            {
                var save = await LoadFileAsync(_path, cancellationToken);
                LastLoadRecovery = RunSaveLoadRecovery.None(_path);
                return save;
            }
            catch (Exception error) when (error is JsonException or InvalidDataException or IOException)
            {
                primaryFailure = error;
            }
        }
        if (File.Exists(_backupPath))
        {
            try
            {
                var save = await LoadFileAsync(_backupPath, cancellationToken);
                LastLoadRecovery = new RunSaveLoadRecovery(
                    true,
                    _backupPath,
                    primaryFailure?.Message ?? "The primary save was missing.");
                return save;
            }
            catch (Exception backupFailure) when (
                backupFailure is JsonException or InvalidDataException or IOException)
            {
                throw new InvalidDataException(
                    $"The primary run save could not be loaded ({primaryFailure?.Message ?? "missing"}) " +
                    $"and backup recovery failed ({backupFailure.Message}).",
                    backupFailure);
            }
        }
        throw new InvalidDataException(
            $"The primary run save could not be loaded and no backup exists: " +
            $"{primaryFailure?.Message ?? "file missing"}.",
            primaryFailure);
    }

    private async ValueTask<RunSave> LoadFileAsync(
        string path,
        CancellationToken cancellationToken)
    {
        await using var stream = File.OpenRead(path);
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

        if (!string.Equals(
                save.ContentVersion,
                _expectedPackage.ContentVersion,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Save content version '{save.ContentVersion}' does not match " +
                $"'{_expectedPackage.ContentVersion}'.");
        }

        if (!string.Equals(
                save.ContentChecksum,
                _expectedPackage.PackageChecksum,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("Save content checksum is invalid.");
        }
    }
}
