using System.Text.Json.Nodes;

namespace Cannonball.Core.Saves;

public interface IRunSaveMigrator
{
    int FromVersion { get; }
    int ToVersion { get; }
    JsonObject Migrate(JsonObject save);
}

public sealed class RunSaveMigrationPipeline
{
    private readonly IReadOnlyDictionary<int, IRunSaveMigrator> _migrators;

    public RunSaveMigrationPipeline(IEnumerable<IRunSaveMigrator>? migrators = null)
    {
        _migrators = (migrators ?? [])
            .ToDictionary(migrator => migrator.FromVersion);
        if (_migrators.Values.Any(migrator => migrator.ToVersion <= migrator.FromVersion))
        {
            throw new ArgumentException("Save migrators must advance the schema version.", nameof(migrators));
        }
    }

    public JsonObject Apply(JsonObject save)
    {
        var version = ReadVersion(save);
        if (version > RunSave.CurrentSchemaVersion)
        {
            throw new InvalidDataException(
                $"Save schema {version} is newer than supported schema {RunSave.CurrentSchemaVersion}.");
        }

        var migrated = save;
        while (version < RunSave.CurrentSchemaVersion)
        {
            if (!_migrators.TryGetValue(version, out var migrator))
            {
                throw new InvalidDataException($"No save migration is registered from schema {version}.");
            }

            migrated = migrator.Migrate((JsonObject)migrated.DeepClone());
            var nextVersion = ReadVersion(migrated);
            if (nextVersion != migrator.ToVersion)
            {
                throw new InvalidDataException(
                    $"Migrator {migrator.FromVersion}->{migrator.ToVersion} emitted schema {nextVersion}.");
            }
            version = nextVersion;
        }

        return migrated;
    }

    private static int ReadVersion(JsonObject save) =>
        save["schemaVersion"]?.GetValue<int>()
        ?? throw new InvalidDataException("Save is missing schemaVersion.");
}
