using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Saves;
using System.Text.Json.Nodes;

namespace Cannonball.Core.Tests;

public sealed class SaveRepositoryTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), $"cannonball-tests-{Guid.NewGuid():N}");

    [Fact]
    public async Task SaveRoundTripPreservesAuthoritativePosition()
    {
        var path = Path.Combine(_directory, "run.json");
        var repository = new JsonRunStateRepository(path, "graybox-v1");
        var expected = CreateSave();

        await repository.SaveAsync(expected);
        var actual = await repository.LoadAsync();

        Assert.NotNull(actual);
        Assert.Equal(expected.Run.Position, actual.Run.Position);
        Assert.Equal(expected.LocalVehicle, actual.LocalVehicle);
    }

    [Fact]
    public async Task ContentVersionMismatchIsRejected()
    {
        var path = Path.Combine(_directory, "run.json");
        var writer = new JsonRunStateRepository(path, "graybox-v1");
        await writer.SaveAsync(CreateSave());
        var reader = new JsonRunStateRepository(path, "continental-v2");

        await Assert.ThrowsAsync<InvalidDataException>(
            async () => await reader.LoadAsync());
    }

    [Fact]
    public async Task RegisteredMigrationUpgradesOlderSchema()
    {
        var path = Path.Combine(_directory, "migrated-run.json");
        var writer = new JsonRunStateRepository(path, "graybox-v1");
        await writer.SaveAsync(CreateSave());
        var root = JsonNode.Parse(await File.ReadAllTextAsync(path))!.AsObject();
        root["schemaVersion"] = 0;
        await File.WriteAllTextAsync(path, root.ToJsonString());
        var reader = new JsonRunStateRepository(
            path,
            "graybox-v1",
            [new SchemaZeroToOneMigrator()]);

        var migrated = await reader.LoadAsync();

        Assert.NotNull(migrated);
        Assert.Equal(RunSave.CurrentSchemaVersion, migrated.SchemaVersion);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }

    private static RunSave CreateSave()
    {
        var position = new RoutePosition("graybox-25mi", 12_345, 1, 0.1, 0.01);
        var run = new RunState(
            42,
            position,
            [position.EdgeId],
            500,
            10_000,
            new VehicleCondition(70, 1, 1, 1, 0),
            new EnforcementState(0, 0, "clear", 0),
            AssistProfile.Balanced);
        return new RunSave(
            RunSave.CurrentSchemaVersion,
            "graybox-v1",
            RunSave.ComputeContentChecksum("graybox-v1"),
            DateTimeOffset.UtcNow,
            run,
            new LocalVehicleState(0, 1, 0, 0, 0, -50, 0, 0, 0),
            [new ReplayMarker(500, position, "autosave")]);
    }

    private sealed class SchemaZeroToOneMigrator : IRunSaveMigrator
    {
        public int FromVersion => 0;
        public int ToVersion => 1;

        public JsonObject Migrate(JsonObject save)
        {
            save["schemaVersion"] = ToVersion;
            return save;
        }
    }
}
