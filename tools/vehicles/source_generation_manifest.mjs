import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const source = "data/assets/vehicles/sources/endurance-sedan.blend";
const specification = "docs/vehicles/endurance-sedan/specification.json";
const binding = "data/assets/vehicles/sources/endurance-sedan.source-binding.json";
const builder = "tools/vehicles/build_endurance_sedan.py";
const scripts = ["tools/vehicles/create_endurance_sedan.py", "tools/vehicles/endurance_sedan/finalize_source.py"];
const labels = ["fresh-construction", "finalize-and-reopen"];
const hashPattern = /^[0-9a-f]{64}$/;
const requireValue = (value, reason) => { if (!value) throw new Error(reason); };

export function generationRequired(spec, inventory, bindingExists) {
  const packaging = spec.original_packaging ?? {};
  return bindingExists || inventory.source_generation_verification != null ||
    ["tire_groove_revision38", "repeated_detail_revision38", "valance_cover_revision39", "front_finish_revision40", "upper_finish_revision40"].some(key => Object.hasOwn(packaging, key));
}

function logicalPath(path) {
  requireValue(typeof path === "string" && /^(tools|docs|data)\//u.test(path) &&
    !path.includes("\\") && !path.includes(":") && path.split("/").every(part => part &&
      part !== "." && part !== ".." && !/[. ]$/u.test(part)), "Nonportable source-generation dependency");
  return path;
}

function actualRow(path, root) {
  logicalPath(path);
  const full = realpathSync(resolve(root, path));
  const local = relative(realpathSync(root), full);
  requireValue(local && !isAbsolute(local) && local !== ".." && !local.startsWith("../") && !local.startsWith("..\\"),
    "Source-generation dependency escapes current project");
  const bytes = readFileSync(full);
  return { path, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
}

export function validateGenerationResult(value, readRow = path => actualRow(path, process.cwd())) {
  requireValue(value?.schema === "sedan-manifest-source-generation.v1" &&
    value.status === "validated-ancestry-and-export-binding", "Complete generation/export binding is required");
  requireValue(Array.isArray(value.artifacts) && value.artifacts.length > 0, "Missing generation artifact closure");
  const rows = new Map();
  for (const row of value.artifacts) {
    logicalPath(row.path);
    requireValue(hashPattern.test(row.sha256) && Number.isSafeInteger(row.bytes) && row.bytes >= 0 &&
      !rows.has(row.path.toLowerCase()), "Invalid/duplicate source-generation artifact");
    const actual = readRow(row.path);
    requireValue(actual.path === row.path && actual.sha256 === row.sha256 && actual.bytes === row.bytes,
      `Changed source-generation artifact: ${row.path}`);
    rows.set(row.path.toLowerCase(), row);
  }
  const member = row => {
    const held = rows.get(logicalPath(row?.path).toLowerCase());
    requireValue(held && held.path === row.path && held.sha256 === row.sha256 && held.bytes === row.bytes,
      "Missing/stale source-generation role");
    return held;
  };
  for (const [key, path] of Object.entries({ source, specification, binding, builder })) {
    requireValue(value[key]?.path === path, "Wrong source-generation role: " + key);
    member(value[key]);
  }
  requireValue(Array.isArray(value.phases) && value.phases.length === 2, "Both source phases are required");
  for (const [index, phase] of value.phases.entries()) {
    requireValue(phase.label === labels[index] && phase.script?.path === scripts[index], "Wrong ordered source phase");
    member(phase.script);
    member(phase.command);
    requireValue(Array.isArray(phase.inputs) && phase.inputs.length > 0, "Missing source phase inputs");
    phase.inputs.forEach(member);
  }
  requireValue(Array.isArray(value.derived_paths) && value.derived_paths.length > 0 &&
    new Set(value.derived_paths).size === value.derived_paths.length, "Incomplete/duplicate generation evidence");
  value.derived_paths.forEach(path => {
    logicalPath(path);
    requireValue(rows.has(path.toLowerCase()) && rows.get(path.toLowerCase()).path === path,
      "Unbound generation evidence path");
  });
  return value;
}

export function loadSourceGeneration(inventory, run = execFileSync) {
  logicalPath(inventory);
  const output = run("uv", ["run", "--project", "tools/map_pipeline", "--frozen", "python", "-B",
    fileURLToPath(new URL("./source_generation_manifest.py", import.meta.url)), "--inventory", inventory],
  { cwd: process.cwd(), encoding: "utf8", maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" }, windowsHide: true });
  return validateGenerationResult(JSON.parse(output));
}
