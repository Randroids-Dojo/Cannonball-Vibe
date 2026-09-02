#!/usr/bin/env node
// Writes the schema-1 asset manifest for the project-original conifer from the
// tracked inventories and derived artifacts, so provenance is recomputed from
// bytes rather than hand-edited.

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) => {
  if (value.startsWith("--") && index + 1 < values.length) pairs.push([value.slice(2), values[index + 1]]);
  return pairs;
}, []));
if (!args.output) throw new Error("Missing --output");

const hash = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
const artifact = (path, kind) => ({ path, sha256: hash(path), kind });
const blenderInventoryPath = "data/assets/environments/trees/conifer.blender.json";
const blender = JSON.parse(readFileSync(blenderInventoryPath, "utf8"));
const contractPath = "data/assets/environments/trees/conifer.contract.json";
const sourcePath = "data/assets/environments/trees/sources/conifer.blend";
const glbPath = "data/assets/environments/trees/derived/conifer.glb";
const generatedScenePath = "assets/environments/trees/conifer/conifer.generated.tscn";
const importPath = "data/assets/environments/trees/conifer.glb.import";
const contactSheetPath = "data/assets/environments/trees/conifer-contact-sheet.png";
const needleAlbedoPath = "assets/environments/trees/conifer/conifer-needles-albedo.png";
const needleNormalPath = "assets/environments/trees/conifer/conifer-needles-normal.png";
const impostorPath = "assets/environments/trees/conifer/conifer-impostor.png";
const needleShaderPath = "assets/environments/shaders/conifer_needles.gdshader";
const creationScript = "tools/environments/create_conifer.py";
const exportScript = "tools/environments/validate_and_export_environment_asset.py";
const normalizationScript = "tools/vehicles/pack_imported_scene.gd";
const gltfProfile = "tools/assets/profiles/gltf2-binary-v2.json";
const godotProfile = "tools/assets/profiles/godot-4.7.1-v1.json";

if (blender.asset_id !== "conifer") throw new Error("Conifer Blender inventory is missing or stale");

const manifest = {
  schema_version: 1,
  asset_id: "conifer",
  asset_kind: "environment",
  authorship: {
    creator: "Randroid's Dojo",
    creation_date: "2026-09-02",
    method: "Project-original deterministic procedural Blender conifer with EEVEE-rendered needle cards and impostor",
    creation_script: creationScript,
    creation_script_sha256: hash(creationScript),
  },
  license: {
    spdx: "CC0-1.0",
    redistributable: true,
    status: "pending-human-review",
    attribution: "Cannonball-Vibe project-original conifer; no third-party source art. Runtime bark uses the separately locked Poly Haven pine_bark set.",
  },
  source: artifact(sourcePath, "blender-source"),
  transformations: [
    {
      id: "conifer-blender-export-v1",
      tool: "Blender",
      tool_version: "5.1.2+ec6e62d40fa9",
      script: exportScript,
      script_sha256: hash(exportScript),
      profile: gltfProfile,
      profile_sha256: hash(gltfProfile),
      inputs: [artifact(sourcePath, "blender-source"), artifact(contractPath, "asset-contract")],
    },
    {
      id: "conifer-card-render-v1",
      tool: "Blender",
      tool_version: "5.1.2+ec6e62d40fa9",
      script: creationScript,
      script_sha256: hash(creationScript),
      profile: gltfProfile,
      profile_sha256: hash(gltfProfile),
      inputs: [artifact(creationScript, "creation-script")],
    },
    {
      id: "conifer-godot-normalization-v1",
      tool: "Godot",
      tool_version: "4.7.1.stable.mono.official.a13da4feb",
      script: normalizationScript,
      script_sha256: hash(normalizationScript),
      profile: godotProfile,
      profile_sha256: hash(godotProfile),
      inputs: [artifact(glbPath, "gltf-binary"), artifact(importPath, "godot-import-settings")],
    },
  ],
  derived: [
    artifact(glbPath, "gltf-binary"),
    artifact(generatedScenePath, "godot-generated-scene"),
    artifact(importPath, "godot-import-settings"),
    artifact(contactSheetPath, "renderer-contact-sheet"),
    artifact(needleAlbedoPath, "rendered-card-albedo"),
    artifact(needleNormalPath, "rendered-card-normal"),
    artifact(impostorPath, "rendered-impostor"),
    artifact(needleShaderPath, "runtime-shader"),
    artifact(blenderInventoryPath, "blender-inventory"),
  ],
  semantic_contract: {
    required_nodes: blender.required_nodes,
    forward_axis: "-Z",
    up_axis: "+Y",
    unit_meters: 1,
    bounds_meters: blender.bounds_meters,
    wrapper_scene: generatedScenePath,
    automation_id: "environment.asset.conifer",
  },
  budgets: blender.budgets,
};
writeFileSync(args.output, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`CANNONBALL_CONIFER_MANIFEST_OK output=${args.output} artifacts=${manifest.derived.length}`);
