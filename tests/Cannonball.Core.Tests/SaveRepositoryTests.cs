using Cannonball.Core.Content;
using Cannonball.Core.Routes;
using Cannonball.Core.Runs;
using Cannonball.Core.Saves;
using System.Text.Json;
using System.Text.Json.Serialization;
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
        AssertNavigationEqual(expected.Run.Navigation, actual.Run.Navigation);
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

    [Fact]
    public async Task SchemaOneSaveMigratesWithExplicitEmptyNavigationState()
    {
        var path = Path.Combine(_directory, "schema-one-run.json");
        var writer = new JsonRunStateRepository(path, "graybox-v1");
        await writer.SaveAsync(CreateSave());
        var root = JsonNode.Parse(await File.ReadAllTextAsync(path))!.AsObject();
        root["schemaVersion"] = 1;
        root["run"]!.AsObject().Remove("navigation");
        await File.WriteAllTextAsync(path, root.ToJsonString());

        var migrated = await writer.LoadAsync();

        Assert.NotNull(migrated);
        Assert.Equal(RunSave.CurrentSchemaVersion, migrated.SchemaVersion);
        AssertNavigationEqual(RouteNavigationState.Empty, migrated.Run.Navigation);
    }

    [Fact]
    public async Task SchemaTwoSaveMigratesOnlyAfterValidatingLegacyChecksum()
    {
        var path = Path.Combine(_directory, "schema-two-run.json");
        var identity = new RoutePackageIdentity("graybox-v1", new string('b', 64));
        var repository = new JsonRunStateRepository(path, identity);
        var root = JsonSerializer.SerializeToNode(CreateSave(), SerializerOptions)!.AsObject();
        root["schemaVersion"] = 2;
        root["contentChecksum"] = RunSave.ComputeContentChecksum("graybox-v1");
        Directory.CreateDirectory(_directory);
        await File.WriteAllTextAsync(path, root.ToJsonString());

        var migrated = await repository.LoadAsync();

        Assert.NotNull(migrated);
        Assert.Equal(RunSave.CurrentSchemaVersion, migrated.SchemaVersion);
        Assert.Equal(identity.PackageChecksum, migrated.ContentChecksum);
    }

    [Fact]
    public async Task CorruptPrimaryRecoversLastDurableSaveFromBackup()
    {
        var path = Path.Combine(_directory, "recover-run.json");
        var repository = new JsonRunStateRepository(path, "graybox-v1");
        var first = CreateSave() with { SavedAtUtc = DateTimeOffset.UnixEpoch };
        var second = CreateSave() with { SavedAtUtc = DateTimeOffset.UnixEpoch.AddSeconds(1) };
        await repository.SaveAsync(first);
        await repository.SaveAsync(second);
        await File.WriteAllTextAsync(path, "{ interrupted");

        var recovered = await repository.LoadAsync();

        Assert.NotNull(recovered);
        Assert.Equal(first.SavedAtUtc, recovered.SavedAtUtc);
        Assert.True(repository.LastLoadRecovery?.UsedBackup);
        Assert.False(string.IsNullOrWhiteSpace(repository.LastLoadRecovery?.PrimaryFailure));

        var replacement = CreateSave() with
        {
            SavedAtUtc = DateTimeOffset.UnixEpoch.AddSeconds(2),
        };
        await repository.SaveAsync(replacement);
        await File.WriteAllTextAsync(path, "{ interrupted again");
        var recoveredAgain = await repository.LoadAsync();

        Assert.NotNull(recoveredAgain);
        Assert.Equal(first.SavedAtUtc, recoveredAgain.SavedAtUtc);
    }

    [Fact]
    public async Task CorruptPrimaryWithoutBackupFailsActionably()
    {
        var path = Path.Combine(_directory, "corrupt-run.json");
        Directory.CreateDirectory(_directory);
        await File.WriteAllTextAsync(path, "{ corrupt");
        var repository = new JsonRunStateRepository(path, "graybox-v1");

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => repository.LoadAsync().AsTask());

        Assert.Contains("no backup exists", error.Message);
        Assert.Contains("primary run save", error.Message);
    }

    [Fact]
    public async Task InterruptedTemporaryWriteCannotReplaceDurablePrimary()
    {
        var path = Path.Combine(_directory, "interrupted-run.json");
        var repository = new JsonRunStateRepository(path, "graybox-v1");
        var expected = CreateSave();
        await repository.SaveAsync(expected);
        await File.WriteAllTextAsync($"{path}.orphan.tmp", "{ incomplete");

        var actual = await repository.LoadAsync();

        Assert.NotNull(actual);
        Assert.Equal(
            JsonSerializer.Serialize(expected, SerializerOptions),
            JsonSerializer.Serialize(actual, SerializerOptions));
        Assert.False(repository.LastLoadRecovery?.UsedBackup);
    }

    [Fact]
    public async Task SeededSavePointsRoundTripEquivalent()
    {
        var cases = int.TryParse(
            Environment.GetEnvironmentVariable("CANNONBALL_RESUME_FUZZ_CASES"),
            out var requested)
            ? requested
            : 64;
        Assert.InRange(cases, 1, 100_000);
        var path = Path.Combine(_directory, "fuzz-run.json");
        var repository = new JsonRunStateRepository(path, "graybox-v1");
        var random = new Random(20_260_718);
        for (var index = 0; index < cases; index++)
        {
            var expected = CreateSeededSave(random, index);
            await repository.SaveAsync(expected);
            var actual = await repository.LoadAsync();

            Assert.NotNull(actual);
            Assert.Equal(
                JsonSerializer.Serialize(expected, SerializerOptions),
                JsonSerializer.Serialize(actual, SerializerOptions));
        }
    }

    [Fact]
    public void PackageIdentityCoversRootAndEveryChunkHash()
    {
        var edge = new RouteEdge(
            "edge",
            "start",
            "end",
            100,
            1,
            30,
            [],
            [],
            "test",
            "test",
            ["chunk"]);
        var graph = new InMemoryRouteGraph(
            "package-v1",
            [
                new RouteNode("start", default, "route", [edge.Id]),
                new RouteNode("end", default, "route", []),
            ],
            [edge]);
        RouteContentPackage Package(string rootHash, string chunkHash) => new(
            graph,
            new Dictionary<string, ChunkManifest>
            {
                ["chunk"] = new ChunkManifest(
                    "chunk",
                    edge.Id,
                    0,
                    100,
                    chunkHash,
                    "chunks/chunk.cbck",
                    default,
                    [])
                {
                    ByteCount = 128,
                },
            })
        {
            RootContentHash = rootHash,
        };

        var original = RunSave.ComputePackageIdentity(
            Package(new string('a', 64), new string('b', 64)));
        var changedRoot = RunSave.ComputePackageIdentity(
            Package(new string('c', 64), new string('b', 64)));
        var changedChunk = RunSave.ComputePackageIdentity(
            Package(new string('a', 64), new string('d', 64)));

        Assert.NotEqual(original.PackageChecksum, changedRoot.PackageChecksum);
        Assert.NotEqual(original.PackageChecksum, changedChunk.PackageChecksum);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }

    private static void AssertNavigationEqual(
        RouteNavigationState expected,
        RouteNavigationState actual)
    {
        Assert.Equal(expected.SelectedPlanId, actual.SelectedPlanId);
        Assert.Equal(expected.ActiveConnectorId, actual.ActiveConnectorId);
        Assert.Equal(expected.BranchStream.DecisionEdgeId, actual.BranchStream.DecisionEdgeId);
        Assert.Equal(
            expected.BranchStream.PrewarmedChunkIds.ToArray(),
            actual.BranchStream.PrewarmedChunkIds.ToArray());
        Assert.Equal(
            expected.BranchStream.SelectedChunkIds.ToArray(),
            actual.BranchStream.SelectedChunkIds.ToArray());
    }

    private static RunSave CreateSave()
    {
        var position = new RoutePosition("graybox-25mi", 12_345, 1, 0.1, 0.01)
        {
            StableLaneId = "legacy:graybox-25mi:lane:1",
        };
        var run = new RunState(
            42,
            position,
            [position.EdgeId],
            500,
            10_000,
            new VehicleCondition(70, 1, 1, 1, 0),
            new EnforcementState(0, 0, "clear", 0),
            AssistProfile.Balanced)
        {
            Navigation = new RouteNavigationState(
                "transfer",
                "connector-transfer",
                new BranchStreamSnapshot(
                    "decision-edge",
                    ["chunk-through", "chunk-transfer"],
                    ["chunk-transfer"])),
        };
        return new RunSave(
            RunSave.CurrentSchemaVersion,
            "graybox-v1",
            RunSave.ComputeContentChecksum("graybox-v1"),
            DateTimeOffset.UtcNow,
            run,
            new LocalVehicleState(0, 1, 0, 0, 0, -50, 0, 0, 0),
            [new ReplayMarker(500, position, "autosave")]);
    }

    private static RunSave CreateSeededSave(Random random, int index)
    {
        var edgeId = $"edge-{random.Next(1, 40):D2}";
        var laneIndex = random.Next(0, 4);
        var position = new RoutePosition(
            edgeId,
            random.NextDouble() * 20_000,
            laneIndex,
            random.NextDouble() * 7.2 - 3.6,
            random.NextDouble() * 0.1 - 0.05)
        {
            StableLaneId = $"{edgeId}:lane:{laneIndex}",
        };
        var run = new RunState(
            (ulong)random.NextInt64(0, long.MaxValue),
            position,
            [edgeId, $"edge-{random.Next(40, 80):D2}"],
            random.NextDouble() * 100_000,
            random.NextDouble() * 250_000,
            new VehicleCondition(
                random.NextDouble() * 100,
                random.NextDouble(),
                random.NextDouble(),
                random.NextDouble(),
                random.NextDouble()),
            new EnforcementState(
                random.NextDouble(),
                random.NextDouble(),
                index % 3 == 0 ? "clear" : "aware",
                random.NextDouble() * 60),
            (AssistProfile)(index % 3))
        {
            Navigation = new RouteNavigationState(
                $"plan-{index % 7}",
                $"connector-{index % 13}",
                new BranchStreamSnapshot(
                    edgeId,
                    [$"prewarm-{index % 5}"],
                    [$"selected-{index % 11}"])),
            WorldStream = new WorldStreamSnapshot(
                random.NextDouble() * 50_000,
                random.NextDouble() * 100,
                random.NextDouble() * 50_000,
                random.NextDouble() * 20_000,
                random.Next(0, 100),
                [$"chunk-{index % 17}", $"chunk-{(index + 1) % 17}"],
                [$"chunk-{index % 17}"]),
        };
        return new RunSave(
            RunSave.CurrentSchemaVersion,
            "graybox-v1",
            RunSave.ComputeContentChecksum("graybox-v1"),
            DateTimeOffset.UnixEpoch.AddMilliseconds(index),
            run,
            new LocalVehicleState(
                random.NextDouble() * 2_000 - 1_000,
                random.NextDouble() * 20,
                random.NextDouble() * 2_000 - 1_000,
                random.NextDouble() * 100,
                random.NextDouble() * 10,
                random.NextDouble() * 100,
                random.NextDouble(),
                random.NextDouble(),
                random.NextDouble())
            {
                RotationX = random.NextDouble(),
                RotationY = random.NextDouble(),
                RotationZ = random.NextDouble(),
                RotationW = random.NextDouble(),
            },
            [new ReplayMarker(run.ElapsedSeconds, position, "fuzz")]);
    }

    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
    };

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
