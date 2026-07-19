#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { pipeline } from "node:stream/promises";
import { spawnSync } from "node:child_process";
import { basename, dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";

const LOCK_PATHS = [
  "data/sources/source-lock.json",
  "data/sources/representative-corridor-lock.json",
];
const CLASSIFICATION_PATH = "data/sources/retention-classification.json";
const DEFAULT_PART_SIZE = 1_900_000_000;

function fail(message) {
  throw new Error(message);
}

function parseArgs(values) {
  const parsed = {};
  for (let index = 0; index < values.length; index += 1) {
    const argument = values[index];
    if (!argument.startsWith("--")) fail(`Unexpected argument: ${argument}`);
    const key = argument.slice(2);
    const value = values[index + 1];
    if (value === undefined || value.startsWith("--")) parsed[key] = true;
    else {
      parsed[key] = value;
      index += 1;
    }
  }
  return parsed;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJson(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

function stableBytes(value) {
  return Buffer.from(`${JSON.stringify(stable(value))}\n`);
}

function sortedStableJson(values) {
  return JSON.stringify(values.map((value) => JSON.stringify(stable(value))).sort());
}

function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function sha256File(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

function assertSha(value, label) {
  if (!/^[0-9a-f]{64}$/.test(value ?? "")) fail(`${label} must be a lowercase SHA-256.`);
}

function repoRelative(repoRoot, relativePath) {
  const root = resolve(repoRoot);
  const candidate = resolve(root, relativePath);
  if (candidate !== root && !candidate.startsWith(`${root}/`)) fail(`Unsafe repository path: ${relativePath}`);
  return candidate;
}

function safeAssetName(name, label = "Release asset") {
  if (typeof name !== "string" || !/^[A-Za-z0-9._-]+$/.test(name) || basename(name) !== name) {
    fail(`${label} has an unsafe name: ${String(name)}`);
  }
  return name;
}

function referencesFromLocks(locks) {
  const unique = new Map();
  const references = [];
  for (const lock of locks) {
    if (!Array.isArray(lock.payload.acquisitions)) fail(`${lock.relativePath} has no acquisitions array.`);
    lock.payload.acquisitions.forEach((acquisition, acquisitionIndex) => {
      if (!Array.isArray(acquisition.artifacts)) fail(`${lock.relativePath} acquisition ${acquisitionIndex} has no artifacts.`);
      acquisition.artifacts.forEach((artifact, artifactIndex) => {
        assertSha(artifact.sha256, `${lock.relativePath} artifact ${artifactIndex}`);
        if (!artifact.path && !artifact.url) fail(`Artifact ${artifact.sha256} has neither path nor URL.`);
        const reference = {
          lock_path: lock.relativePath,
          acquisition_index: acquisitionIndex,
          artifact_index: artifactIndex,
          source_id: acquisition.source_id,
          role: artifact.role,
          sha256: artifact.sha256,
          expected_bytes: artifact.byte_count ?? null,
          origin: artifact.path ? { kind: "repository", path: artifact.path } : { kind: "url", url: artifact.url },
        };
        references.push(reference);
        const existing = unique.get(artifact.sha256);
        if (!existing) unique.set(artifact.sha256, { sha256: artifact.sha256, candidates: [reference] });
        else existing.candidates.push(reference);
      });
    });
  }
  return { references, unique };
}

function sourceClassification(repoRoot, locks) {
  const classificationPath = repoRelative(repoRoot, CLASSIFICATION_PATH);
  const payload = readJson(classificationPath);
  if (payload.schema_version !== 1 || payload.decision !== "ADR-0010") {
    fail("Retention classification must use schema 1 and ADR-0010.");
  }
  const rows = new Map(payload.sources.map((row) => [row.source_id, row]));
  const sourceIds = new Set(locks.flatMap(({ payload: lock }) => lock.acquisitions.map((item) => item.source_id)));
  const triggers = [];
  for (const sourceId of [...sourceIds].sort()) {
    const row = rows.get(sourceId);
    if (!row) fail(`Missing ADR-0010 classification for ${sourceId}.`);
    for (const field of ["unique", "privately_licensed", "legally_critical", "expensive_to_reconstruct", "reliably_reacquirable"]) {
      if (typeof row[field] !== "boolean") fail(`Classification ${sourceId}.${field} must be boolean.`);
    }
    if (typeof row.rationale !== "string" || row.rationale.trim() === "") fail(`Classification ${sourceId} needs a rationale.`);
    const reasons = [
      row.unique && "unique",
      row.privately_licensed && "privately_licensed",
      row.legally_critical && "legally_critical",
      row.expensive_to_reconstruct && "expensive_to_reconstruct",
      !row.reliably_reacquirable && "not_reliably_reacquirable",
    ].filter(Boolean);
    if (reasons.length > 0) triggers.push({ source_id: sourceId, reasons });
  }
  for (const sourceId of rows.keys()) {
    if (!sourceIds.has(sourceId)) fail(`Classification contains unlocked source ${sourceId}.`);
  }
  return {
    path: CLASSIFICATION_PATH,
    sha256: sha256Bytes(readFileSync(classificationPath)),
    sources: [...rows.values()].sort((a, b) => a.source_id.localeCompare(b.source_id)),
    p1_005_required: triggers.length > 0,
    triggers,
  };
}

function loadInventory(repoRoot) {
  const locks = LOCK_PATHS.map((relativePath) => {
    const path = repoRelative(repoRoot, relativePath);
    return { relativePath, path, payload: readJson(path), sha256: sha256Bytes(readFileSync(path)) };
  });
  const classification = sourceClassification(repoRoot, locks);
  const { references, unique } = referencesFromLocks(locks);
  return { locks, classification, references, unique };
}

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.status !== 0) fail(`${command} exited with status ${result.status}.`);
}

async function acquire(repoRoot, cacheRoot, item) {
  mkdirSync(cacheRoot, { recursive: true });
  const destination = join(cacheRoot, item.sha256);
  if (existsSync(destination) && await sha256File(destination) === item.sha256) return destination;
  rmSync(destination, { force: true });
  const local = item.candidates.find((candidate) => candidate.origin.kind === "repository");
  if (local) {
    const source = repoRelative(repoRoot, local.origin.path);
    if (!existsSync(source)) fail(`Locked repository artifact is missing: ${local.origin.path}`);
    run("cp", [source, destination]);
  } else {
    const url = item.candidates[0].origin.url;
    run("curl", ["--fail", "--location", "--retry", "3", "--retry-all-errors", "--output", destination, url]);
  }
  const actual = await sha256File(destination);
  if (actual !== item.sha256) {
    rmSync(destination, { force: true });
    fail(`Locked artifact hash mismatch for ${item.sha256}: received ${actual}.`);
  }
  const expectedSizes = [...new Set(item.candidates.map((candidate) => candidate.expected_bytes).filter((size) => size !== null))];
  if (expectedSizes.some((size) => size !== statSync(destination).size)) fail(`Locked artifact byte count mismatch for ${item.sha256}.`);
  return destination;
}

async function splitFile(source, assetsRoot, digest, partSize) {
  const bytes = statSync(source).size;
  if (bytes <= partSize) {
    const name = `${digest}.blob`;
    await pipeline(createReadStream(source), createWriteStream(join(assetsRoot, name), { mode: 0o644 }));
    return [{ name, index: 0, bytes, sha256: digest }];
  }
  const partCount = Math.ceil(bytes / partSize);
  const width = Math.max(5, String(partCount).length);
  const parts = [];
  let index = 0;
  let offset = 0;
  while (offset < bytes) {
    const length = Math.min(partSize, bytes - offset);
    const name = `${digest}.part-${String(index + 1).padStart(width, "0")}-of-${String(partCount).padStart(width, "0")}`;
    await pipeline(createReadStream(source, { start: offset, end: offset + length - 1 }), createWriteStream(join(assetsRoot, name), { mode: 0o644 }));
    parts.push({ name, index, bytes: length, sha256: await sha256File(join(assetsRoot, name)) });
    index += 1;
    offset += length;
  }
  return parts;
}

async function prepare(options) {
  const repoRoot = resolve(options.repo ?? ".");
  const outputRoot = resolve(options.output ?? fail("prepare requires --output."));
  const partSize = Number(options["part-size"] ?? DEFAULT_PART_SIZE);
  if (!Number.isSafeInteger(partSize) || partSize < 1 || partSize >= 2_000_000_000) fail("Part size must be an integer from 1 through 1,999,999,999 bytes.");
  const { locks, classification, references, unique } = loadInventory(repoRoot);
  if (classification.p1_005_required) fail(`ADR-0010 activates P1-005: ${JSON.stringify(classification.triggers)}`);
  rmSync(outputRoot, { recursive: true, force: true });
  const assetsRoot = join(outputRoot, "assets");
  const cacheRoot = resolve(options.cache ?? join(dirname(outputRoot), "cache"));
  mkdirSync(assetsRoot, { recursive: true });
  const retained = [];
  for (const item of [...unique.values()].sort((a, b) => a.sha256.localeCompare(b.sha256))) {
    const source = await acquire(repoRoot, cacheRoot, item);
    retained.push({
      sha256: item.sha256,
      bytes: statSync(source).size,
      parts: await splitFile(source, assetsRoot, item.sha256, partSize),
      references: item.candidates.sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
    });
  }
  const lockAssets = [];
  for (const lock of locks) {
    const name = `lock-${basename(lock.relativePath, ".json")}-${lock.sha256}.json`;
    writeFileSync(join(assetsRoot, name), readFileSync(lock.path));
    lockAssets.push({ path: lock.relativePath, name, sha256: lock.sha256, bytes: statSync(lock.path).size });
  }
  const classificationName = `retention-classification-${classification.sha256}.json`;
  writeFileSync(join(assetsRoot, classificationName), readFileSync(repoRelative(repoRoot, CLASSIFICATION_PATH)));
  const identity = {
    schema_version: 1,
    locks: lockAssets.map(({ path, sha256 }) => ({ path, sha256 })),
    classification_sha256: classification.sha256,
    retained: retained.map(({ sha256, bytes, parts }) => ({ sha256, bytes, parts })),
  };
  const packageId = sha256Bytes(stableBytes(identity));
  const manifest = {
    schema_version: 1,
    package_id: packageId,
    release_tag: `source-lock-v1-${packageId.slice(0, 16)}`,
    source_revision: options.revision ?? "unknown",
    source_date_utc: options["source-date"] ?? "unknown",
    part_size_bytes: partSize,
    policy: {
      decision: "ADR-0006",
      recovery_decision: "ADR-0010",
      classification_asset: classificationName,
      classification_sha256: classification.sha256,
      p1_005_required: false,
      triggers: [],
    },
    locks: lockAssets,
    artifacts: retained,
    references,
    notices: [
      "NHPN source data: U.S. Department of Transportation; public domain.",
      "3DEP source data: U.S. Geological Survey; public domain.",
      "Agency names identify provenance and do not imply endorsement.",
    ],
  };
  writeJson(join(assetsRoot, "source-retention-manifest-v1.json"), manifest);
  const files = [
    ...retained.flatMap((item) => item.parts.map((part) => part.name)),
    ...lockAssets.map((lock) => lock.name),
    classificationName,
    "source-retention-manifest-v1.json",
  ].sort();
  const sums = [];
  for (const name of files) sums.push(`${await sha256File(join(assetsRoot, name))}  ${name}`);
  writeFileSync(join(assetsRoot, "SHA256SUMS"), `${sums.join("\n")}\n`);
  writeJson(join(outputRoot, "result.json"), {
    status: "prepared",
    package_id: packageId,
    release_tag: manifest.release_tag,
    manifest_sha256: await sha256File(join(assetsRoot, "source-retention-manifest-v1.json")),
    artifact_count: retained.length,
    source_reference_count: references.length,
    release_asset_count: files.length + 1,
    total_retained_bytes: retained.reduce((sum, item) => sum + item.bytes, 0),
    part_size_bytes: partSize,
    p1_005_required: false,
  });
  process.stdout.write(`${JSON.stringify(readJson(join(outputRoot, "result.json")))}\n`);
}

async function verify(options) {
  const assetsRoot = resolve(options.assets ?? fail("verify requires --assets."));
  const manifestPath = join(assetsRoot, "source-retention-manifest-v1.json");
  const manifest = readJson(manifestPath);
  if (manifest.schema_version !== 1) fail("Unsupported source-retention manifest schema.");
  assertSha(manifest.package_id, "Manifest package ID");
  const checksums = readFileSync(join(assetsRoot, "SHA256SUMS"), "utf8").trim().split("\n");
  const checksumNames = new Set();
  for (const line of checksums) {
    const match = /^([0-9a-f]{64})  ([^/]+)$/.exec(line);
    if (!match) fail(`Malformed SHA256SUMS line: ${line}`);
    safeAssetName(match[2], "SHA256SUMS entry");
    if (checksumNames.has(match[2])) fail(`Duplicate SHA256SUMS entry: ${match[2]}`);
    checksumNames.add(match[2]);
    const file = join(assetsRoot, match[2]);
    if (!existsSync(file) || await sha256File(file) !== match[1]) fail(`Release asset checksum mismatch: ${match[2]}`);
  }
  const expectedNames = new Set(["source-retention-manifest-v1.json", manifest.policy.classification_asset]);
  const lockPayloads = [];
  for (const lock of manifest.locks) {
    safeAssetName(lock.name, "Lock asset");
    expectedNames.add(lock.name);
    const lockPath = join(assetsRoot, lock.name);
    if (!existsSync(lockPath) || await sha256File(lockPath) !== lock.sha256) fail(`Lock document mismatch: ${lock.name}`);
    lockPayloads.push({ relativePath: lock.path, payload: readJson(lockPath) });
  }
  safeAssetName(manifest.policy.classification_asset, "Classification asset");
  const classificationPath = join(assetsRoot, manifest.policy.classification_asset);
  if (!existsSync(classificationPath) || await sha256File(classificationPath) !== manifest.policy.classification_sha256) {
    fail("Retention classification asset mismatch.");
  }
  const locked = referencesFromLocks(lockPayloads);
  if (sortedStableJson(locked.references) !== sortedStableJson(manifest.references)) {
    fail("Manifest references do not match the retained lock documents.");
  }
  if (sortedStableJson(manifest.references) !== sortedStableJson(manifest.artifacts.flatMap((artifact) => artifact.references))) {
    fail("Retained artifact references do not match the manifest reference index.");
  }
  const reconstructRoot = resolve(options.reconstruct ?? join(dirname(assetsRoot), "reconstructed"));
  rmSync(reconstructRoot, { recursive: true, force: true });
  mkdirSync(reconstructRoot, { recursive: true });
  for (const artifact of manifest.artifacts) {
    assertSha(artifact.sha256, "Retained artifact");
    const output = join(reconstructRoot, artifact.sha256);
    const writer = createWriteStream(output, { mode: 0o600 });
    for (const [index, part] of artifact.parts.entries()) {
      if (part.index !== index) fail(`Non-contiguous part order for ${artifact.sha256}.`);
      safeAssetName(part.name, "Retained part");
      expectedNames.add(part.name);
      const partPath = join(assetsRoot, part.name);
      if (!existsSync(partPath) || statSync(partPath).size !== part.bytes || await sha256File(partPath) !== part.sha256) {
        fail(`Part verification failed: ${part.name}`);
      }
      for await (const chunk of createReadStream(partPath)) {
        if (!writer.write(chunk)) await new Promise((accept) => writer.once("drain", accept));
      }
    }
    await new Promise((accept, reject) => writer.end((error) => error ? reject(error) : accept()));
    if (statSync(output).size !== artifact.bytes || await sha256File(output) !== artifact.sha256) fail(`Reconstruction failed: ${artifact.sha256}`);
  }
  const actualNames = readdirSync(assetsRoot).filter((name) => name !== "SHA256SUMS").sort();
  if (JSON.stringify(actualNames) !== JSON.stringify([...expectedNames].sort()) ||
      JSON.stringify([...checksumNames].sort()) !== JSON.stringify([...expectedNames].sort())) {
    fail("Release asset inventory does not exactly match the manifest and SHA256SUMS.");
  }
  const identity = {
    schema_version: 1,
    locks: manifest.locks.map(({ path, sha256 }) => ({ path, sha256 })),
    classification_sha256: manifest.policy.classification_sha256,
    retained: manifest.artifacts.map(({ sha256, bytes, parts }) => ({ sha256, bytes, parts })),
  };
  const packageId = sha256Bytes(stableBytes(identity));
  if (packageId !== manifest.package_id || manifest.release_tag !== `source-lock-v1-${packageId.slice(0, 16)}`) {
    fail("Manifest package identity does not match its locked content.");
  }
  if (manifest.policy.p1_005_required || manifest.policy.triggers.length > 0) fail("Manifest improperly bypasses an ADR-0010 recovery-replica trigger.");
  process.stdout.write(`${JSON.stringify({ status: "verified", package_id: manifest.package_id, release_tag: manifest.release_tag, artifact_count: manifest.artifacts.length, reconstructed_bytes: manifest.artifacts.reduce((sum, item) => sum + item.bytes, 0) })}\n`);
}

function classify(options) {
  const repoRoot = resolve(options.repo ?? ".");
  const inventory = loadInventory(repoRoot);
  const result = {
    status: inventory.classification.p1_005_required ? "blocked" : "passed",
    decision: "ADR-0010",
    source_count: inventory.classification.sources.length,
    artifact_reference_count: inventory.references.length,
    unique_artifact_count: inventory.unique.size,
    p1_005_required: inventory.classification.p1_005_required,
    triggers: inventory.classification.triggers,
  };
  process.stdout.write(`${JSON.stringify(result)}\n`);
  if (result.p1_005_required) process.exitCode = 2;
}

async function selfTest() {
  const root = mkdtempSync(join(tmpdir(), "cannonball-source-retention-"));
  try {
    const assets = join(root, "assets");
    mkdirSync(assets);
    const source = join(root, "source");
    writeFileSync(source, "deterministic-part-boundary-test");
    const digest = await sha256File(source);
    const parts = await splitFile(source, assets, digest, 7);
    if (parts.length !== 5 || parts.some((part, index) => part.index !== index || part.bytes > 7)) fail("Deterministic split self-test failed.");
    const combined = Buffer.concat(parts.map((part) => readFileSync(join(assets, part.name))));
    if (sha256Bytes(combined) !== digest) fail("Deterministic reconstruction self-test failed.");
    process.stdout.write(`${JSON.stringify({ status: "passed", parts: parts.length, sha256: digest })}\n`);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

const [command, ...values] = process.argv.slice(2);
const options = parseArgs(values);
if (command === "prepare") await prepare(options);
else if (command === "verify") await verify(options);
else if (command === "classify") classify(options);
else if (command === "self-test") await selfTest();
else fail(`Unknown command: ${command ?? "<missing>"}`);
