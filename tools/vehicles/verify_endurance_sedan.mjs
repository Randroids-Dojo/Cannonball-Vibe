#!/usr/bin/env node

// The shell front door dispatches here. Every export/import runs in retained,
// isolated output directories; this verifier never writes canonical assets.
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { closeSync, copyFileSync, cpSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";

const options = {};
for (let i = 2; i < process.argv.length; i++) {
  const arg = process.argv[i];
  if (arg === "--candidate") options.candidate = true;
  else if (arg === "--probe-blender-diagnostics") options.probeBlenderDiagnostics = true;
  else if (["--blender-bin", "--output"].includes(arg) && process.argv[i + 1]) options[arg.slice(2)] = process.argv[++i];
  else throw new Error(`Unknown or incomplete argument: ${arg}`);
}
if (!options["blender-bin"]) throw new Error("Missing --blender-bin");
const root = process.cwd();
const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
const output = resolve(options.output ?? `reports/assets/p1-018/${timestamp}`);
if (existsSync(output)) throw new Error(`Evidence directory already exists; preserve it and use a new --output: ${output}`);
mkdirSync(output, { recursive: true });
copyFileSync(join(root, "tools/vehicles/verify_endurance_sedan.mjs"), join(output, "verifier-input.mjs"));
const asset = "endurance-sedan";
const source = `data/assets/vehicles/sources/${asset}.blend`;
const glb = `data/assets/vehicles/derived/${asset}.glb`;
const assetDirectory = `assets/vehicles/${asset}`;
const generated = `${assetDirectory}/${asset}.generated.tscn`;
const bindings = `${assetDirectory}/${asset}.generated.textures.json`;
const wrapper = "game/Vehicle/Visuals/EnduranceSedan.tscn";
const importSettings = `data/assets/vehicles/${asset}.glb.import`;
const spec = "docs/vehicles/endurance-sedan/specification.json";
const blenderInventory = `data/assets/vehicles/${asset}.blender.json`;
const godotInventory = `data/assets/vehicles/${asset}.godot.json`;
const manifestPath = `data/assets/vehicles/${asset}.asset.json`;
const profile = "tools/assets/profiles/gltf2-endurance-sedan-v1.json";
const godotProfile = "tools/assets/profiles/godot-4.7.1-v1.json";
const blender = resolve(options["blender-bin"]);
const bash = process.env.CANNONBALL_BASH_BIN ?? (process.platform === "win32" ? "C:/Program Files/Git/bin/bash.exe" : "bash");
const hash = path => createHash("sha256").update(readFileSync(path)).digest("hex");
const load = path => JSON.parse(readFileSync(path, "utf8"));
const walk = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
  ? walk(join(directory, entry.name)) : [join(directory, entry.name)]).sort();
const pathLabel = path => relative(root, path).split(sep).join("/");
const env = { ...process.env, DOTNET_GCgen0size: "800000", CANNONBALL_GIT_REVISION: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim() };
const report = {
  schema_version: 1, task_id: "P1-018", milestone: "M5", status: "running", started_utc: new Date().toISOString(),
  git_revision: env.CANNONBALL_GIT_REVISION, platform: process.platform, architecture: process.arch, node: process.version,
  verifier_input_snapshot: { path: pathLabel(join(output, "verifier-input.mjs")), sha256: hash(join(output, "verifier-input.mjs")) },
  mode: options.probeBlenderDiagnostics ? "Blender log-policy diagnostic only; no asset acceptance" : options.candidate ? "isolated candidate; canonical output comparison deferred" : "delivered-artifact verification",
  commands: [], comparisons: [], failures: [], negative_controls: [], normalization_inputs: [], human_approval_reference: null,
  project_copy_exclusions: [{ path: "data/assets/vehicles/endurance-sedan-review/",
    reason: "Historical review media is outside Godot import and release data; adjacent authoritative assets/docs/tools remain copied and hash-locked." }],
  limitations: ["This asset gate does not replace native driving, visual inspection, frame-time evidence or human approval.",
    "Renderer contact sheets are independently retained; no deterministic contact-sheet claim is made here.",
    "Importer metadata UIDs are staging identities; portable sidecars contain paths and shipping GPU texture bytes are compared.",
    "Two complete PCK files are compared here. Native executables and external managed assemblies remain covered by the required scripts/release/build-unsigned.sh platform gate."],
};
const allowedImportWarnings = ["WARNING: Ignoring unsupported header information in HDR: GAMMA=1.",
  "WARNING: Ignoring unsupported header information in HDR: PRIMARIES=0 0 0 0 0 0 0 0."];
const saveReport = () => writeFileSync(join(output, "evidence.json"), JSON.stringify(report, null, 2) + "\n");
const blenderDiagnosticLines = text => text.split(/\r?\n/).filter(line =>
  /PyDriver|Traceback \(most recent call last\)|SyntaxError:|Error: Python|ERROR[^\r\n]*\bDriver\b/i.test(line) ||
  /(?:image|texture|packed (?:file|data)).*(?:cannot|could not|can't|couldn't|unable|missing|not found|not available|not packed|unpacked|failed|does not exist|no such file)/i.test(line) ||
  /(?:cannot|could not|can't|couldn't|unable|missing|not found|not available|unpacked|failed|no such file).*(?:image|texture|packed (?:file|data))/i.test(line));

