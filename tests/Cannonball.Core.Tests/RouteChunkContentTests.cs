using System.Security.Cryptography;
using Cannonball.Content;
using Cannonball.Core.Content;
using Google.FlatBuffers;

namespace Cannonball.Core.Tests;

public sealed class RouteChunkContentTests
{
    [Fact]
    public async Task VerifiedSourceLoadsMatchingChunkSamples()
    {
        var fixture = CreateFixture();
        try
        {
            var chunk = await fixture.Source.LoadChunkAsync("chunk-1");

            Assert.Equal("edge-1", chunk.EdgeId);
            Assert.Equal(2, chunk.Samples.Count);
            var sample = chunk.Samples[0];
            Assert.Equal(1_602.5f, sample.ElevationMeters);
            Assert.Equal(0.03125f, sample.Grade);
        }
        finally
        {
            Directory.Delete(fixture.Directory, recursive: true);
        }
    }

    [Fact]
    public void VerifiedSourceSynchronouslyLoadsInitialChunk()
    {
        var fixture = CreateFixture();
        try
        {
            var chunk = fixture.Source.LoadChunk("chunk-1");

            Assert.Equal("edge-1", chunk.EdgeId);
            Assert.Equal(2, chunk.Samples.Count);
        }
        finally
        {
            Directory.Delete(fixture.Directory, recursive: true);
        }
    }

    [Fact]
    public async Task VerifiedMemorySourceEnforcesManifestHashBeforeLoading()
    {
        var chunkBytes = CreateChunkBytes();
        var package = FlatBufferRouteContent.Load(CreateRootBytes(chunkBytes));
        var source = new VerifiedMemoryChunkSource(
            package,
            new Dictionary<string, byte[]> { ["chunk-1"] = chunkBytes });

        var chunk = await source.LoadChunkAsync("chunk-1");
        chunkBytes[^1] ^= 0xff;
        var stillValid = source.LoadChunk("chunk-1");

        Assert.Equal("edge-1", chunk.EdgeId);
        Assert.Equal(chunk.Id, stillValid.Id);
        Assert.Equal(chunk.Samples.ToArray(), stillValid.Samples.ToArray());
    }

    [Fact]
    public async Task VerifiedMemorySourceRejectsCorruptPayload()
    {
        var chunkBytes = CreateChunkBytes();
        var package = FlatBufferRouteContent.Load(CreateRootBytes(chunkBytes));
        chunkBytes[^1] ^= 0xff;
        var source = new VerifiedMemoryChunkSource(
            package,
            new Dictionary<string, byte[]> { ["chunk-1"] = chunkBytes });

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => source.LoadChunkAsync("chunk-1").AsTask());

