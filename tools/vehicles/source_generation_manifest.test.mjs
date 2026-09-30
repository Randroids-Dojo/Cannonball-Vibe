import assert from "node:assert/strict";
import test from "node:test";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { generationRequired, validateGenerationResult, loadSourceGeneration } from "./source_generation_manifest.mjs";

// Small JS protocol fixture only. It does not model a valid Blender source or
// replace the Python v2 closure/native export validation exercised separately.
const paths = {
  source: "data/assets/vehicles/sources/endurance-sedan.blend",
  specification: "docs/vehicles/endurance-sedan/specification.json",
  binding: "data/assets/vehicles/sources/endurance-sedan.source-binding.json",
  builder: "tools/vehicles/build_endurance_sedan.py",
  fresh: "tools/vehicles/create_endurance_sedan.py",
  final: "tools/vehicles/endurance_sedan/finalize_source.py",
  freshCommand: "data/assets/vehicles/sources/endurance-sedan-generation/commands/fresh-construction.json",
  finalCommand: "data/assets/vehicles/sources/endurance-sedan-generation/commands/finalize-and-reopen.json",
};
const rows = Object.fromEntries(Object.entries(paths).map(([name, path], index) =>
  [name, { path, bytes: index + 1, sha256: String(index + 1).repeat(64) }]));
const fixture = {
  schema: "sedan-manifest-source-generation.v1", status: "validated-ancestry-and-export-binding",
  source: rows.source, specification: rows.specification, binding: rows.binding, builder: rows.builder,
  artifacts: Object.values(rows), derived_paths: [paths.binding, paths.freshCommand, paths.finalCommand],
  phases: [
    { label: "fresh-construction", script: rows.fresh, command: rows.freshCommand, inputs: [rows.builder, rows.specification] },
    { label: "finalize-and-reopen", script: rows.final, command: rows.finalCommand, inputs: [rows.source, rows.specification] },
  ],
};
const actual = path => structuredClone(Object.values(rows).find(row => row.path === path));

test("Python native-command protocol rejects inconsistent destinations and output sets", () => {
  execFileSync("uv", ["run", "--project", "tools/map_pipeline", "--frozen", "python", "-B",
    fileURLToPath(new URL("./test_source_generation_manifest.py", import.meta.url))],
  { cwd: process.cwd(), windowsHide: true, stdio: "pipe", timeout: 60000,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
});

test("Python front companion protocol preserves phase and ownership boundaries", () => {
  execFileSync("uv", ["run", "--project", "tools/map_pipeline", "--frozen", "python", "-B",
    fileURLToPath(new URL("./test_front_finish40_binding.py", import.meta.url))],
  { cwd: process.cwd(), windowsHide: true, stdio: "pipe", timeout: 60000,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
});

test("Python upper companion protocol preserves pane and source boundaries", () => {
  execFileSync("uv", ["run", "--project", "tools/map_pipeline", "--frozen", "python", "-B",
    fileURLToPath(new URL("./test_upper_finish40_binding.py", import.meta.url))],
  { cwd: process.cwd(), windowsHide: true, stdio: "pipe", timeout: 60000,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
});

test("v2 declarations require ancestry even for explicit null", () => {
  assert.equal(generationRequired({}, {}, false), false);
  assert.equal(generationRequired({}, {}, true), true);
  assert.equal(generationRequired({}, { source_generation_verification: {} }, false), true);
  for (const key of ["tire_groove_revision38", "repeated_detail_revision38", "valance_cover_revision39", "front_finish_revision40", "upper_finish_revision40"])
    assert.equal(generationRequired({ original_packaging: { [key]: null } }, {}, false), true);
});

test("complete JS protocol retains the exact two phase roles", () => {
  assert.deepEqual(validateGenerationResult(fixture, actual), fixture);
});

for (const [name, change] of [
  ["ancestry-only cannot claim exported validation", x => x.status = "validated-generation-ancestry-only"],
  ["missing binding artifact", x => x.artifacts = x.artifacts.filter(row => row.path !== paths.binding)],
  ["stale artifact hash", x => x.artifacts[0].sha256 = "0".repeat(64)],
  ["wrong current source", x => x.source.path = "data/assets/vehicles/sources/other.blend"],
  ["missing phase", x => x.phases.pop()],
  ["wrong phase order", x => x.phases.reverse()],
  ["wrong native script", x => x.phases[1].script = x.phases[0].script],
  ["unbound command receipt", x => x.phases[0].command.sha256 = "0".repeat(64)],
  ["duplicate artifact", x => x.artifacts.push(structuredClone(x.artifacts[0]))],
  ["duplicate evidence", x => x.derived_paths.push(x.derived_paths[0])],
  ["missing phase inputs", x => x.phases[0].inputs = []],
  ["unportable fixture dependency", x => x.artifacts[0].path = ".tools/private/source.blend"],
  ["parent escape", x => x.artifacts[0].path = "data/../source.blend"],
  ["absolute path", x => x.artifacts[0].path = "C:/source.blend"],
  ["noncanonical separator", x => x.artifacts[0].path = "data\\source.blend"],
]) {
  test(name, () => {
    const value = structuredClone(fixture);
    change(value);
    assert.throws(() => validateGenerationResult(value, actual));
  });
}

test("Python bridge failure propagates without native or historical fallback", () => {
  let calls = 0;
  assert.throws(() => loadSourceGeneration("data/assets/vehicles/endurance-sedan.blender.json", (program, argv, options) => {
    calls++;
    assert.equal(program, "uv");
    assert.deepEqual(argv.slice(0, 7), ["run", "--project", "tools/map_pipeline", "--frozen", "python", "-B", argv[6]]);
    assert.ok(argv[6].endsWith("source_generation_manifest.py"));
    assert.equal(options.env.PYTHONDONTWRITEBYTECODE, "1");
    throw new Error("actual source binding rejected");
  }), /actual source binding rejected/u);
  assert.equal(calls, 1);
});
