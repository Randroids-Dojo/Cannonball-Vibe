import assert from "node:assert/strict";
import test from "node:test";
import { cornerControlRequirements, validateCornerControlReport } from "./corner_control_contract.mjs";

function glb(hasUv1, hasScalar) {
  const doc = { meshes: [{ primitives: [{ attributes: { TEXCOORD_0: 0, ...(hasUv1 ? { TEXCOORD_1: 1 } : {}) } }] }],
    materials: hasScalar ? [{ extensions: { KHR_materials_specular: { specularFactor: 0.12 } } }] : [] };
  const json = Buffer.from(JSON.stringify(doc));
  const padded = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]);
  const header = Buffer.alloc(20);
  header.write("glTF"); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + padded.length, 8);
  header.writeUInt32LE(padded.length, 12); header.write("JSON", 16);
  return Buffer.concat([header, padded]);
}

for (const [uv1, scalar, count] of [[true, false, 31], [false, false, 32], [true, true, 37], [false, true, 38]]) {
  test(`actual GLB uv1=${uv1}, scalar=${scalar} requires ${count} named cases`, () => {
    const required = cornerControlRequirements(glb(uv1, scalar));
    assert.equal(Object.keys(required.cases).length, count);
    assert.equal(Object.hasOwn(required.cases, "dual-uv-fixture"), !uv1);
    assert.equal(Object.hasOwn(required.cases, "required-specular-unsupported"), scalar);
  });
}
test("damaged GLB header cannot select reduced coverage", () => {
  for (const offset of [0, 4, 8, 12, 16]) {
    const raw = glb(false, true); raw[offset] ^= 0xff;
    assert.throws(() => cornerControlRequirements(raw));
  }
});

// Report-only fixture exercises the orchestrator; native corruption cases run
// separately against the actual exported GLB in verify_endurance_sedan.mjs.
const required = cornerControlRequirements(glb(false, true));
const sha = "a".repeat(64);
const fixture = () => ({ status: "passed", inputs: { source: sha, raw: required.rawSha256 },
  scalar_specular_materials: 1, synthetic_dual_uv_fixture: { shipping_asset_has_uv1: false, sha256: sha },
  cases: Object.entries(required.cases).map(([name, rejection]) => ({ name, status: "passed",
    expected_rejection: rejection, observed_rejection: rejection,
    input_sha256: sha, output_sha256: sha, result: { raw_glb_sha256: required.rawSha256 } })) });
test("complete report-only fixture is recognized without claiming native execution", () => {
  assert.equal(validateCornerControlReport(fixture(), required, [sha]).cases, 38);
});
for (const [name, change] of [
  ["missing negative", r => r.cases.pop()],
  ["same-count duplicate", r => r.cases[2] = r.cases[1]],
  ["renamed negative", r => r.cases.at(-1).name = "invented-control"],
  ["failed result", r => r.cases.at(-1).status = "failed"],
  ["wrong rejection", r => r.cases.at(-1).observed_rejection = "unrelated failure"],
  ["fabricated expected rejection", r => r.cases.at(-1).expected_rejection = "unrelated failure"],
  ["rejected artifact changed", r => r.cases.at(-1).output_sha256 = "b".repeat(64)],
  ["false actual UV1 claim", r => r.synthetic_dual_uv_fixture.shipping_asset_has_uv1 = true],
  ["suppressed scalar declaration", r => r.scalar_specular_materials = 0],
  ["wrong actual source binding", r => r.inputs.source = "b".repeat(64)],
  ["wrong actual export", r => r.cases[0].result.raw_glb_sha256 = "b".repeat(64)],
]) test(`reject ${name}`, () => {
  const report = fixture(); change(report);
  assert.throws(() => validateCornerControlReport(report, required, [sha]));
});
