#!/usr/bin/env node

import { readFileSync } from "node:fs";

const path = process.argv[2];
if (!path) throw new Error("usage: validate_release_pack.mjs PACKAGE.pck");
const assetArgument = process.argv.find((value) => value.startsWith("--asset="));
const assetId = assetArgument?.slice("--asset=".length) ?? "graybox-road-module";
const bytes = readFileSync(path);
let offset = 0;
const u32 = () => { const value = bytes.readUInt32LE(offset); offset += 4; return value; };
const u64 = () => { const value = Number(bytes.readBigUInt64LE(offset)); offset += 8; return value; };
if (u32() !== 0x43504447) throw new Error("Not a Godot PCK");
const format = u32();
if (![2, 3, 4].includes(format)) throw new Error(`Unsupported PCK format: ${format}`);
offset += 12;
const flags = u32();
if ((flags & 1) !== 0) throw new Error("Encrypted PCK cannot be audited");
u64();
if (format >= 3) offset = u64(); else offset += 64;
const count = u32();
if (count > 1_000_000) throw new Error(`Implausible PCK file count: ${count}`);
const paths = [];
for (let index = 0; index < count; index++) {
  const length = u32();
  if (length > bytes.length - offset) throw new Error("Truncated PCK path table");
  paths.push(bytes.subarray(offset, offset + length).toString("utf8").replace(/\0+$/, ""));
  offset += length;
  u64();
  u64();
  offset += 16;
  u32();
}
const forbidden = paths.filter((value) => value.endsWith(".blend") || value.includes("tools/") || value.includes("data/assets/"));
if (forbidden.length) throw new Error(`Release pack contains build-only asset inputs: ${forbidden.join(", ")}`);
const wrapperPresent = paths.some((value) => value.endsWith(`/${assetId}.tscn`) ||
  value.endsWith(`/${assetId}.tscn.remap`) ||
  (assetId === "hero-gt" && (value.endsWith("/HeroGt.tscn") || value.endsWith("/HeroGt.tscn.remap"))));
const escapedAssetId = assetId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const importedPattern = new RegExp(`(^|/)\\.godot/imported/${escapedAssetId}\\.glb-[0-9a-f]+\\.scn$`, "i");
const visualAssetPresent = assetId === "hero-gt"
  ? paths.some((value) => value.endsWith("/hero-gt.generated.tscn.remap") ||
      /(^|\/)\.godot\/exported\/[0-9]+\/export-[0-9a-f]+-hero-gt\.generated\.scn$/i.test(value))
  : paths.some((value) => importedPattern.test(value));
if (!wrapperPresent || !visualAssetPresent) throw new Error("Release pack is missing the wrapper or generated visual asset");
console.log(`CANNONBALL_ASSET_RELEASE_OK asset=${assetId} files=${paths.length} wrapper=1 visual_asset=1 build_dependencies=0`);
