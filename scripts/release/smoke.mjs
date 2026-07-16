#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";

const packageRoot = resolve(process.argv[2] ?? ".");
const transcriptPath = resolve(process.argv[3] ?? join(tmpdir(), "cannonball-smoke.log"));
const manifest = JSON.parse(readFileSync(join(packageRoot, "metadata", "manifest.json"), "utf8"));
const launcher = join(packageRoot, manifest.artifact.launcher);
const runtimeHome = mkdtempSync(join(tmpdir(), "cannonball-release-smoke-"));
mkdirSync(join(runtimeHome, "empty-dotnet-root"));
const forbiddenTranscript = join(runtimeHome, "playgodot-transcript.jsonl");
const hostileToken = "release-surface-must-remain-absent-7f4e6c9a";

const child = spawn(launcher, ["--smoke-test", "--playgodot"], {
  cwd: runtimeHome,
  detached: process.platform !== "win32",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    HOME: runtimeHome,
    XDG_DATA_HOME: join(runtimeHome, "xdg-data"),
    APPDATA: join(runtimeHome, "appdata"),
    LOCALAPPDATA: join(runtimeHome, "localappdata"),
    DOTNET_ROOT: join(runtimeHome, "empty-dotnet-root"),
    DOTNET_ROOT_X64: join(runtimeHome, "empty-dotnet-root"),
    DOTNET_MULTILEVEL_LOOKUP: "0",
    PLAYGODOT_TOKEN: hostileToken,
    PLAYGODOT_TRANSCRIPT: forbiddenTranscript,
    CANNONBALL_RELEASE_SMOKE: "1",
  },
});

let stdout = "";
let stderr = "";
child.stdout.setEncoding("utf8");
child.stderr.setEncoding("utf8");
child.stdout.on("data", (chunk) => { stdout += chunk; process.stdout.write(chunk); });
child.stderr.on("data", (chunk) => { stderr += chunk; process.stderr.write(chunk); });
const timeout = setTimeout(() => {
  if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"]);
  else process.kill(-child.pid, "SIGKILL");
}, 120_000);
const [code, signal] = await new Promise((done) => child.on("close", (...result) => done(result)));
clearTimeout(timeout);
const transcript = `${stdout}\n${stderr}`;
writeFileSync(transcriptPath, transcript);

const required = [
  "CANNONBALL_READY engine=4.7.1.stable (official)",
  `content_version=${manifest.content.content_version}`,
  "CANNONBALL_SAVE_OK",
  "CANNONBALL_SMOKE_OK",
];
const normalizedTranscript = transcript.replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "").replace(/\r/g, "");
const missing = required.filter((marker) => !normalizedTranscript.includes(marker));
const forbidden = ["PLAYGODOT_", hostileToken, "SCRIPT ERROR", "ERROR:", "FATAL", "Unhandled exception"].filter((marker) => transcript.includes(marker));
const transcriptCreated = existsSync(forbiddenTranscript);
rmSync(runtimeHome, { recursive: true, force: true });
if (code !== 0 || signal || missing.length || forbidden.length || transcriptCreated) {
  console.error(JSON.stringify({ code, signal, missing, forbidden, transcriptCreated }));
  process.exit(1);
}
