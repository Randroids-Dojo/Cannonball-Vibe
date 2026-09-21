// The actual GLB chooses the required corruption coverage, never the report.
import { createHash } from "node:crypto";

const base = Object.freeze({
  "actual-platform-export": null, "canonical-encoding": null, "bounded-uv-rounding": null,
  "stale-source": "source is stale", "changed-limits": "Unsupported corner bake contract",
  "corrupt-reference-hash": "Corrupt or oversized canonical", "changed-position": "Position exceeds",
  "reversed-normal": "Normal exceeds", "nonfinite-position": "Nonfinite corner",
  "changed-uv0": "UV exceeds", "changed-uv1-only": "UV exceeds", "changed-semantic": "metadata changed",
  "changed-image": "Embedded image bytes", "changed-winding": "Position exceeds",
  "external-buffer": "External or multiple", "sparse-accessor": "Unsupported accessor",
  "interleaved-view": "Unsupported buffer view", "overlapping-view": "Overlapping or unclaimed",
  "new-attribute": "Unsupported or missing primitive attribute", "morph-target": "Only uncompressed rigid triangles",
  "new-extension": "Unsupported GLB extension", "wrong-bounds": "Accessor bounds",
  "missing-position-bounds": "POSITION requires min and max", "boolean-buffer-index": "Unsupported buffer view",
  "decimal-component-profile": "Unsupported accessor format", "boolean-scene-metadata": "metadata changed",
  "numeric-material-boolean": "metadata changed", "numeric-extra-boolean": "metadata changed",
  "duplicate-json-key": "Duplicate JSON key", "thin-triangle-collapse": "Degenerate triangle",
  "thin-triangle-winding": "Triangle winding changed",
});
const scalar = Object.freeze({
  "changed-specular-factor": "metadata changed", "boolean-specular-factor": "Invalid scalar specularFactor",
  "out-of-range-specular-factor": "Invalid scalar specularFactor",
  "specular-color-unsupported": "Only declared scalar", "specular-texture-unsupported": "Only declared scalar",
  "required-specular-unsupported": "must remain optional",
});
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
const isHash = value => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);

export function cornerControlRequirements(raw) {
  if (!Buffer.isBuffer(raw) || raw.length < 20 || raw.toString("ascii", 0, 4) !== "glTF" ||
      raw.readUInt32LE(4) !== 2 || raw.readUInt32LE(8) !== raw.length ||
      raw.toString("ascii", 16, 20) !== "JSON" || 20 + raw.readUInt32LE(12) > raw.length)
    throw new Error("Cannot derive corner controls from malformed GLB");
  const document = JSON.parse(raw.toString("utf8", 20, 20 + raw.readUInt32LE(12)));
  if (!Array.isArray(document.meshes) || !document.meshes.length ||
      !document.meshes.every(mesh => Array.isArray(mesh.primitives) && mesh.primitives.length &&
        mesh.primitives.every(p => p.attributes && Object.hasOwn(p.attributes, "TEXCOORD_0"))))
    throw new Error("Cannot derive corner controls without actual mesh UV attributes");
  const hasUv1 = document.meshes.some(mesh => mesh.primitives.some(p => Object.hasOwn(p.attributes, "TEXCOORD_1")));
  const scalarMaterials = (document.materials ?? []).filter(m => Object.hasOwn(m.extensions ?? {}, "KHR_materials_specular")).length;
  return { cases: { ...base, ...(!hasUv1 ? { "dual-uv-fixture": null } : {}), ...(scalarMaterials ? scalar : {}) },
    hasUv1, scalarMaterials, rawSha256: digest(raw) };
}

export function validateCornerControlReport(report, requirements, inputHashes) {
  const expected = requirements.cases;
  const rows = report?.cases;
  if (report?.status !== "passed" || !Array.isArray(rows) || rows.length !== Object.keys(expected).length ||
      new Set(rows.map(r => r.name)).size !== rows.length || rows.some(r => !Object.hasOwn(expected, r.name)))
    throw new Error("Corner control case inventory incomplete, duplicate or unexpected");
  const declared = Object.values(report.inputs ?? {});
  if (![requirements.rawSha256, ...inputHashes].every(h => isHash(h) && declared.includes(h)))
    throw new Error("Corner control actual input binding mismatch");
  if (rows.find(r => r.name === "actual-platform-export")?.result?.raw_glb_sha256 !== requirements.rawSha256 ||
      (report.scalar_specular_materials ?? 0) !== requirements.scalarMaterials)
    throw new Error("Corner control actual GLB coverage mismatch");
  if (!requirements.hasUv1 && (report.synthetic_dual_uv_fixture?.shipping_asset_has_uv1 !== false ||
      !isHash(report.synthetic_dual_uv_fixture?.sha256)))
    throw new Error("Nonshipping dual-UV fixture must be explicit");
  if (requirements.hasUv1 && report.synthetic_dual_uv_fixture !== undefined)
    throw new Error("Unexpected synthetic dual-UV claim for actual dual-UV asset");
  for (const row of rows) {
    const rejection = expected[row.name];
    if (row.status !== "passed" || row.expected_rejection !== rejection ||
        (rejection === null ? row.observed_rejection !== null :
          typeof row.observed_rejection !== "string" || !row.observed_rejection.includes(rejection) ||
          !isHash(row.input_sha256) || row.input_sha256 !== row.output_sha256))
      throw new Error(`Corner control outcome inconsistent: ${row.name}`);
  }
  return { cases: rows.length, negative_cases: Object.values(expected).filter(v => v !== null).length,
    scalar_materials: requirements.scalarMaterials, actual_has_uv1: requirements.hasUv1,
    raw_glb_sha256: requirements.rawSha256 };
}
