#!/usr/bin/env node

import { readFileSync } from "node:fs";

const path = process.argv[2];
if (!path) throw new Error("usage: pck-inspect.mjs PACKAGE.pck");
const bytes = readFileSync(path);
let offset = 0;
const u32 = () => { const value = bytes.readUInt32LE(offset); offset += 4; return value; };
const u64 = () => { const value = Number(bytes.readBigUInt64LE(offset)); offset += 8; return value; };
if (u32() !== 0x43504447) throw new Error("Not a Godot PCK (missing GDPC header).");
const format = u32();
if (![2, 3, 4].includes(format)) throw new Error(`Unsupported Godot PCK format: ${format}`);
offset += 12; // Engine major, minor, patch.
const flags = u32();
if ((flags & 1) !== 0) throw new Error("Encrypted PCK directories are forbidden for auditable unsigned exports.");
u64(); // File base.
if (format >= 3) {
  const directoryOffset = u64();
  offset = directoryOffset;
} else {
  offset += 64; // Reserved V2 header words.
}
const count = u32();
if (count > 1_000_000) throw new Error(`Implausible PCK file count: ${count}`);
const paths = [];
for (let index = 0; index < count; index++) {
  const length = u32();
  if (length > bytes.length - offset) throw new Error("Truncated PCK path table.");
  const resourcePath = bytes.subarray(offset, offset + length).toString("utf8").replace(/\0+$/, "");
  offset += length;
  u64();
  u64();
  offset += 16;
  u32();
  paths.push(resourcePath);
}
const forbidden = paths.filter((item) => /(^|\/)addons\/playgodot(\/|$)|playgodot\/bootstrap\.tscn$|playgodot\/server\.gd$/i.test(item));
if (forbidden.length) throw new Error(`PCK contains forbidden PlayGodot resources: ${forbidden.join(", ")}`);
const developmentFiles = paths.filter((item) => /(^|\/)(reports|tests|automation|tools|docs|evidence|src|bin|obj)(\/|$)|\.(cs|csproj|sln)$|packages[^/]*\.lock\.json$/i.test(item));
if (developmentFiles.length) throw new Error(`PCK contains development-only files: ${developmentFiles.join(", ")}`);
console.log(`CANNONBALL_PCK_OK files=${paths.length} playgodot_resources=0`);
