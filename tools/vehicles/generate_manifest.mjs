#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) => {
  if (value.startsWith("--") && index + 1 < values.length) pairs.push([value.slice(2), values[index + 1]]);
  return pairs;
}, []));
if (!args.output) throw new Error("Missing --output");

const hash = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
const artifact = (path, kind) => ({ path, sha256: hash(path), kind });
const blenderInventoryPath = "data/assets/vehicles/hero-gt.blender.json";
const godotInventoryPath = "data/assets/vehicles/hero-gt.godot.json";
const blender = JSON.parse(readFileSync(blenderInventoryPath, "utf8"));
const godot = JSON.parse(readFileSync(godotInventoryPath, "utf8"));
const sourcePath = "data/assets/vehicles/sources/hero-gt.blend";
const glbPath = "data/assets/vehicles/derived/hero-gt.glb";
const generatedScenePath = "assets/vehicles/hero-gt/hero-gt.generated.tscn";
const wrapperPath = "game/Vehicle/Visuals/HeroGt.tscn";
const adapterPath = "game/Vehicle/VehicleVisualRig.cs";
const importPath = "data/assets/vehicles/hero-gt.glb.import";
const contactSheetPath = "data/assets/vehicles/hero-gt-contact-sheet.png";
const creationScript = "tools/vehicles/create_hero_gt.py";
const exportScript = "tools/vehicles/validate_and_export_hero_gt.py";
const importScript = "tools/vehicles/validate_import.gd";
const normalizationScript = "tools/vehicles/pack_imported_scene.gd";
const gltfProfile = "tools/assets/profiles/gltf2-binary-v1.json";
const godotProfile = "tools/assets/profiles/godot-4.7.1-v1.json";

if (blender.asset_id !== "hero-gt" || godot.asset_id !== "hero-gt") {
  throw new Error("Hero GT inventories are missing or stale");
}
const manifest = {
  schema_version: 1,
  asset_id: "hero-gt",
  asset_kind: "vehicle",
  authorship: {
    creator: "Randroid's Dojo",
    creation_date: "2026-07-18",
    method: "Project-original deterministic procedural Blender model",
    creation_script: creationScript,
    creation_script_sha256: hash(creationScript),
  },
  license: {
    spdx: "CC0-1.0",
    redistributable: true,
    status: "pending-human-review",
    attribution: "Cannonball-Vibe project-original Hero GT; no third-party source art",
  },
  source: artifact(sourcePath, "blender-source"),
  transformations: [
    {
      id: "hero-gt-blender-export-v1",
      tool: "Blender",
      tool_version: "5.1.2+ec6e62d40fa9",
      script: exportScript,
      script_sha256: hash(exportScript),
      profile: gltfProfile,
      profile_sha256: hash(gltfProfile),
      inputs: [artifact(sourcePath, "blender-source")],
    },
    {
      id: "hero-gt-godot-normalization-v1",
      tool: "Godot",
      tool_version: "4.7.1.stable.mono.official.a13da4feb",
      script: normalizationScript,
      script_sha256: hash(normalizationScript),
      profile: godotProfile,
      profile_sha256: hash(godotProfile),
      inputs: [artifact(glbPath, "gltf-binary")],
    },
    {
      id: "hero-gt-godot-wrapper-validation-v1",
      tool: "Godot",
      tool_version: "4.7.1.stable.mono.official.a13da4feb",
      script: importScript,
      script_sha256: hash(importScript),
      profile: godotProfile,
      profile_sha256: hash(godotProfile),
      inputs: [artifact(generatedScenePath, "godot-generated-scene")],
    },
  ],
  derived: [
    artifact(glbPath, "gltf-binary"),
    artifact(generatedScenePath, "godot-generated-scene"),
    artifact(wrapperPath, "godot-wrapper"),
    artifact(adapterPath, "runtime-adapter"),
    artifact(importPath, "godot-import-settings"),
    artifact(contactSheetPath, "renderer-contact-sheet"),
    artifact(blenderInventoryPath, "blender-inventory"),
    artifact(godotInventoryPath, "godot-inventory"),
  ],
  semantic_contract: {
    required_nodes: blender.required_nodes,
    forward_axis: "-Z",
    up_axis: "+Y",
    unit_meters: 1,
    bounds_meters: blender.bounds_meters,
    wrapper_scene: wrapperPath,
    automation_id: "vehicle.hero-gt.visual-rig",
  },
  budgets: blender.budgets,
};
writeFileSync(args.output, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`CANNONBALL_HERO_GT_MANIFEST_OK output=${args.output} artifacts=${manifest.derived.length}`);
