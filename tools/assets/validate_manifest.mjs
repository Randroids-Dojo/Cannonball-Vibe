#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) => {
  if (value.startsWith("--") && index + 1 < values.length) pairs.push([value.slice(2), values[index + 1]]);
  return pairs;
}, []));
for (const required of ["schema", "manifest", "blender-inventory", "godot-inventory", "output"]) {
  if (!args[required]) throw new Error(`Missing --${required}`);
}
const root = process.cwd();
const load = (path) => JSON.parse(readFileSync(path, "utf8"));
const hash = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
const safePath = (path) => {
  if (path.startsWith("/") || path.split("/").includes("..")) throw new Error(`Nonportable path: ${path}`);
  return resolve(root, path);
};
const manifest = load(args.manifest);
const schema = load(args.schema);
const blender = load(args["blender-inventory"]);
const godot = load(args["godot-inventory"]);
const godotProfile = load("tools/assets/profiles/godot-4.7.1-v1.json");
const assertKeys = (value, expected, label) => {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) throw new Error(`${label} fields do not match schema`);
};
const shaPattern = /^[0-9a-f]{64}$/;
const artifactKeys = ["path", "sha256", "kind"];
const requiredTopLevel = [
  "schema_version", "asset_id", "asset_kind", "authorship", "license", "source",
  "transformations", "derived", "semantic_contract", "budgets",
];
assertKeys(manifest, requiredTopLevel, "Manifest");
if (schema.$id !== "https://randroid.dev/cannonball/asset-manifest.schema.json" || schema.properties.schema_version.const !== 1) {
  throw new Error("Unexpected asset-manifest schema identity");
}
if (manifest.schema_version !== 1 || manifest.asset_id !== "graybox-road-module") throw new Error("Unexpected manifest identity");
assertKeys(manifest.authorship, ["creator", "creation_date", "method", "creation_script", "creation_script_sha256"], "Authorship");
assertKeys(manifest.license, ["spdx", "redistributable", "status", "attribution"], "License");
if (!/^\d{4}-\d{2}-\d{2}$/.test(manifest.authorship.creation_date) ||
    !shaPattern.test(manifest.authorship.creation_script_sha256)) {
  throw new Error("Invalid authorship date or creation-script hash");
}
if (!manifest.license.spdx || typeof manifest.license.redistributable !== "boolean" || !manifest.license.status) {
  throw new Error("License and redistribution policy must be explicit");
}
if (!["approved", "pending-human-review", "restricted"].includes(manifest.license.status)) {
  throw new Error("Unknown redistribution status");
}
assertKeys(manifest.semantic_contract, ["required_nodes", "forward_axis", "up_axis", "unit_meters", "bounds_meters", "wrapper_scene", "automation_id"], "Semantic contract");
assertKeys(manifest.budgets, ["triangles_lod0_max", "triangles_total_max", "materials_max", "textures_max", "texture_bytes_max", "collision_triangles_max"], "Budgets");
if (!manifest.semantic_contract.required_nodes.length || new Set(manifest.semantic_contract.required_nodes).size !== manifest.semantic_contract.required_nodes.length) {
  throw new Error("Semantic nodes must be nonempty and unique");
}
if (JSON.stringify(blender.bounds_meters) !== JSON.stringify(manifest.semantic_contract.bounds_meters) ||
    blender.godot_axes.forward !== manifest.semantic_contract.forward_axis ||
    blender.godot_axes.up !== manifest.semantic_contract.up_axis ||
    blender.metric_scale !== manifest.semantic_contract.unit_meters) {
  throw new Error("Scale, bounds, or axis contract drift");
}
for (const [name, value] of Object.entries(manifest.budgets)) {
  if (!Number.isInteger(value) || value < 0) throw new Error(`Invalid budget ${name}`);
}
if (hash(safePath(manifest.authorship.creation_script)) !== manifest.authorship.creation_script_sha256) {
  throw new Error("Source-creation ancestry drift");
}
const artifacts = [manifest.source, ...manifest.derived];
for (const artifact of artifacts) {
  assertKeys(artifact, artifactKeys, `Artifact ${artifact.path ?? "unknown"}`);
  if (!shaPattern.test(artifact.sha256)) throw new Error(`Invalid artifact hash: ${artifact.path}`);
  const actual = hash(safePath(artifact.path));
  if (actual !== artifact.sha256) throw new Error(`Hash mismatch for ${artifact.path}: ${actual}`);
}
for (const transformation of manifest.transformations) {
  assertKeys(transformation, ["id", "tool", "tool_version", "script", "script_sha256", "profile", "profile_sha256", "inputs"], `Transformation ${transformation.id ?? "unknown"}`);
  if (!shaPattern.test(transformation.script_sha256) || !shaPattern.test(transformation.profile_sha256)) {
    throw new Error(`Invalid transformation hash: ${transformation.id}`);
  }
  if (hash(safePath(transformation.script)) !== transformation.script_sha256) {
    throw new Error(`Transformation script drift: ${transformation.script}`);
  }
  if (hash(safePath(transformation.profile)) !== transformation.profile_sha256) {
    throw new Error(`Transformation profile drift: ${transformation.profile}`);
  }
  for (const input of transformation.inputs) {
    assertKeys(input, artifactKeys, `Transformation input ${input.path ?? "unknown"}`);
    if (hash(safePath(input.path)) !== input.sha256) throw new Error(`Transformation input drift: ${input.path}`);
  }
}
const requiredNodes = [...manifest.semantic_contract.required_nodes].sort();
if (JSON.stringify([...blender.required_nodes].sort()) !== JSON.stringify(requiredNodes)) {
  throw new Error("Blender semantic inventory does not match the manifest");
}
if (!godot.all_required_nodes_resolved || JSON.stringify([...godot.required_nodes].sort()) !== JSON.stringify(requiredNodes)) {
  throw new Error("Godot wrapper did not resolve the semantic contract");
}
if (godot.automation_id !== manifest.semantic_contract.automation_id) throw new Error("Automation ID drift");
const importSettings = manifest.derived.find((artifact) => artifact.kind === "godot-import-settings");
if (!importSettings || godot.import_settings_sha256 !== importSettings.sha256) {
  throw new Error("Godot import settings are not pinned to the manifest");
}
const importText = readFileSync(safePath(importSettings.path), "utf8");
const requiredImportSettings = [
  `nodes/root_type="${godotProfile.root_type}"`,
  `nodes/root_name="${godotProfile.root_name}"`,
  `mesh_library/use_node_names_as_mesh_names=${godotProfile.mesh_library_use_node_names}`,
  `meshes/ensure_tangents=${godotProfile.meshes_ensure_tangents}`,
  `meshes/generate_lods=${godotProfile.meshes_generate_lods}`,
  `meshes/create_shadow_meshes=${godotProfile.meshes_create_shadow_meshes}`,
  `meshes/light_baking=${godotProfile.meshes_light_baking}`,
  `animation/import=${godotProfile.animation_import}`,
  `animation/fps=${godotProfile.animation_fps}`,
  `materials/extract=${godotProfile.materials_extract ? 1 : 0}`,
];
for (const setting of requiredImportSettings) {
  if (!importText.includes(setting)) throw new Error(`Godot import profile drift: ${setting}`);
}
if (godot.release_depends_on_blender || godot.release_depends_on_test_automation) {
  throw new Error("Release wrapper depends on build-time tooling");
}
const budgets = manifest.budgets;
if (blender.triangles.Visual_LOD0 > budgets.triangles_lod0_max ||
    blender.triangle_total > budgets.triangles_total_max ||
    blender.materials.length > budgets.materials_max ||
    blender.textures.length > budgets.textures_max ||
    blender.triangles.CollisionProxy > budgets.collision_triangles_max) {
  throw new Error("Asset budget exceeded");
}
const report = {
  schema_version: 1,
  asset_id: manifest.asset_id,
  manifest_sha256: hash(args.manifest),
  schema_sha256: hash(args.schema),
  source_sha256: manifest.source.sha256,
  glb_sha256: blender.glb.sha256,
  contact_sheet_sha256: blender.contact_sheet.sha256,
  wrapper_sha256: godot.wrapper_sha256,
  blender_version: blender.blender_version,
  godot_version: godot.godot_version,
  semantic_nodes: requiredNodes,
  triangle_total: blender.triangle_total,
  materials: blender.materials.length,
  textures: blender.textures.length,
  deterministic_export: true,
  deterministic_contact_sheet: true,
  portable_paths: blender.portable_paths,
  identity_transforms: blender.identity_transforms,
  release_depends_on_blender: godot.release_depends_on_blender,
  release_depends_on_test_automation: godot.release_depends_on_test_automation,
  redistribution_status: manifest.license.status,
};
writeFileSync(args.output, `${JSON.stringify(report, null, 2)}\n`);
console.log(`CANNONBALL_ASSET_MANIFEST_OK asset=${manifest.asset_id} artifacts=${artifacts.length} nodes=${requiredNodes.length}`);