        Assert.Contains("SHA-256", error.Message);
    }

    [Theory]
    [InlineData("uppercase-hash")]
    [InlineData("unsafe-path")]
    [InlineData("zero-byte-count")]
    public void SchemaThreeRejectsInvalidChunkManifests(string invalidField)
    {
        var chunkBytes = CreateChunkBytes();
        var rootBytes = CreateRootBytes(
            chunkBytes,
            manifest =>
            {
                switch (invalidField)
                {
                    case "uppercase-hash":
                        manifest.ContentHash = manifest.ContentHash.ToUpperInvariant();
                        break;
                    case "unsafe-path":
                        manifest.RelativePath = "chunks\\chunk-1.cbck";
                        break;
                    case "zero-byte-count":
                        manifest.ByteCount = 0;
                        break;
                }
            });

        Assert.Throws<InvalidDataException>(() => FlatBufferRouteContent.Load(rootBytes));
    }

    [Theory]
    [InlineData("empty")]
    [InlineData("gap")]
    [InlineData("duplicate")]
    public void SchemaThreeRejectsIncoherentChunkCoverage(string layout)
    {
        var chunkBytes = CreateChunkBytes();
        var rootBytes = CreateRootBytes(
            chunkBytes,
            manifest =>
            {
                if (layout == "gap")
                {
                    manifest.StartMeters = 1;
                }
            },
            graph =>
            {
                graph.Edges[0].ChunkIds = layout switch
                {
                    "empty" => [],
                    "duplicate" => ["chunk-1", "chunk-1"],
                    _ => ["chunk-1"],
                };
            });

        Assert.Throws<InvalidDataException>(() => FlatBufferRouteContent.Load(rootBytes));
    }

    [Fact]
    public async Task ChunkFileLengthMustMatchManifestBeforeParsing()
    {
        var fixture = CreateFixture();
        try
        {
            await using (var stream = new FileStream(fixture.ChunkPath, FileMode.Append))
            {
                stream.WriteByte(0);
            }

            var error = await Assert.ThrowsAsync<InvalidDataException>(
                () => fixture.Source.LoadChunkAsync("chunk-1").AsTask());
            Assert.Contains("byte count", error.Message);
        }
        finally
        {
            Directory.Delete(fixture.Directory, recursive: true);
        }
    }

    [Theory]
    [InlineData("missing-start")]
    [InlineData("missing-end")]
    [InlineData("duplicate-distance")]
    [InlineData("non-finite")]
    public async Task InvalidSampleSequencesFailClosed(string invalidSequence)
    {
        var fixture = CreateFixture(
            chunk =>
            {
                switch (invalidSequence)
                {
                    case "missing-start":
                        chunk.Samples[0].DistanceMeters = 1;
                        break;
                    case "missing-end":
                        chunk.Samples[^1].DistanceMeters = 24;
                        break;
                    case "duplicate-distance":
                        chunk.Samples[^1].DistanceMeters = 0;
                        break;
                    case "non-finite":
                        chunk.Samples[^1].ProjectedXMeters = double.NaN;
                        break;
                }
            });
        try
        {
            await Assert.ThrowsAsync<InvalidDataException>(
                () => fixture.Source.LoadChunkAsync("chunk-1").AsTask());
        }
        finally
        {
            Directory.Delete(fixture.Directory, recursive: true);
        }
    }

    [Fact]
    public async Task MissingAndCorruptChunksFailBeforeUse()
    {
        var missing = CreateFixture();
        try
        {
            File.Delete(missing.ChunkPath);
            await Assert.ThrowsAsync<FileNotFoundException>(
                () => missing.Source.LoadChunkAsync("chunk-1").AsTask());
        }
        finally
        {
            Directory.Delete(missing.Directory, recursive: true);
        }

        var corrupt = CreateFixture();
        try
        {
            var bytes = File.ReadAllBytes(corrupt.ChunkPath);
            bytes[^1] ^= 0xff;
            File.WriteAllBytes(corrupt.ChunkPath, bytes);
            var error = await Assert.ThrowsAsync<InvalidDataException>(
                () => corrupt.Source.LoadChunkAsync("chunk-1").AsTask());
            Assert.Contains("SHA-256", error.Message);
        }
        finally
        {
            Directory.Delete(corrupt.Directory, recursive: true);
        }
    }

    [Fact]
    public async Task UnsafeChunkPathFailsClosed()
    {
        var fixture = CreateFixture();
        try
        {
            var manifest = fixture.Package.Chunks["chunk-1"] with
            {
                RelativePath = "../escape.cbck",
            };
            var package = fixture.Package with
            {
                Chunks = new Dictionary<string, Cannonball.Core.Routes.ChunkManifest>
                {
                    [manifest.Id] = manifest,
                },
            };
            var source = new VerifiedFileChunkSource(package, fixture.Directory);

            await Assert.ThrowsAsync<InvalidDataException>(
                () => source.LoadChunkAsync("chunk-1").AsTask());
        }
        finally
        {
            Directory.Delete(fixture.Directory, recursive: true);
        }
    }

    [Fact]
    public async Task SymbolicLinkChunkPathFailsClosed()
    {
        var fixture = CreateFixture();
        var external = Path.Combine(Path.GetTempPath(), $"cannonball-external-{Guid.NewGuid():N}.cbck");
        try
        {
            File.Move(fixture.ChunkPath, external);
            try
            {
                File.CreateSymbolicLink(fixture.ChunkPath, external);
            }
            catch (Exception exception) when (
                exception is UnauthorizedAccessException or PlatformNotSupportedException)
            {
                return;
            }

            var error = await Assert.ThrowsAsync<InvalidDataException>(
                () => fixture.Source.LoadChunkAsync("chunk-1").AsTask());
            Assert.Contains("symbolic link", error.Message);
        }
        finally
        {
            Directory.Delete(fixture.Directory, recursive: true);
            File.Delete(external);
        }
    }

    private static ChunkFixture CreateFixture(Action<RouteChunkBufferT>? configureChunk = null)
    {
        var chunkBytes = CreateChunkBytes(configureChunk);
        var package = FlatBufferRouteContent.Load(CreateRootBytes(chunkBytes));
        var directory = Directory.CreateTempSubdirectory("cannonball-chunk-").FullName;
        var chunkDirectory = Path.Combine(directory, "chunks");
        Directory.CreateDirectory(chunkDirectory);
        var chunkPath = Path.Combine(chunkDirectory, "chunk-1.cbck");
        File.WriteAllBytes(chunkPath, chunkBytes);
        return new ChunkFixture(
            directory,
            chunkPath,
            package,
            new VerifiedFileChunkSource(package, directory));
    }

    private static byte[] CreateChunkBytes(Action<RouteChunkBufferT>? configure = null)
    {
        var chunkData = new RouteChunkBufferT
        {
            SchemaVersion = 1,
            ContentVersion = "route-v3-fixture",
            Id = "chunk-1",
            EdgeId = "edge-1",
            StartMeters = 0,
            EndMeters = 25,
            Samples =
            [
                new ChunkRouteSampleT
                {
                    DistanceMeters = 0,
                    ElevationMeters = 1_602.5f,
                    Grade = 0.03125f,
                    ProjectedTangentY = 1,
                },
                new ChunkRouteSampleT
                {
                    DistanceMeters = 25,
                    ElevationMeters = 1_603.0f,
                    Grade = 0.03125f,
                    ProjectedYMeters = 25,
                    ProjectedTangentY = 1,
                },
            ],
        };
        configure?.Invoke(chunkData);
        var chunkBuilder = new FlatBufferBuilder(4_096);
        var chunkRoot = RouteChunkBuffer.Pack(chunkBuilder, chunkData);
        RouteChunkBuffer.FinishRouteChunkBufferBuffer(chunkBuilder, chunkRoot);
        return chunkBuilder.SizedByteArray();
    }

    private static byte[] CreateRootBytes(
        byte[] chunkBytes,
        Action<ChunkManifestDataT>? configureManifest = null,
        Action<RouteGraphBufferT>? configureGraph = null)
    {
        const string version = "route-v3-fixture";
        var chunkHash = Convert.ToHexString(SHA256.HashData(chunkBytes)).ToLowerInvariant();
        var manifest = new ChunkManifestDataT
        {
            Id = "chunk-1",
            EdgeId = "edge-1",
            StartMeters = 0,
            EndMeters = 25,
            ContentHash = chunkHash,
            RelativePath = "chunks/chunk-1.cbck",
            ByteCount = (ulong)chunkBytes.Length,
            ProbableBranchChunkIds = [],
        };
        configureManifest?.Invoke(manifest);
        var graphData = new RouteGraphBufferT
        {
            SchemaVersion = 3,
            ContentVersion = version,
            Nodes =
            [
                new RouteNodeDataT { Id = "west", Kind = "route", OutgoingEdgeIds = ["edge-1"] },
                new RouteNodeDataT { Id = "east", Kind = "route", OutgoingEdgeIds = [] },
            ],
            Edges =
            [
                new RouteEdgeDataT
                {
                    Id = "edge-1",
                    FromNodeId = "west",
                    ToNodeId = "east",
                    LengthMeters = 25,
                    LaneCount = 2,
                    ChunkIds = ["chunk-1"],
                    Samples = [],
                },
            ],
            Chunks =
            [
                manifest,
            ],
            Provenance = new SourceProvenanceDataT
            {
                SourceId = "source",
                Publisher = "publisher",
                SourceUrl = "https://example.gov/source",
                ArtifactSha256 = new string('a', 64),
                AcquisitionLockSha256 = new string('b', 64),
            },
            SpatialReference = new SpatialReferenceDataT
            {
                RouteCrs = "EPSG:5070",
                ElevationCrs = "EPSG:4269",
                HorizontalDatum = "NAD83",
                VerticalDatum = "NAVD88",
                ElevationUnits = "meters",
                ElevationProductId = "product",
                ElevationProductTitle = "title",
                ElevationProductResolution = "1/3 arc-second",
                ElevationArtifactSha256 = new string('c', 64),
            },
        };
        configureGraph?.Invoke(graphData);
        var rootBuilder = new FlatBufferBuilder(8_192);
        var root = RouteGraphBuffer.Pack(rootBuilder, graphData);
        RouteGraphBuffer.FinishRouteGraphBufferBuffer(rootBuilder, root);
        return rootBuilder.SizedByteArray();
    }

    private sealed record ChunkFixture(
        string Directory,
        string ChunkPath,
        RouteContentPackage Package,
        VerifiedFileChunkSource Source);
}
