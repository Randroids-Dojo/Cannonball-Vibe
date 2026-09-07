import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const verifier = fileURLToPath(new URL("./smoke.mjs", import.meta.url));
const successOutput = [
  "CANNONBALL_READY engine=4.7.1-stable (official)",
  "content_version=smoke-fixture",
  "CANNONBALL_SAVE_OK",
  "CANNONBALL_SMOKE_OK",
].join("\n");

function runFixture(t, output, exitCode = 0) {
  const root = mkdtempSync(join(tmpdir(), "cannonball-smoke-verifier-test-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, "metadata"));
  const launcher = process.platform === "win32" ? "run.cmd" : "run.sh";
  writeFileSync(join(root, "metadata/manifest.json"), JSON.stringify({
    artifact: { launcher },
    files: [{ path: launcher }],
    content: { content_version: "smoke-fixture" },
  }));
  writeFileSync(join(root, "fixture.mjs"),
    `process.stdout.write(${JSON.stringify(output)}); process.exit(${exitCode});\n`);
  const quote = (value) => `'${value.replaceAll("'", "'\\''")}'`;
  writeFileSync(join(root, launcher), process.platform === "win32"
    ? `@"${process.execPath}" "%~dp0fixture.mjs"\r\n`
    : `#!/bin/sh\nexec ${quote(process.execPath)} ${quote(join(root, "fixture.mjs"))}\n`);
  chmodSync(join(root, launcher), 0o755);
  return spawnSync(process.execPath, [verifier, root, join(root, "transcript.log")], {
    encoding: "utf8", timeout: 10_000,
  });
}

test("a clean packaged runtime with every required marker passes", (t) => {
  const result = runFixture(t, successOutput);
  assert.equal(result.status, 0, result.stderr);
});

test("a native fatal error after success markers fails even when the launcher exits zero", (t) => {
  const result = runFixture(t, `${successOutput}\nFatal error. System.AccessViolationException:\n` +
    "at Godot.NativeInterop.NativeFuncs.godotsharp_internal_object_get_associated_gchandle(IntPtr)\n");
  assert.equal(result.status, 1, result.stderr);
  const failure = JSON.parse(result.stderr.trim().split("\n").at(-1));
  assert.equal(failure.code, 0);
  assert.deepEqual(failure.missing, []);
  assert.ok(failure.forbidden.includes("FATAL"));
});

test("a nonzero runtime exit fails despite every success marker", (t) => {
  const result = runFixture(t, successOutput, 7);
  assert.equal(result.status, 1, result.stderr);
});
