#!/usr/bin/env node

import { createHash } from "node:crypto";
import { cpSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";

const sha256 = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
const readJson = (path) => JSON.parse(readFileSync(path, "utf8"));
const writeJson = (path, value) => writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
const unixPath = (path) => path.split(sep).join("/");

function filesUnder(root) {
  const found = [];
  function walk(directory) {
    for (const name of readdirSync(directory).sort()) {
      const path = join(directory, name);
      if (lstatSync(path).isSymbolicLink()) throw new Error(`Package must not contain symlinks: ${path}`);
      if (statSync(path).isDirectory()) walk(path);
      else found.push(path);
    }
  }
  walk(root);
  return found;
}

function copyContent(source, destination) {
  const pointerPath = join(source, "current-package.json");
  const pointer = readJson(pointerPath);
  const metadataPath = join(source, pointer.metadata_relative_path);
  const metadata = readJson(metadataPath);
  if (pointer.schema_version !== 1 || metadata.schema_version !== 5) throw new Error("Unexpected fixture schema version.");
  if (pointer.content_version !== metadata.content_version) throw new Error("Fixture pointer and metadata versions differ.");
  const seenChunks = new Set();
  for (const chunk of metadata.chunks) {
    if (seenChunks.has(chunk.chunk_id)) throw new Error(`Duplicate fixture chunk: ${chunk.chunk_id}`);
    seenChunks.add(chunk.chunk_id);
    if (!chunk.relative_path.startsWith(`chunks/${pointer.content_version}/`)) throw new Error(`Unsafe fixture chunk path: ${chunk.relative_path}`);
    const chunkPath = resolve(source, chunk.relative_path);
    if (!chunkPath.startsWith(`${resolve(source)}${sep}`) || !existsSync(chunkPath)) throw new Error(`Missing fixture chunk: ${chunk.relative_path}`);
    if (statSync(chunkPath).size !== chunk.byte_count || sha256(chunkPath) !== chunk.content_hash) throw new Error(`Fixture chunk integrity mismatch: ${chunk.chunk_id}`);
  }
  const paths = [pointer.root_relative_path, pointer.metadata_relative_path, ...metadata.chunks.map((chunk) => chunk.relative_path)];
  mkdirSync(destination, { recursive: true });
  cpSync(pointerPath, join(destination, "current-package.json"));
  for (const item of [...new Set(paths)].sort()) {
    const sourcePath = resolve(source, item);
    if (!sourcePath.startsWith(`${resolve(source)}${sep}`) || !existsSync(sourcePath)) {
      throw new Error(`Fixture manifest references missing or unsafe path: ${item}`);
    }
    const targetPath = join(destination, item);
    mkdirSync(dirname(targetPath), { recursive: true });
    cpSync(sourcePath, targetPath);
  }
}

function nugetComponents(lockPath) {
  const lock = readJson(lockPath);
  const components = new Map();
  for (const dependencies of Object.values(lock.dependencies ?? {})) {
    for (const [name, detail] of Object.entries(dependencies)) {
      const version = detail.resolved;
      if (!version) continue;
      const key = `${name.toLowerCase()}@${version}`;
      components.set(key, {
        type: "library",
        name,
        version,
        purl: `pkg:nuget/${encodeURIComponent(name)}@${encodeURIComponent(version)}`,
      });
    }
  }
  return components;
}

function generateMetadata(args) {
  if (args.length !== 16) {
    throw new Error("metadata usage: PACKAGE REPO TARGET REVISION EPOCH PRESET BINARY LAUNCHER TEMPLATE_SHA TEMPLATE_VERSION GODOT_VERSION DOTNET_VERSION RUNTIME_VERSION UV_VERSION NODE_VERSION PYTHON_VERSION");
  }
  const [packageRoot, repoRoot, target, revision, epochText, presetName, binaryRelative, launcherRelative, templateSha, templateVersion, godotVersion, dotnetVersion, runtimeVersion, uvVersion, nodeVersion, pythonVersion] = args;
  const contentRoot = join(packageRoot, "content", "official-corridor");
  const pointer = readJson(join(contentRoot, "current-package.json"));
  const routeMetadata = readJson(join(contentRoot, pointer.metadata_relative_path));
  const epoch = Number(epochText);
  if (!Number.isSafeInteger(epoch) || epoch < 0) throw new Error(`Invalid SOURCE_DATE_EPOCH: ${epochText}`);

  const components = new Map();
  for (const lock of [join(repoRoot, "packages.lock.json"), join(repoRoot, "src", "Cannonball.Core", "packages.lock.json")]) {
    for (const [key, component] of nugetComponents(lock)) components.set(key, component);
  }
  components.set(`godot@${godotVersion}`, { type: "framework", name: "Godot Engine Mono", version: godotVersion });
  components.set(`dotnet-runtime@${runtimeVersion}`, {
    type: "framework",
    name: "Microsoft.NETCore.App Runtime",
    version: runtimeVersion,
    purl: `pkg:generic/microsoft-dotnet-runtime@${encodeURIComponent(runtimeVersion)}`,
  });
  components.set(`route@${pointer.content_version}`, {
    type: "data",
    name: "Cannonball official-corridor fixture",
    version: pointer.content_version,
    hashes: [{ alg: "SHA-256", content: sha256(join(contentRoot, pointer.root_relative_path)) }],
  });
  const metadataDir = join(packageRoot, "metadata");
  mkdirSync(metadataDir, { recursive: true });
  writeJson(join(metadataDir, "sbom.cdx.json"), {
    bomFormat: "CycloneDX",
    specVersion: "1.6",
    serialNumber: `urn:uuid:${createHash("sha256").update(`${revision}:${target}`).digest("hex").slice(0, 8)}-${createHash("sha256").update(`${revision}:${target}`).digest("hex").slice(8, 12)}-4000-8000-${createHash("sha256").update(`${revision}:${target}`).digest("hex").slice(12, 24)}`,
    version: 1,
    metadata: {
      timestamp: new Date(epoch * 1000).toISOString(),
      component: { type: "application", name: "Cannonball Run", version: revision },
      tools: { components: [
        { type: "application", name: "Godot Engine Mono", version: godotVersion },
        { type: "application", name: ".NET SDK", version: dotnetVersion },
        { type: "framework", name: ".NET Runtime", version: runtimeVersion },
        { type: "application", name: "uv", version: uvVersion },
        { type: "application", name: "Node.js", version: nodeVersion },
        { type: "application", name: "Python", version: pythonVersion },
      ] },
    },
    components: [...components.values()].sort((a, b) => `${a.name}@${a.version}` < `${b.name}@${b.version}` ? -1 : 1),
  });

  const presetPath = join(repoRoot, "export_presets.cfg");
  const inventory = filesUnder(packageRoot)
    .filter((path) => !path.endsWith(`${sep}manifest.json`) && !path.endsWith(`${sep}SHA256SUMS`))
    .map((path) => ({
      path: unixPath(relative(packageRoot, path)),
      bytes: statSync(path).size,
      sha256: sha256(path),
      mode: (statSync(path).mode & 0o777).toString(8).padStart(4, "0"),
    }));
  const chunks = routeMetadata.chunks.map((chunk) => ({
    id: chunk.chunk_id,
    path: chunk.relative_path,
    sha256: sha256(join(contentRoot, chunk.relative_path)),
    bytes: statSync(join(contentRoot, chunk.relative_path)).size,
  })).sort((a, b) => a.id < b.id ? -1 : 1);
  const contentSetSha256 = createHash("sha256").update(
    inventory.map((item) => `${item.path}\0${item.sha256}\0${item.bytes}\n`).join("")
  ).digest("hex");
  const runtimeId = target === "linux" ? "linux-x64" : "win-x64";
  writeJson(join(metadataDir, "manifest.json"), {
    schema_version: 1,
    artifact: {
      id: `cannonball-${target}-${revision}`,
      platform: target,
      architecture: "x86_64",
      signed: false,
      fixture_scoped: true,
      public_release_ready: false,
      representative_route: false,
      milestone_complete: false,
      binary: binaryRelative,
      launcher: launcherRelative,
    },
    source: { revision, source_date_epoch: epoch, source_date_utc: new Date(epoch * 1000).toISOString() },
    build: {
      preset: presetName,
      preset_sha256: sha256(presetPath),
      godot_version: godotVersion,
      dotnet_version: dotnetVersion,
      uv_version: uvVersion,
      export_template_archive_sha256: templateSha,
      export_template_version: templateVersion,
      runtime_framework_version: runtimeVersion,
      node_version: nodeVersion,
      python_version: pythonVersion,
      restore_locked_mode: true,
      content_set_sha256: contentSetSha256,
      lockfiles: [`packages.${runtimeId}.lock.json`, `src/Cannonball.Core/packages.${runtimeId}.lock.json`].map((path) => ({ path, sha256: sha256(join(repoRoot, path)) })),
      inputs: ["project.godot", "Cannonball.csproj", "src/Cannonball.Core/Cannonball.Core.csproj"].map((path) => ({ path, sha256: sha256(join(repoRoot, path)) })),
    },
    content: {
      fixture: "official-corridor",
      representative: false,
      content_version: pointer.content_version,
      pointer: "content/official-corridor/current-package.json",
      route_root: `content/official-corridor/${pointer.root_relative_path}`,
      route_root_sha256: sha256(join(contentRoot, pointer.root_relative_path)),
      metadata: `content/official-corridor/${pointer.metadata_relative_path}`,
      metadata_sha256: sha256(join(contentRoot, pointer.metadata_relative_path)),
      unique_route_miles: routeMetadata.edges.reduce((sum, edge) => sum + Number(edge.length_meters), 0) / 1609.344,
      chunks,
    },
    files: inventory,
  });

  const checksums = filesUnder(packageRoot)
    .filter((path) => !path.endsWith(`${sep}SHA256SUMS`))
    .map((path) => `${sha256(path)}  ${unixPath(relative(packageRoot, path))}`)
    .join("\n");
  writeFileSync(join(metadataDir, "SHA256SUMS"), `${checksums}\n`);
}

const [command, ...args] = process.argv.slice(2);
if (command === "copy-content" && args.length === 2) copyContent(args[0], args[1]);
else if (command === "metadata") generateMetadata(args);
else throw new Error(`Unknown package-tools command: ${command ?? "<missing>"}`);
