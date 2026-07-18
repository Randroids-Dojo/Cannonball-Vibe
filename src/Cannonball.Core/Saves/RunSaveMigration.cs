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

    public RunSaveMigrationPipeline(
        RoutePackageIdentity expectedPackage,
        IEnumerable<IRunSaveMigrator>? migrators = null)
    {
        _migrators = (migrators ?? [])
            .Append(new SchemaOneToTwoMigrator())
            .Append(new SchemaTwoToThreeMigrator(expectedPackage))
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

    private sealed class SchemaOneToTwoMigrator : IRunSaveMigrator
    {
        public int FromVersion => 1;
        public int ToVersion => 2;

        public JsonObject Migrate(JsonObject save)
        {
            var run = save["run"] as JsonObject
                ?? throw new InvalidDataException("Schema-1 save is missing run state.");
            run["navigation"] = new JsonObject
            {
                ["selectedPlanId"] = string.Empty,
                ["activeConnectorId"] = string.Empty,
                ["branchStream"] = new JsonObject
                {
                    ["decisionEdgeId"] = string.Empty,
                    ["prewarmedChunkIds"] = new JsonArray(),
                    ["selectedChunkIds"] = new JsonArray(),
                },
            };
            save["schemaVersion"] = ToVersion;
            return save;
        }
    }

    private sealed class SchemaTwoToThreeMigrator(RoutePackageIdentity expectedPackage)
        : IRunSaveMigrator
    {
        public int FromVersion => 2;
        public int ToVersion => 3;

        public JsonObject Migrate(JsonObject save)
        {
            var contentVersion = save["contentVersion"]?.GetValue<string>()
                ?? throw new InvalidDataException("Schema-2 save is missing contentVersion.");
            var checksum = save["contentChecksum"]?.GetValue<string>()
                ?? throw new InvalidDataException("Schema-2 save is missing contentChecksum.");
            if (!string.Equals(
                    checksum,
                    RunSave.ComputeContentChecksum(contentVersion),
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    "Schema-2 save has an invalid legacy content checksum.");
            }
            if (!string.Equals(
                    contentVersion,
                    expectedPackage.ContentVersion,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"Schema-2 save content version '{contentVersion}' does not match " +
                    $"'{expectedPackage.ContentVersion}'.");
            }
            var run = save["run"] as JsonObject
                ?? throw new InvalidDataException("Schema-2 save is missing run state.");
            run["worldStream"] = new JsonObject
            {
                ["originWorldX"] = 0,
                ["originWorldY"] = 0,
                ["originWorldZ"] = 0,
                ["localOriginRouteMeters"] = 0,
                ["rebaseCount"] = 0,
                ["loadedChunkIds"] = new JsonArray(),
                ["collisionChunkIds"] = new JsonArray(),
            };
            var localVehicle = save["localVehicle"] as JsonObject
                ?? throw new InvalidDataException("Schema-2 save is missing local vehicle state.");
            localVehicle["rotationX"] = 0;
            localVehicle["rotationY"] = 0;
            localVehicle["rotationZ"] = 0;
            localVehicle["rotationW"] = 1;
            save["contentChecksum"] = expectedPackage.PackageChecksum;
            save["schemaVersion"] = ToVersion;
            return save;
        }
    }
}