async function run(label, executable, args, { cwd = root, timeout = 300000, expected = 0, expectedText = null, strictGodot = false, allowExistingHdrHeaders = false } = {}) {
  const stdoutPath = join(output, `${label}.stdout.log`);
  const stderrPath = join(output, `${label}.stderr.log`);
  const stdout = openSync(stdoutPath, "w"), stderr = openSync(stderrPath, "w");
  const record = { label, executable, args, cwd, started_utc: new Date().toISOString(), expected_exit: expected, expected_text: expectedText };
  let child;
  let timer;
  try {
    child = spawn(executable, args, { cwd, env, windowsHide: true, stdio: ["ignore", stdout, stderr], detached: process.platform !== "win32" });
    record.pid = child.pid;
    timer = setTimeout(() => {
      record.timed_out = true;
      if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { windowsHide: true, stdio: "ignore" });
      else process.kill(-child.pid, "SIGKILL");
    }, timeout);
    const [code, signal] = await new Promise((done, reject) => { child.once("error", reject); child.once("close", (...values) => done(values)); });
    record.exit_status = code;
    record.signal = signal;
  } finally {
    clearTimeout(timer); closeSync(stdout); closeSync(stderr);
    record.finished_utc = new Date().toISOString();
    record.stdout = pathLabel(stdoutPath); record.stdout_sha256 = hash(stdoutPath);
    record.stderr = pathLabel(stderrPath); record.stderr_sha256 = hash(stderrPath);
    report.commands.push(record); saveReport();
  }
  const text = readFileSync(stdoutPath, "utf8") + "\n" + readFileSync(stderrPath, "utf8");
  if (record.timed_out || record.exit_status !== expected || expectedText && !text.includes(expectedText))
    throw new Error(`${label} failed its expected exit/diagnostic contract: ${record.exit_status}, timeout=${!!record.timed_out}`);
  // Expected rejection cases may emit their named validation error; native
  // crashes, managed fatals and resource leaks never count as that rejection.
  if (/Unhandled exception|Fatal error|AccessViolationException|SIGSEGV|Segmentation fault|Leaked unsafe reference|ObjectDB instances leaked|resources still in use/i.test(text))
    throw new Error(`${label} emitted a fatal or resource-leak diagnostic`);
  // Blender can finish with exit 0 after a failed driver or Python callback.
  // Expected exporter rejections retain their named exception contract above.
  if (executable === blender && expected === 0) {
    record.positive_blender_diagnostics = blenderDiagnosticLines(text);
    saveReport();
    if (record.positive_blender_diagnostics.length) {
      const error = new Error(`${label} emitted a Blender driver, Python or image-dependency diagnostic`);
      error.code = "BLENDER_DIAGNOSTIC_REJECTED";
      throw error;
    }
  }
  let checkedText = text;
  if (allowExistingHdrHeaders) {
    record.known_import_warnings = allowedImportWarnings.filter(warning => text.includes(warning));
    for (const warning of allowedImportWarnings) checkedText = checkedText.replaceAll(warning, "");
    saveReport();
  }
  if (strictGodot && /(?:^|\n)(?:ERROR|WARNING|SCRIPT ERROR):|Unhandled exception|Fatal error|AccessViolationException|SIGSEGV|Segmentation fault|Leaked unsafe reference|ObjectDB instances leaked|resources still in use/i.test(checkedText))
    throw new Error(`${label} emitted an engine error, warning, fatal or resource-leak diagnostic`);
  return text;
}
const godot = (label, stage, args, settings = {}) => run(label, bash,
  [join(root, "scripts/godot.sh").split(sep).join("/"), "--headless", "--path", stage, ...args], { strictGodot: true, ...settings });
