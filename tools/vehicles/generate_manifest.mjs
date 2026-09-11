#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) => {
  if (value.startsWith("--") && index + 1 < values.length) pairs.push([value.slice(2), values[index + 1]]);
  return pairs;
}, []));
if (!args.output) throw new Error("Missing --output");
const vehicle = args.vehicle ?? "hero-gt";
if (!["hero-gt", "endurance-sedan"].includes(vehicle)) throw new Error(`Unknown vehicle ${vehicle}`);

const hash = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
const artifact = (path, kind) => ({ path, sha256: hash(path), kind });
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object"
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;

if (vehicle === "endurance-sedan") {
  const base = "data/assets/vehicles/endurance-sedan";
  const source = "data/assets/vehicles/sources/endurance-sedan.blend";
  const glb = "data/assets/vehicles/derived/endurance-sedan.glb";
  const generated = "assets/vehicles/endurance-sedan/endurance-sedan.generated.tscn";
  const bindings = "assets/vehicles/endurance-sedan/endurance-sedan.generated.textures.json";
  const wrapper = "game/Vehicle/Visuals/EnduranceSedan.tscn";
  const specification = "docs/vehicles/endurance-sedan/specification.json";
  const profile = "tools/assets/profiles/gltf2-endurance-sedan-v1.json";
  const godotProfile = "tools/assets/profiles/godot-4.7.1-v1.json";
  const creation = "tools/vehicles/create_endurance_sedan.py";
  const exportScript = "tools/vehicles/validate_and_export_endurance_sedan.py";
  const normalization = "tools/vehicles/pack_imported_scene.gd";
  const validation = "tools/vehicles/validate_import.gd";
  const uvBake = "data/assets/vehicles/endurance-sedan.uv-bake.json";
  const walk = (directory, extension) => readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name).replaceAll("\\", "/");
    return entry.isDirectory() ? walk(path, extension) : path.endsWith(extension) ? [path] : [];
  }).sort();
  const spec = JSON.parse(readFileSync(specification, "utf8"));
  const blender = JSON.parse(readFileSync(`${base}.blender.json`, "utf8"));
  const godot = JSON.parse(readFileSync(`${base}.godot.json`, "utf8"));
  if (blender.asset_id !== vehicle || godot.asset_id !== vehicle || blender.status !== "passed" ||
      !godot.all_required_nodes_resolved || blender.source.sha256 !== hash(source) || blender.glb.sha256 !== hash(glb) ||
      godot.glb_sha256 !== hash(glb) || godot.generated_scene_sha256 !== hash(generated) ||
      godot.wrapper_sha256 !== hash(wrapper) || godot.specification_sha256 !== hash(specification) ||
      godot.import_settings_sha256 !== hash(`${base}.glb.import`) || godot.profile_sha256 !== hash(godotProfile) ||
      godot.validator_sha256 !== hash(validation) || blender.specification_sha256 !== hash(specification) ||
      blender.budget_contract_sha256 !== hash("tools/vehicles/vehicle_contract.json") ||
      blender.export_validator_sha256 !== hash(exportScript) || blender.gltf_profile_sha256 !== hash(profile) ||
      blender.source_preview_only !== false || blender.validation_scope !== "evaluated_and_exported_runtime_asset" ||
      blender.evaluated_uv_bake?.bake_sha256 !== hash(uvBake) || blender.evaluated_uv_bake?.source_sha256 !== hash(source) ||
      blender.evaluated_uv_bake?.glb_sha256 !== hash(glb) || blender.evaluated_uv_bake?.maximum_allowed_uv_error !== 0.00001 ||
      !Number.isFinite(blender.evaluated_uv_bake?.maximum_measured_uv_error) ||
      !(blender.evaluated_uv_bake?.maximum_measured_uv_error >= 0 && blender.evaluated_uv_bake?.maximum_measured_uv_error <= 0.00001) ||
      JSON.stringify(canonical(blender.export_options)) !== JSON.stringify(canonical(JSON.parse(readFileSync(profile, "utf8")))))
    throw new Error("Sedan inventories do not describe the delivered source, GLB and normalized wrapper");
  if (!godot.transitive_release_dependencies || Object.keys(godot.transitive_release_dependencies).length === 0)
    throw new Error("Sedan inventory is missing its transitive release dependency hashes");
  for (const [path, expected] of Object.entries(godot.transitive_release_dependencies)) {
    if (!path.startsWith("res://") || path.includes("\\") || path.split("/").includes("..") || expected !== hash(path.slice(6)))
      throw new Error(`Sedan inventory release dependency is stale or nonportable: ${path}`);
  }
  if (!godot.runtime_adapter_input_sha256 || Object.keys(godot.runtime_adapter_input_sha256).length === 0)
    throw new Error("Sedan inventory is missing its runtime adapter input hashes");
  for (const [path, expected] of Object.entries(godot.runtime_adapter_input_sha256)) {
    if (!path.startsWith("res://game/Vehicle/") || path.includes("\\") || path.split("/").includes("..") || expected !== hash(path.slice(6)))
      throw new Error(`Sedan inventory runtime adapter input is stale or nonportable: ${path}`);
  }
  const currentAdapterPaths = [".cs", ".tres", ".tscn", ".gdshader", ".uid"].flatMap(extension => walk("game/Vehicle", extension)).map(path => "res://" + path).sort();
  if (JSON.stringify(Object.keys(godot.runtime_adapter_input_sha256).sort()) !== JSON.stringify(currentAdapterPaths))
    throw new Error("Sedan inventory runtime adapter input inventory is stale");
  const constructionInputs = [specification, "tools/vehicles/vehicle_contract.json", "tools/assets/toolchain.json",
    "docs/vehicles/endurance-sedan/research.md", "docs/vehicles/endurance-sedan/reference-values.json",
    "docs/vehicles/endurance-sedan/production-plan.md", "docs/vehicles/endurance-sedan/production-reference-appendix.md",
    creation, ...walk("tools/vehicles/endurance_sedan", ".py")];
  if (spec.original_packaging?.revision_record) constructionInputs.push(spec.original_packaging.revision_record);
  const exportInputs = [source, uvBake, ...constructionInputs, "tools/vehicles/validate_and_export_hero_gt.py", "tools/vehicles/glb_geometry.py"];
  const texturePaths = [...new Set(Object.values(JSON.parse(readFileSync(bindings, "utf8")).materials)
    .flatMap(slots => Object.values(slots)))].sort().map(path => {
      if (!path.startsWith("res://assets/vehicles/endurance-sedan/") || path.includes("\\") || path.split("/").includes(".."))
        throw new Error(`Nonportable sedan texture binding: ${path}`);
      return path.slice("res://".length);
    });
  const derived = [artifact(glb, "gltf-binary"), artifact(generated, "godot-generated-scene"),
    artifact(bindings, "godot-texture-bindings"), artifact(wrapper, "godot-wrapper"),
    artifact(`${base}.glb.import`, "godot-import-settings"),
    artifact(`${base}.blender.json`, "blender-inventory"), artifact(`${base}.godot.json`, "godot-inventory"),
    artifact("assets/vehicles/hero-gt/shaders/car_paint.gdshader", "shared-runtime-shader"),
    ...walk("game/Vehicle", ".cs").map(path => artifact(path, "runtime-adapter-source")),
    ...walk("game/Vehicle", ".uid").map(path => artifact(path, "runtime-adapter-uid")),
    ...walk("game/Vehicle/Setups", ".tres").map(path => artifact(path, "vehicle-setup-resource")),
    ...texturePaths.map(path => artifact(path, "project-original-runtime-texture")),
    ...texturePaths.filter(path => existsSync(path + ".import")).map(path => artifact(path + ".import", "texture-import-settings"))];
  // A contact sheet is evidence only when explicitly supplied. Its presence
  // never turns pending human visual or rights review into an approval.
  if (args["contact-sheet"]) derived.push(artifact(args["contact-sheet"], "renderer-contact-sheet"));
  const transform = (id, tool, version, script, transformProfile, inputs) => ({ id, tool, tool_version: version,
    script, script_sha256: hash(script), profile: transformProfile, profile_sha256: hash(transformProfile),
    inputs: [...new Set(inputs)].map(path => artifact(path, "locked-transformation-input")) });
  const manifest = {
    schema_version: 1, asset_id: vehicle, asset_kind: "vehicle",
    authorship: { creator: "Randroid's Dojo", creation_date: spec.locked_utc.slice(0, 10),
      method: "Project-original editable procedural Blender construction; referenced engineering, fictional Meridian S8R styling and original material inputs",
      creation_script: creation, creation_script_sha256: hash(creation) },
    license: { spdx: "LicenseRef-Meridian-S8R-Output-Rights-Pending-Review", redistributable: false, status: "pending-human-review",
      attribution: "Cannonball-Vibe original Meridian S8R design and procedural material inputs. Label outlines derive from Blender Bfont; its byte-identical font source data carries copyright 2001-2002 NaN Holding BV and GPL-2.0-or-later. Engineering references and exact font ancestry are identified in the provenance dossier. Glyph-mesh/output treatment and final source/asset rights approval remain a human gate." },
    source: artifact(source, "blender-source"),
    transformations: [
      transform("endurance-sedan-construction-v1", "Blender", "5.1.2+ec6e62d40fa9", creation, specification, constructionInputs),
      transform("endurance-sedan-blender-export-v1", "Blender", "5.1.2+ec6e62d40fa9", exportScript, profile, exportInputs),
      transform("endurance-sedan-godot-normalization-v1", "Godot", "4.7.1.stable.mono.official.a13da4feb", normalization, godotProfile, [glb, `${base}.glb.import`]),
      transform("endurance-sedan-wrapper-validation-v1", "Godot", "4.7.1.stable.mono.official.a13da4feb", validation, godotProfile,
        [generated, bindings, wrapper, specification, "tools/vehicles/vehicle_contract.json", ...walk("game/Vehicle", ".cs"), ...walk("game/Vehicle", ".uid"), ...walk("game/Vehicle/Setups", ".tres")]),
    ], derived,
    semantic_contract: { required_nodes: blender.required_nodes, forward_axis: "-Z", up_axis: "+Y", unit_meters: 1,
      bounds_meters: blender.bounds_meters, wrapper_scene: wrapper, automation_id: "vehicle.endurance-sedan.visual-rig" },
    budgets: blender.budgets,
  };
  writeFileSync(args.output, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`CANNONBALL_ENDURANCE_SEDAN_MANIFEST_OK output=${args.output} artifacts=${derived.length} rights=pending-human-review`);
  process.exit(0);
}
const blenderInventoryPath = "data/assets/vehicles/hero-gt.blender.json";
const godotInventoryPath = "data/assets/vehicles/hero-gt.godot.json";
const blender = JSON.parse(readFileSync(blenderInventoryPath, "utf8"));
const godot = JSON.parse(readFileSync(godotInventoryPath, "utf8"));
const sourcePath = "data/assets/vehicles/sources/hero-gt.blend";
const glbPath = "data/assets/vehicles/derived/hero-gt.glb";
const generatedScenePath = "assets/vehicles/hero-gt/hero-gt.generated.tscn";
const textureBindingsPath = "assets/vehicles/hero-gt/hero-gt.generated.textures.json";
const wrapperPath = "game/Vehicle/Visuals/HeroGt.tscn";
const adapterPath = "game/Vehicle/VehicleVisualRig.cs";
const importPath = "data/assets/vehicles/hero-gt.glb.import";
const contactSheetPath = "data/assets/vehicles/hero-gt-contact-sheet.png";
const creationScript = "tools/vehicles/create_hero_gt.py";
const exportScript = "tools/vehicles/validate_and_export_hero_gt.py";
const importScript = "tools/vehicles/validate_import.gd";
const normalizationScript = "tools/vehicles/pack_imported_scene.gd";
const gltfProfile = "tools/assets/profiles/gltf2-binary-v3.json";
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
    artifact(textureBindingsPath, "godot-texture-bindings"),
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