const compare = (label, first, second) => {
  const left = hash(first), right = hash(second);
  report.comparisons.push({ label, first: pathLabel(first), second: pathLabel(second), first_sha256: left, second_sha256: right, equal: left === right });
  if (left !== right) throw new Error(`Byte drift: ${label}`);
};
const compareFields = (label, first, second, fields) => {
  for (const field of fields) {
    if (!Object.hasOwn(first, field) || !Object.hasOwn(second, field)) throw new Error(`${label} required field missing: ${field}`);
    if (JSON.stringify(first[field]) !== JSON.stringify(second[field])) throw new Error(`${label} field drift: ${field}`);
  }
};
const copy = (from, to) => { mkdirSync(dirname(to), { recursive: true }); copyFileSync(from, to); };
const safeRemoveFile = path => {
  const checked = resolve(path);
  if (!checked.startsWith(output + sep) || statSync(checked).isDirectory()) throw new Error(`Refusing non-file/outside-stage removal: ${checked}`);
  rmSync(checked);
};
function stageProject(destination) {
  const excluded = new Set([".git", ".godot", ".tools", "reports", "node_modules", "bin", "obj", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"]);
  const reviewMedia = resolve(root, "data/assets/vehicles/endurance-sedan-review");
  mkdirSync(destination, { recursive: true });
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (excluded.has(entry.name)) continue;
    cpSync(join(root, entry.name), join(destination, entry.name), {
      recursive: true, filter: path => resolve(path) !== reviewMedia && !resolve(path).startsWith(reviewMedia + sep) &&
        !relative(root, path).split(sep).some(part => excluded.has(part)),
    });
  }
  const copiedInputs = Object.fromEntries(walk(destination).map(path => [relative(destination, path).split(sep).join("/"), hash(path)]));
  if (report.copied_project_inputs && JSON.stringify(report.copied_project_inputs) !== JSON.stringify(copiedInputs))
    throw new Error("Project source/input bytes changed between isolated copies");
  report.copied_project_inputs = copiedInputs;
  // Retaining an orphan .png.import makes the first editor scan try to load a
  // missing image, so glTF falls back to an uncompressed embedded texture.
  // Lock the parameters in memory, then remove both files for fresh extraction.
  const lockedTextureImports = walk(join(destination, assetDirectory)).filter(path => path.endsWith(".png.import"))
    .map(path => ({ path: relative(destination, path).split(sep).join("/"), sha256: hash(path),
      parameters: textureImportParameters(readFileSync(path, "utf8")).parameters }));
  for (const path of walk(join(destination, assetDirectory)))
    if (path.endsWith(".png") || path.endsWith(".png.import")) safeRemoveFile(path);
  const remaining = walk(join(destination, assetDirectory));
  const preparation = { lockedTextureImports, pngs_before_extraction: remaining.filter(path => path.endsWith(".png")).length,
    texture_metadata_before_extraction: remaining.filter(path => path.endsWith(".png.import")).length,
    import_cache_before_extraction: existsSync(join(destination, ".godot")) };
  if (preparation.pngs_before_extraction || preparation.texture_metadata_before_extraction || preparation.import_cache_before_extraction)
    throw new Error("Fresh texture extraction requires absent PNGs, texture metadata and import cache");
  return preparation;
}
function textureImportParameters(text) {
  const normalized = text.replaceAll("\r\n", "\n");
  const marker = /^\[params\]\n/gm;
  const matches = [...normalized.matchAll(marker)];
  if (matches.length !== 1) throw new Error("Texture import metadata must contain one parameters section");
  const offset = matches[0].index + matches[0][0].length;
  const parameters = normalized.slice(offset).trim() + "\n";
  if (/^\[/m.test(parameters)) throw new Error("Texture import parameters must be the final section");
  return { prefix: normalized.slice(0, offset), parameters };
}
function importedTexturePaths(text) {
  return [...new Set([...text.matchAll(/"(res:\/\/\.godot\/imported\/[^"\n]+\.ctex)"/g)].map(match => match[1].slice(6)))];
}
async function prepareExtractedTextures(name, stage, preparation) {
  const images = walk(join(stage, assetDirectory)).filter(path => path.endsWith(".png"));
  const extractedMetadata = images.map(path => relative(stage, path).split(sep).join("/") + ".import").sort();
  const locked = new Map(preparation.lockedTextureImports.map(row => [row.path, row]));
  if (locked.size && JSON.stringify([...locked.keys()].sort()) !== JSON.stringify(extractedMetadata))
    throw new Error("Fresh GLB texture inventory differs from locked import settings");
  const record = { stage: name, ...preparation, extracted: [], regenerated_gpu_textures: [] };
  report.texture_import_preparation ??= [];
  report.texture_import_preparation.push(record);
  for (const path of extractedMetadata) {
    const metadata = join(stage, path), png = metadata.slice(0, -".import".length);
    const fresh = readFileSync(metadata, "utf8");
    const parts = textureImportParameters(fresh);
    const parameters = locked.get(path)?.parameters ?? parts.parameters;
    const caches = importedTexturePaths(fresh);
    if (!caches.length) throw new Error(`Fresh extraction has no compressed texture cache: ${path}`);
    record.extracted.push({ path: path.slice(0, -".import".length), sha256: hash(png), bytes: statSync(png).size,
      fresh_metadata_sha256: hash(metadata), fresh_uid: fresh.match(/^uid="([^"]+)"/m)?.[1],
      parameters, locked_metadata_sha256: locked.get(path)?.sha256 ?? null,
      removed_gpu_caches: caches.map(cache => ({ path: cache, sha256: hash(join(stage, cache)), bytes: statSync(join(stage, cache)).size })) });
    // Keep freshly registered identities and generator/dependency metadata;
    // only the locked portable parameters replace automatic import defaults.
    writeFileSync(metadata, parts.prefix + parameters);
    for (const cache of caches) safeRemoveFile(join(stage, cache));
  }
  saveReport();
  if (images.length) await godot(`${name}-locked-texture-import`, stage, ["--import"], { timeout: 600000, allowExistingHdrHeaders: true });
  for (const row of record.extracted) {
    const metadata = readFileSync(join(stage, row.path + ".import"), "utf8");
    if (textureImportParameters(metadata).parameters !== row.parameters || hash(join(stage, row.path)) !== row.sha256 ||
        metadata.match(/^uid="([^"]+)"/m)?.[1] !== row.fresh_uid)
      throw new Error(`Locked texture parameters, extracted image or fresh identity changed: ${row.path}`);
    const caches = importedTexturePaths(metadata);
    if (!caches.length) throw new Error(`Locked texture reimport has no GPU payload: ${row.path}`);
    for (const cache of caches) {
      const bytes = readFileSync(join(stage, cache));
      // Pinned Godot 4.7.1 CompressedTexture2D::_load_data and load_image_from_file.
      if (bytes.length < 52 || bytes.toString("ascii", 0, 4) !== "GST2" || bytes.readUInt32LE(4) !== 1)
        throw new Error(`Invalid pinned compressed texture header: ${cache}`);
      const flags = bytes.readUInt32LE(16), mipmaps = bytes.readUInt32LE(44), format = bytes.readUInt32LE(48);
      const expectedMipmaps = /^mipmaps\/generate=true$/m.test(row.parameters);
      if (!!(flags & (1 << 23)) !== expectedMipmaps || expectedMipmaps && Math.max(bytes.readUInt32LE(8), bytes.readUInt32LE(12)) > 1 && mipmaps === 0)
        throw new Error(`Compressed texture mipmap flags differ from locked parameters: ${cache}`);
      if (/^compress\/mode=2$/m.test(row.parameters) && (bytes.readUInt32LE(36) !== 0 || format < 17 || format > 38))
        throw new Error(`Locked VRAM compression was not applied: ${cache}`);
      record.regenerated_gpu_textures.push({ path: cache, sha256: hash(join(stage, cache)), bytes: bytes.length,
        width: bytes.readUInt32LE(8), height: bytes.readUInt32LE(12), format_flags: flags,
        has_mipmaps: !!(flags & (1 << 23)), mipmap_count: mipmaps, image_data_format: bytes.readUInt32LE(36), image_format: format });
    }
  }
  record.status = "fresh_extraction_and_locked_texture_reimport_verified";
  saveReport();
}
const exporter = (input, destination) => ["--background", input, "--python-exit-code", "1", "--python", "tools/vehicles/validate_and_export_endurance_sedan.py", "--",
  "--source", input, "--output", join(destination, `${asset}.glb`), "--inventory", join(destination, "blender.json")];
const importArgs = outputPath => ["--script", "res://tools/vehicles/validate_import.gd", "--", "--vehicle", asset,
  "--specification", `res://${spec}`, "--wrapper", `res://${wrapper}`, "--glb", `res://${glb}`,
  "--generated-scene", `res://${generated}`, "--import-settings", `res://${importSettings}`,
  "--output", outputPath, "--profile", `res://${godotProfile}`];
function textureBytes(stage) {
  const sidecar = load(join(stage, bindings));
  const textures = [...new Set(Object.values(sidecar.materials).flatMap(slots => Object.values(slots)))].sort();
  const result = {};
  for (const texture of textures) {
    if (!texture.startsWith(`res://${assetDirectory}/`) || texture.includes("\\") || texture.split("/").includes("..")) throw new Error(`Texture outside sedan directory: ${texture}`);
    const relativePath = texture.slice(6);
    result[relativePath] = join(stage, relativePath);
    const importFile = readFileSync(join(stage, relativePath + ".import"), "utf8");
    const imported = [...importFile.matchAll(/"(res:\/\/\.godot\/imported\/[^"\n]+\.ctex)"/g)].map(match => match[1].slice(6));
    if (!imported.length) throw new Error(`No imported shipping texture bytes: ${relativePath}`);
    for (const path of imported) result[path] = join(stage, path);
  }
  const extracted = walk(join(stage, assetDirectory)).filter(path => path.endsWith(".png")).map(path => relative(stage, path).split(sep).join("/")).sort();
  if (JSON.stringify(extracted) !== JSON.stringify(textures.map(path => path.slice(6)))) throw new Error("Unbound or unaccounted extracted sedan texture PNGs");
  return result;
}

async function verifyBlenderDiagnosticPolicy() {
  const corrected = join(output, "corrected-driver.py");
  const probe = expression => `import bpy
probe = bpy.data.objects.new("CannonballDriverDiagnostic", None)
bpy.context.scene.collection.objects.link(probe)
curve = probe.driver_add("location", 0)
curve.driver.expression = ${JSON.stringify(expression)}
bpy.context.scene.frame_set(2)
bpy.context.view_layer.update()
evaluated = probe.evaluated_get(bpy.context.evaluated_depsgraph_get())
print("CANNONBALL_BLENDER_DRIVER_PROBE_COMPLETE valid=" + str(curve.driver.is_valid) + " x=" + str(evaluated.location.x))
`;
  writeFileSync(corrected, probe("2.0"));
  const argv = script => ["--background", "--factory-startup", "--python-exit-code", "1", "--python", script];
  for (const [name, expression, diagnostic] of [
    ["unknown-name", "CANNONBALL_MISSING_DRIVER_FUNCTION()", /PyDriver/i],
    ["division-by-zero", "1/0", /ERROR[^\r\n]*\bDriver\b/i],
  ]) {
    const invalid = join(output, `invalid-driver-${name}.py`);
    writeFileSync(invalid, probe(expression));
    let rejection;
    try {
      await run(`blender-invalid-driver-${name}-exit-zero`, blender, argv(invalid), { timeout: 60000,
        expectedText: "CANNONBALL_BLENDER_DRIVER_PROBE_COMPLETE valid=False" });
    } catch (error) {
      if (error.code !== "BLENDER_DIAGNOSTIC_REJECTED") throw error;
      rejection = error.message;
    }
    const invalidCommand = report.commands.at(-1);
    if (!rejection || invalidCommand.exit_status !== 0 || !invalidCommand.positive_blender_diagnostics.some(line => diagnostic.test(line)))
      throw new Error(`Invalid-driver ${name} probe did not demonstrate an exit-zero Blender diagnostic rejection`);
    report.negative_controls.push({ mutation: `invalid-driver-${name}-with-successful-process-exit`, status: "passed",
      invalid_script: pathLabel(invalid), invalid_script_sha256: hash(invalid), corrected_script: pathLabel(corrected),
      corrected_script_sha256: hash(corrected), process_exit: 0, policy_rejection: rejection,
      comparison: `Only the driver expression changes from ${JSON.stringify(expression)} to the constant 2.0.`,
      scope: "Factory-empty Blender diagnostic; no vehicle source, rendering or asset acceptance." });
  }
  await run("blender-corrected-driver", blender, argv(corrected), { timeout: 60000,
    expectedText: "CANNONBALL_BLENDER_DRIVER_PROBE_COMPLETE valid=True x=2.0" });
  saveReport();
}

async function verifyAsset() {
  const revisionRecord = load(spec).original_packaging?.revision_record;
  const construction = ["tools/vehicles/create_endurance_sedan.py", "tools/vehicles/validate_and_export_endurance_sedan.py",
    "tools/vehicles/validate_and_export_hero_gt.py", "tools/vehicles/glb_geometry.py", "tools/vehicles/vehicle_contract.json",
    "tools/vehicles/pack_imported_scene.gd", "tools/vehicles/validate_import.gd", "tools/vehicles/generate_manifest.mjs",
    "tools/vehicles/mutate_endurance_sedan.py", "tools/vehicles/verify_endurance_sedan.mjs", "scripts/verify-vehicle-asset.sh",
    "tools/assets/validate_manifest.mjs", "tools/assets/validate_release_pack.mjs", "data/assets/manifest.schema.json",
    "tools/assets/toolchain.json", spec, profile, godotProfile, source, importSettings, "project.godot", "export_presets.cfg",
    "data/assets/vehicles/endurance-sedan.uv-bake.json",
    "docs/vehicles/endurance-sedan/research.md", "docs/vehicles/endurance-sedan/reference-values.json",
    "docs/vehicles/endurance-sedan/production-plan.md", "docs/vehicles/endurance-sedan/production-reference-appendix.md",
    ...(revisionRecord ? [revisionRecord] : []), "scripts/godot.sh", "scripts/tool-versions.sh", "scripts/release/pck-inspect.mjs",
    "Cannonball.csproj", "global.json", "packages.lock.json", "packages.linux-x64.lock.json", "packages.win-x64.lock.json",
    "src/Cannonball.Core/Cannonball.Core.csproj", "src/Cannonball.Core/packages.lock.json",
    "assets/vehicles/hero-gt/shaders/car_paint.gdshader",
    ...walk("tools/vehicles/endurance_sedan").filter(path => path.endsWith(".py")),
    ...walk("game").filter(path => /\.(cs|tres|tscn|gdshader|uid)$/.test(path)),
    ...walk("src/Cannonball.Core").filter(path => path.endsWith(".cs") && !path.split(sep).some(part => ["bin", "obj"].includes(part))),
    ...walk(assetDirectory).filter(path => path.endsWith(".png.import"))];
  report.input_hashes = Object.fromEntries([...new Set(construction)].sort().map(path => [path.split(sep).join("/"), hash(path)]));
  const hero = ["data/assets/vehicles/sources/hero-gt.blend", "data/assets/vehicles/derived/hero-gt.glb",
    "assets/vehicles/hero-gt/hero-gt.generated.tscn", "assets/vehicles/hero-gt/hero-gt.generated.textures.json"];
  report.preserved_hero_before = Object.fromEntries(hero.map(path => [path, hash(path)]));
  const toolchain = load("tools/assets/toolchain.json");
  report.godot_version = (await run("godot-version", bash, ["scripts/godot.sh", "--version"])).trim();
  if (report.godot_version !== toolchain.godot.version) throw new Error("Godot toolchain pin mismatch");
  report.dotnet_sdk = (await run("dotnet-version", "dotnet", ["--version"])).trim();
  if (report.dotnet_sdk !== load("global.json").sdk.version) throw new Error(".NET SDK pin mismatch");
  const importText = readFileSync(importSettings, "utf8");
  for (const required of ['nodes/root_type="Node3D"', 'mesh_library/use_node_names_as_mesh_names=true', 'meshes/light_baking=0', 'meshes/generate_lods=false', 'animation/import=false'])
    if (!importText.includes(required)) throw new Error(`Sedan import profile drift: ${required}`);
  for (const binary of [source, glb]) {
    const attributes = await run(`lfs-${binary.endsWith(".blend") ? "source" : "glb"}`, "git", ["check-attr", "filter", "--", binary]);
    if (!attributes.includes(": lfs")) throw new Error(`Asset is not Git LFS governed: ${binary}`);
  }
  const stages = [];
  for (const name of ["first", "second"]) {
    const directory = join(output, name), stage = join(directory, "project");
    mkdirSync(directory, { recursive: true });
    await run(`${name}-blender-export`, blender, exporter(source, directory), { timeout: 600000 });
    const texturePreparation = stageProject(stage);
    copy(join(directory, `${asset}.glb`), join(stage, glb));
    copy(join(directory, `${asset}.glb`), join(stage, assetDirectory, `${asset}.glb`));
    copy(join(root, importSettings), join(stage, assetDirectory, `${asset}.glb.import`));
    await run(`${name}-build`, "dotnet", ["build", join(stage, "Cannonball.csproj"), "--nologo"], { timeout: 300000 });
    await godot(`${name}-clean-import`, stage, ["--import"], { timeout: 600000, allowExistingHdrHeaders: true });
    await prepareExtractedTextures(name, stage, texturePreparation);
    // Importing the raw GLB may discover the project-owned wrapper. Retain its
    // old outputs for that editor scan only, then require the normalizer to
    // create both outputs from absence. A no-op normalizer cannot pass.
    for (const path of [generated, bindings]) if (existsSync(join(stage, path))) safeRemoveFile(join(stage, path));
    report.normalization_inputs.push({ stage: name, generated_scene_exists: existsSync(join(stage, generated)), texture_sidecar_exists: existsSync(join(stage, bindings)) });
    await godot(`${name}-normalize`, stage, ["--script", "res://tools/vehicles/pack_imported_scene.gd", "--",
      `res://${assetDirectory}/${asset}.glb`, `res://${generated}`, "--vehicle", asset]);
    await godot(`${name}-wrapper`, stage, importArgs(join(directory, "godot.json")));
    const textures = textureBytes(stage);
    stages.push({ name, directory, project: stage, textures,
      compared_output_hashes: Object.fromEntries([generated, bindings, ...Object.keys(textures)].map(path => [path, hash(join(stage, path))])) });
  }
  const [first, second] = stages;
  compare("two GLB exports", join(first.directory, `${asset}.glb`), join(second.directory, `${asset}.glb`));
  await run("uv-bake-controls", blender, ["--background", "--factory-startup", "--python-exit-code", "1",
    "--python", "tools/vehicles/endurance_sedan/uv_bake_controls.py", "--", "--source", source,
    "--raw-glb", join(first.directory, `${asset}.pre-uv-bake.glb`),
    "--bake", "data/assets/vehicles/endurance-sedan.uv-bake.json", "--output", join(output, "uv-bake-controls")],
    { expectedText: "CANNONBALL_UV_BAKE_CONTROLS_OK cases=11" });
  const uvControls = load(join(output, "uv-bake-controls/evidence.json"));
  if (uvControls.status !== "passed" || uvControls.cases.length !== 11 || uvControls.cases.some(row => row.status !== "passed"))
    throw new Error("Evaluated UV bake controls incomplete");
  report.negative_controls.push({ mutation: "evaluated-uv-bake-corruption", status: "passed", cases: 11,
    evidence: pathLabel(join(output, "uv-bake-controls/evidence.json")), evidence_sha256: hash(join(output, "uv-bake-controls/evidence.json")) });
  for (const path of [generated, bindings]) compare(`two clean imports: ${path}`, join(first.project, path), join(second.project, path));
  if (JSON.stringify(Object.keys(first.textures)) !== JSON.stringify(Object.keys(second.textures))) throw new Error("Clean-import texture inventory drift");
  for (const path of Object.keys(first.textures)) compare(`two clean texture outputs: ${path}`, first.textures[path], second.textures[path]);
  const blenderFields = ["required_nodes", "triangles", "triangle_total", "lod0_triangle_total", "collision_triangle_total", "materials", "textures", "texture_bytes_total", "budgets", "bounds_meters", "hardpoints", "specification_sha256", "budget_contract_sha256", "export_validator_sha256", "gltf_profile_sha256", "source_preview_only", "validation_scope", "export_options"];
  const godotFields = ["required_nodes", "all_required_nodes_resolved", "script_reference_present", "automation_id", "glb_sha256", "generated_scene_sha256", "wrapper_sha256", "specification_sha256", "import_settings_sha256", "profile_sha256", "validator_sha256", "transitive_release_dependencies", "runtime_adapter_input_sha256", "wheelbase_meters", "track_meters", "rear_track_meters", "lod_count", "damage_zone_count", "hardpoint_measurements", "runtime_setup_values", "collision_policy_verified", "measured_dimensions_m"];
  compareFields("Blender repeat", load(join(first.directory, "blender.json")), load(join(second.directory, "blender.json")), blenderFields);
  compareFields("Exported triangle inspection repeat", load(join(first.directory, "blender.json")).glb_geometry,
    load(join(second.directory, "blender.json")).glb_geometry, ["status", "sha256", "triangles", "minimum_triangle_area_m2", "area_threshold_m2", "defects"]);
  compareFields("Godot repeat", load(join(first.directory, "godot.json")), load(join(second.directory, "godot.json")), godotFields);
  if (!options.candidate) {
    compare("delivered GLB", join(first.directory, `${asset}.glb`), join(root, glb));
    for (const path of [generated, bindings]) compare(`delivered runtime: ${path}`, join(first.project, path), join(root, path));
    for (const path of Object.keys(first.textures).filter(path => path.startsWith("assets/"))) compare(`delivered texture: ${path}`, first.textures[path], join(root, path));
    compareFields("Delivered Blender inventory", load(join(first.directory, "blender.json")), load(blenderInventory), blenderFields);
    compareFields("Delivered Godot inventory", load(join(first.directory, "godot.json")), load(godotInventory), godotFields);
  }
  for (const [mutation, expectedText] of [["unapplied-scale", "nonunit scale"], ["missing-semantic-node", "Missing semantic nodes"],
    ["external-texture", "Unpacked texture"], ["unparked-control", "must be parked"], ["hardpoint-drift", "hardpoint drift"], ["degenerate-triangle", "degenerate evaluated"]]) {
    const directory = join(output, `negative-${mutation}`), invalid = join(directory, "source.blend");
    mkdirSync(directory);
    await run(`mutate-${mutation}`, blender, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "tools/vehicles/mutate_endurance_sedan.py", "--", "--source", source, "--output", invalid, "--mutation", mutation]);
    await run(`reject-${mutation}`, blender, exporter(invalid, directory), { expected: 1, expectedText, timeout: 600000 });
    report.negative_controls.push({ mutation, status: "passed", rejected_input_sha256: hash(invalid), expected_exit: 1, expected_text: expectedText });
  }
  const baseWrapper = readFileSync(join(first.project, wrapper), "utf8");
  const invalidDirectory = join(first.project, "game/Vehicle/Visuals/ValidationOnly"); mkdirSync(invalidDirectory);
  const duplicate = baseWrapper + '\n[node name="DuplicateProbe" type="Node3D" parent="ImportedAsset"]\n\n[node name="Wheel_FL" type="Node3D" parent="ImportedAsset/DuplicateProbe"]\n';
  const nestedPath = "game/Vehicle/Visuals/ValidationOnly/Nested.tscn";
  writeFileSync(join(first.project, nestedPath), '[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://tools/vehicles/validate_import.gd" id="1_build"]\n[node name="NestedBuildDependency" type="Node3D"]\n');
  const buildDependency = baseWrapper.replace("load_steps=5", "load_steps=6").replace('[node name=', `[ext_resource type="PackedScene" path="res://${nestedPath}" id="991_fixture"]\n\n[node name=`);
  for (const [name, text, diagnostic] of [["duplicate-semantic", duplicate, "Semantic node Wheel_FL occurs 2 times"], ["transitive-build-dependency", buildDependency, "nonportable/build/test dependency"]]) {
    const path = join(invalidDirectory, `${name}.tscn`); writeFileSync(path, text);
    const argv = importArgs(join(output, `negative-${name}.json`));
    argv[argv.indexOf("--wrapper") + 1] = "res://" + relative(first.project, path).split(sep).join("/");
    await godot(`reject-${name}`, first.project, argv, { expected: 1, expectedText: diagnostic, strictGodot: false });
    report.negative_controls.push({ mutation: name, status: "passed", rejected_input_sha256: hash(path), expected_exit: 1, expected_text: diagnostic });
  }
  // Validation-only wrappers are not runtime inputs and may not enter the pack.
  for (const path of walk(invalidDirectory)) safeRemoveFile(path);
  copy(join(first.directory, "blender.json"), join(first.project, blenderInventory));
  copy(join(first.directory, "godot.json"), join(first.project, godotInventory));
  await run("candidate-manifest", process.execPath, ["tools/vehicles/generate_manifest.mjs", "--vehicle", asset, "--output", manifestPath], { cwd: first.project });
  for (const [name, path, diagnostic] of [["wrapper", wrapper, "Sedan inventories do not describe"],
    ["specification", spec, "Sedan inventories do not describe"], ["import-settings", importSettings, "Sedan inventories do not describe"],
    ["import-profile", godotProfile, "Sedan inventories do not describe"], ["validator", "tools/vehicles/validate_import.gd", "Sedan inventories do not describe"],
    ["export-profile", profile, "Sedan inventories do not describe"], ["export-validator", "tools/vehicles/validate_and_export_endurance_sedan.py", "Sedan inventories do not describe"],
    ["uv-bake", "data/assets/vehicles/endurance-sedan.uv-bake.json", "Sedan inventories do not describe"],
    ["adapter", "game/Vehicle/EnduranceSedanPresentation.cs", "runtime adapter input is stale"]]) {
    const input = join(first.project, path), original = readFileSync(input), before = hash(input);
    try {
      writeFileSync(input, Buffer.concat([original, Buffer.from("\n")]));
      const rejectedHash = hash(input);
      await run(`reject-stale-${name}-inventory`, process.execPath, ["tools/vehicles/generate_manifest.mjs", "--vehicle", asset,
        "--output", join(output, `negative-stale-${name}.asset.json`)], { cwd: first.project, expected: 1, expectedText: diagnostic });
      report.negative_controls.push({ mutation: `stale-${name}-inventory`, status: "passed", path, original_sha256: before,
        rejected_input_sha256: rejectedHash, exact_mutation: "append one LF byte to the validated input without refreshing its inventory", expected_exit: 1, expected_text: diagnostic });
    } finally { writeFileSync(input, original); }
    if (hash(input) !== before) throw new Error(`Provenance mutation did not restore the isolated input: ${path}`);
  }
  if (!options.candidate) {
    // Inventory metadata (e.g. source path) is retained as delivered. Generate
    // the final comparison manifest from those exact approved canonical files.
    await run("delivered-manifest", process.execPath, ["tools/vehicles/generate_manifest.mjs", "--vehicle", asset, "--output", join(output, "delivered.asset.json")]);
    compare("delivered manifest", join(output, "delivered.asset.json"), join(root, manifestPath));
  }
  await run("manifest-validation", process.execPath, ["tools/assets/validate_manifest.mjs", "--schema", "data/assets/manifest.schema.json", "--manifest", manifestPath,
    "--blender-inventory", blenderInventory, "--godot-inventory", godotInventory, "--output", join(output, "manifest-validation.json"),
    "--task-id", "P1-018", "--milestone", "M5", "--validation-preset", "Original endurance sedan", "--command", "node tools/assets/validate_manifest.mjs (exact arguments retained in the outer asset verifier command record)",
    "--human-gate-name", "Meridian S8R final art direction and source/asset rights review", "--human-question", "Q-047"], { cwd: first.project });
  // The normalized scene owns its mesh/material data. A retained temporary
  // GLB would make all_resources ship a second copy of the imported vehicle.
  for (const stage of stages) {
    safeRemoveFile(join(stage.project, assetDirectory, `${asset}.glb`));
    safeRemoveFile(join(stage.project, assetDirectory, `${asset}.glb.import`));
    await godot(`${stage.name}-normalized-only-rescan`, stage.project, ["--import"], { timeout: 600000, allowExistingHdrHeaders: true });
    await godot(`${stage.name}-normalized-only-wrapper`, stage.project, importArgs(join(stage.directory, "normalized-only.godot.json")));
    await godot(`${stage.name}-release-pack`, stage.project, ["--export-pack", "Linux x86_64", join(stage.directory, "endurance-sedan.pck")], { timeout: 600000 });
    await run(`${stage.name}-release-pack-asset-policy`, process.execPath, ["tools/assets/validate_release_pack.mjs", join(stage.directory, "endurance-sedan.pck"), "--asset=endurance-sedan"]);
    await run(`${stage.name}-release-pack-build-policy`, process.execPath, ["scripts/release/pck-inspect.mjs", join(stage.directory, "endurance-sedan.pck")]);
    for (const [path, before] of Object.entries(stage.compared_output_hashes))
      if (hash(join(stage.project, path)) !== before) throw new Error(`Previously compared import output changed during normalized-only pack: ${stage.name}/${path}`);
  }
  compare("two complete shipping PCK files", join(first.directory, "endurance-sedan.pck"), join(second.directory, "endurance-sedan.pck"));
  compareFields("Normalized-only wrapper repeat", load(join(first.directory, "normalized-only.godot.json")), load(join(second.directory, "normalized-only.godot.json")), godotFields);
  report.preserved_hero_after = Object.fromEntries(hero.map(path => [path, hash(path)]));
  if (JSON.stringify(report.preserved_hero_before) !== JSON.stringify(report.preserved_hero_after)) throw new Error("Unrelated Hero geometry/artifact bytes changed during verification");
  for (const [path, before] of Object.entries(report.input_hashes)) if (hash(path) !== before) throw new Error(`Locked input changed during verification: ${path}`);
  for (const [path, before] of Object.entries(report.copied_project_inputs)) if (hash(path) !== before) throw new Error(`Copied project input changed during verification: ${path}`);
  report.metrics = { deterministic_exports: 2, clean_imports: 2, normalized_only_packs: 2, asset_byte_comparisons: report.comparisons.length,
    texture_outputs: Object.keys(first.textures).length, negative_controls: report.negative_controls.length,
    blender: load(join(first.directory, "blender.json")), godot: load(join(first.directory, "godot.json")) };
  report.candidate_outputs = [glb, generated, bindings, blenderInventory, godotInventory, manifestPath, ...Object.keys(first.textures)].map(path => ({ path: pathLabel(join(first.project, path)), sha256: hash(join(first.project, path)) }));
  report.status = options.candidate ? "candidate_verified" : "passed";
}

try {
  report.input_hashes = Object.fromEntries(["tools/vehicles/verify_endurance_sedan.mjs", "tools/assets/toolchain.json"].map(path => [path, hash(path)]));
  report.blender_version = (await run("blender-version", blender, ["--version"])).trim();
  const toolchain = load("tools/assets/toolchain.json");
  if (!report.blender_version.includes(`Blender ${toolchain.blender.version}`) || !report.blender_version.includes(toolchain.blender.build_hash)) throw new Error("Blender toolchain pin mismatch");
  report.blender_executable_sha256 = hash(blender);
  await verifyBlenderDiagnosticPolicy();
  if (options.probeBlenderDiagnostics) report.status = "diagnostic_probe_verified";
  else await verifyAsset();
  for (const [path, before] of Object.entries(report.input_hashes)) if (hash(path) !== before) throw new Error(`Locked input changed during verification: ${path}`);
} catch (error) {
  report.status = "failed";
  report.failures.push(error.stack ?? String(error));
} finally {
  report.finished_utc = new Date().toISOString();
  report.retry_count = 0;
  saveReport();
}
console.log(`CANNONBALL_${options.probeBlenderDiagnostics ? "BLENDER_DIAGNOSTIC" : "ENDURANCE_SEDAN_ASSET"}_${report.status === "failed" ? "FAILED" : "OK"} status=${report.status} evidence=${output}`);
if (report.status === "failed") { console.error(report.failures.join("\n")); process.exitCode = 1; }
