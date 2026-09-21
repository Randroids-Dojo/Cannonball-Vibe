#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
vehicle="all"
blockout="false"
output_root=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vehicle) vehicle="${2:?--vehicle requires a value}"; shift 2 ;;
    --blockout) blockout="true"; shift ;;
    --output-root) output_root="${2:?--output-root requires a value}"; shift 2 ;;
    *) echo "Usage: $0 [--vehicle endurance-sedan|hero-gt|graybox|all] [--blockout] [--output-root PATH]" >&2; exit 2 ;;
  esac
done
case "$vehicle" in
  all) vehicles=(endurance-sedan hero-gt graybox) ;;
  endurance-sedan|hero-gt|graybox) vehicles=("$vehicle") ;;
  *) echo "Unknown vehicle: $vehicle" >&2; exit 2 ;;
esac

# The asset gate imports isolated projects, not this checkout. Prepare this
# actual runtime root explicitly and keep even exit-zero importer diagnostics.
suite_root="${output_root:-$repo_root/reports/p1-018/runtime}"
if [[ -z "$output_root" && "$blockout" == "true" ]]; then suite_root="$suite_root/blockout"; fi
import_output="$(realpath -m "$suite_root/import-$vehicle")"
if [[ -e "$import_output" ]]; then
  echo "Preserve existing import evidence and use a fresh --output-root: $import_output" >&2
  exit 1
fi
mkdir -p "$import_output"
node - "$import_output" <<'NODE'
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const inputs = {};
function walk(directory) {
  for (const entry of fs.readdirSync(directory, {withFileTypes:true})) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (/\.(?:png|jpe?g|hdr|exr|webp|svg)\.import$/i.test(file) && fs.existsSync(file.slice(0,-7))) {
      inputs[file] = {sha256:hash(file), source_sha256:hash(file.slice(0,-7))};
    }
  }
}
walk('assets');
fs.writeFileSync(path.join(process.argv[2], 'before.json'), JSON.stringify({
  started_utc:new Date().toISOString(), imported_cache_existed:fs.existsSync('.godot/imported'),
  wrapper_sha256:hash('scripts/godot.sh'), project_sha256:hash('project.godot'), texture_inputs:inputs
}, null, 2)+'\n');
NODE
set +e
dotnet build "$repo_root/Cannonball.sln" --nologo >"$import_output/build.log" 2>&1
build_exit=$?
import_exit=-1
if [[ "$build_exit" == 0 ]]; then
  ./scripts/godot.sh --headless --path "$repo_root" --import \
    --log-file "$import_output/engine.log" >"$import_output/transcript.log" 2>&1
  import_exit=$?
fi
set -e
node - "$import_output" "$build_exit" "$import_exit" "$repo_root" <<'NODE'
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const [out, buildExit, importExit, root] = process.argv.slice(2);
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const before = JSON.parse(fs.readFileSync(path.join(out,'before.json'),'utf8'));
const failures = [], outputs = {}, textures = {};
let logs = '';
for (const name of ['build.log','engine.log','transcript.log']) {
  const file = path.join(out,name);
  if (!fs.existsSync(file)) { failures.push('missing '+name); continue; }
  outputs[name] = hash(file);
  logs += '\n'+fs.readFileSync(file,'utf8');
}
const known = new Set(['WARNING: Ignoring unsupported header information in HDR: GAMMA=1.',
  'WARNING: Ignoring unsupported header information in HDR: PRIMARIES=0 0 0 0 0 0 0 0.']);
logs = logs.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g,'').replace(/\r/g,'');
const acceptedHeaderWarnings = logs.split('\n').filter(line => known.has(line));
const checked = logs.split('\n').filter(line => !known.has(line)).join('\n');
if (Number(buildExit) !== 0 || Number(importExit) !== 0) failures.push('build/import command failed');
if (/(?:^|\n)(?:ERROR|WARNING|SCRIPT ERROR):|Unhandled exception|Fatal error|AccessViolationException|SIGSEGV|Segmentation fault|Leaked unsafe reference|ObjectDB instances leaked|resources still in use/i.test(checked))
  failures.push('strict import diagnostic policy failed');
for (const [file,input] of Object.entries(before.texture_inputs)) {
  if (hash(file.slice(0,-7)) !== input.source_sha256) failures.push('texture source changed: '+file);
  const settings = fs.readFileSync(file,'utf8');
  for (const match of settings.matchAll(/^path(?:\.[\w]+)?="res:\/\/(\.godot\/imported\/[^"\r\n]+)"/gm)) {
    const cache = match[1];
    if (!fs.existsSync(cache)) { failures.push('missing imported texture: '+cache); continue; }
    textures[cache] = {sha256:hash(cache),bytes:fs.statSync(cache).size,
      header_hex:fs.readFileSync(cache).subarray(0,32).toString('hex')};
  }
}
if (!Object.keys(textures).length) failures.push('no actual imported texture artifacts');
const gate = {task_id:'P1-018',status:failures.length?'failed':'passed',
  scope:'Actual runtime-root editor import before headless scenarios; two existing exact HDR header warnings only.',
  started_utc:before.started_utc,finished_utc:new Date().toISOString(),platform:process.platform,node:process.version,
  command:['./scripts/godot.sh','--headless','--path',root,'--import','--log-file',path.join(out,'engine.log')],
  build_exit:Number(buildExit),import_exit:Number(importExit),before,imported_textures:textures,
  accepted_header_warnings:[...new Set(acceptedHeaderWarnings)],outputs,failures,human_approval_reference:null};
fs.writeFileSync(path.join(out,'gate.json'),JSON.stringify(gate,null,2)+'\n');
if (failures.length) { console.error(failures.join('\n')); process.exit(1); }
console.log(`CANNONBALL_SEDAN_IMPORT_OK textures=${Object.keys(textures).length}`);
NODE

for variant in "${vehicles[@]}"; do
  output="$repo_root/reports/p1-018/runtime/$variant"
  extra_args=()
  if [[ "$blockout" == "true" ]]; then
    output="$repo_root/reports/p1-018/runtime/blockout/$variant"
    extra_args+=(--sedan-blockout)
  fi
  if [[ -n "$output_root" ]]; then output="$output_root/$variant"; fi
  output="$(realpath -m "$output")"
  if [[ -e "$output" ]]; then
    echo "Preserve existing evidence and use a fresh --output-root: $output" >&2
    exit 1
  fi
  mkdir -p "$output"
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set +e
  CANNONBALL_GODOT_LOG_FILE="$output/engine.log" \
  CANNONBALL_SCENARIO_RESULT_FILE="$output/process.json" \
  CANNONBALL_SCENARIO_TIMEOUT_SECONDS=240 \
    ./scripts/run-scenario.sh --fixture representative-corridor \
      --engine-fixed-fps 120 --endurance-sedan-profile --vehicle="$variant" \
      --run-save-path="$output/run-save.json" \
      --sedan-evidence-dir="$output" "${extra_args[@]}" >"$output/transcript.log" 2>&1
  process_exit=$?
  set -e
  node - "$output" "$variant" "$process_exit" "$started" "$blockout" "$output_root" <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const [out, vehicle, exitText, started, blockout, outputRoot] = process.argv.slice(2);
const expected = ['static-ride','keyboard-acceleration','keyboard-braking','controller-acceleration',
  'controller-braking','reverse','steer-left','steer-right','suspension','collision','reset','cameras',
  'natural-rebase','forced-rebase','save-resume','starter-policy'];
if (vehicle === 'endurance-sedan' && blockout !== 'true') expected.push('lod-driving');
// BEGIN scoped neutral static-ride reader
function checkStaticRide(events, summary) {
  const failures = [];
  const fail = reason => failures.push(`neutral static-ride: ${reason}`);
  const finiteVector = v => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);
  const norm = v => Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  const same = (a, b) => Array.isArray(a) && a.length === b.length && a.every((v, i) => v === b[i]);
  const neutral = input => input && ['Throttle', 'Brake', 'Reverse', 'Handbrake', 'Steering'].every(k => input[k] === 0) &&
    input.StationaryHold === false && input.Reset === false;
  const entries = events.filter(r => r.kind === 'static-neutral-entry');
  const exits = events.filter(r => r.kind === 'static-neutral-exit');
  const frames = events.filter(r => r.kind === 'physics-frame' && r.stage === 'static-ride');
  const result = summary.completed_stages?.find(r => r.stage === 'static-ride');
  if (entries.length !== 1 || exits.length !== 1 || frames.length < 240 || !result?.static_neutral)
    return ['neutral static-ride: incomplete entry/exit/frame/summary inventory'];
  const entry = entries[0], e = entry.state, exit = exits[0], s = result.static_neutral;
  if (entry.stage !== 'static-ride' || exit.stage !== 'static-ride' ||
      !Number.isSafeInteger(e.started_usec) || e.started_usec < 0 || typeof e.pad_instance !== 'string' || !/^[1-9][0-9]*$/.test(e.pad_instance) ||
      !Number.isSafeInteger(e.reset_count) || e.reset_count < 0 || e.minimum_frames !== 240 ||
      e.warmup_frames !== 120 || e.required_consecutive !== 24 || e.deadline_usec !== 15000000 ||
      e.first_observation !== 'entry-before-first-neutral-physics-step') fail('entry policy/receiver mismatch');
  if (!same(e.local_linear, [Math.fround(0.04), 0, 0]) || !same(e.local_angular, [0, 0, Math.fround(-0.10)]) ||
      !Array.isArray(e.basis) || e.basis.length !== 3 || !e.basis.every(finiteVector)) fail('seed local fields/basis mismatch');
  else {
    const linear = e.basis[0].map(v => Math.fround(v * Math.fround(0.04)));
    const angular = e.basis[2].map(v => Math.fround(v * Math.fround(-0.10)));
    if (!same(e.assigned_linear, linear) || !same(e.assigned_angular, angular)) fail('seed native basis/velocity mismatch');
  }
  const first = frames[0];
  if (!same(first.velocity, e.assigned_linear) || !same(first.angular_velocity, e.assigned_angular) ||
      !Array.isArray(first.basis) || first.basis.length !== 3 ||
      first.basis.some((column, i) => !same(column, e.basis[i]))) fail('actual first-row seed differs from entry');
  let consecutive = 0, previousUsec = e.started_usec;
  for (let i = 0; i < frames.length; i++) {
    const f = frames[i], n = f.static_neutral;
    if (f.stage_frame !== i + 1 || f.frame !== entry.frame + i || f.vehicle_epoch !== 0 ||
        f.input_source !== 'explicit-neutral-fixture' || f.frozen !== false || !n || n.live !== true ||
        n.override_neutral !== true || n.autopilot !== false || n.resets !== e.reset_count || n.teleports !== 0 ||
        (i > 0 && !neutral(f.input))) { fail(`live/input/frame continuity at${i + 1}`); continue; }
    if (!Number.isSafeInteger(n.observed_usec) || n.observed_usec < previousUsec ||
        n.elapsed_usec !== n.observed_usec - e.started_usec || n.elapsed_usec < 0 || n.elapsed_usec > 15000000)
      fail(`wall clock at${i + 1}`);
    previousUsec = n.observed_usec;
    if (!finiteVector(f.velocity) || !finiteVector(f.angular_velocity) || !finiteVector(f.position) ||
        !Array.isArray(f.basis) || f.basis.length !== 3 || !f.basis.every(finiteVector)) { fail(`nonfinite state at${i + 1}`); continue; }
    if (!Array.isArray(f.wheels) || f.wheels.length !== 4 || f.wheels.some((w, j) => w.index !== j)) {
      fail(`wheel inventory at${i + 1}`); continue;
    }
    const supported = n.grounded === 4 && f.wheels.every(w => w.contact === true && w.body === 'EndurancePad' &&
      w.body_instance === e.pad_instance && finiteVector(w.position) && Number.isFinite(w.compression_m) && w.compression_m > 0);
    const qualifies = i + 1 > 120 && supported && norm(f.velocity) <= 0.1 && norm(f.angular_velocity) <= 0.05;
    consecutive = qualifies ? consecutive + 1 : 0;
    if (n.supported !== supported || n.qualifies !== qualifies || n.consecutive !== consecutive)
      fail(`native readiness disagrees at${i + 1}`);
  }
  if (consecutive < 24 || result.physics_frames !== frames.length || result.teleports !== 0 || result.resets !== 0 ||
      s.minimum_frames !== 240 || s.warmup_frames !== 120 || s.required_consecutive !== 24 || s.consecutive !== consecutive ||
      s.maximum_linear_mps !== 0.1 || s.maximum_angular_radps !== 0.05 || s.deadline_usec !== 15000000 ||
      s.started_usec !== e.started_usec || s.decision_usec !== frames.at(-1).static_neutral?.observed_usec ||
      exit.frame !== frames.at(-1).frame || exit.state.override_cleared !== true) fail('final readiness/restoration summary');
  const next = events.find(r => r.kind === 'physics-frame' && r.stage === 'keyboard-acceleration');
  if (!next || next.input_source !== 'InputMap-action-fixture' || next.static_neutral !== null || next.frozen !== false)
    fail('InputMap acceleration did not resume');
  return failures;
}
// END scoped neutral static-ride reader

const failures = [];
const outputs = {};
const read = name => {
  const file = path.join(out, name);
  if (!fs.existsSync(file)) { failures.push(`missing ${name}`); return ''; }
  const bytes = fs.readFileSync(file);
  outputs[name] = crypto.createHash('sha256').update(bytes).digest('hex');
  return bytes.toString('utf8');
};
const transcript = read('transcript.log');
const engine = read('engine.log');
const summaryText = read('summary.json');
const frameText = read('frames.jsonl');
const processText = read('process.json');
const savePathLine = transcript.split(/\r?\n/).find(line => line.startsWith('CANNONBALL_AUTOMATION_SAVE_PATH '));
try {
  if (path.resolve(JSON.parse(savePathLine?.slice('CANNONBALL_AUTOMATION_SAVE_PATH '.length)).path) !== path.resolve(out, 'run-save.json'))
    failures.push('run save was not isolated to its evidence directory');
} catch { failures.push('automation save-path record missing or invalid'); }
read('run-save.json');
if (Number(exitText) !== 0) failures.push(`scenario command exit ${exitText}`);
if (/(?:^|\n)(?:ERROR|WARNING|SCRIPT ERROR):|Unhandled exception|Fatal error|AccessViolationException|SIGSEGV|Segmentation fault|Leaked unsafe reference|ObjectDB instances leaked|resources still in use/i.test(engine + '\n' + transcript))
  failures.push('engine fatal, warning, exception or resource-leak diagnostic');
if (!transcript.includes(`CANNONBALL_ENDURANCE_SEDAN_OK vehicle=${vehicle} stages=${expected.length} `))
  failures.push('suite completion marker absent');
if (!transcript.includes('CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true'))
  failures.push('controlled shutdown completion marker absent');
for (const stage of expected)
  if (!transcript.includes(`CANNONBALL_ENDURANCE_SEDAN_STAGE_OK vehicle=${vehicle} stage=${stage} `))
    failures.push(`stage marker absent: ${stage}`);
let summary;
try {
  summary = JSON.parse(summaryText);
  if (summary.status !== 'passed' || summary.vehicle !== vehicle ||
      JSON.stringify(summary.expected_stages) !== JSON.stringify(expected) ||
      JSON.stringify(summary.completed_stages.map(s => s.stage)) !== JSON.stringify(expected) ||
      summary.completed_stages.some(s => s.status !== 'passed')) failures.push('summary stage/identity/status mismatch');
  if (summary.frames.sha256 !== outputs['frames.jsonl']) failures.push('per-frame evidence hash mismatch');
  if (summary.physics_hz !== 120) failures.push('wrong physics rate');
  const camera = summary.reconstruction_camera ?? {};
  const cameraFrames = camera.process_frames ?? [];
  const cameraObservations = camera.observations ?? [];
  if (camera.native_display !== false || cameraFrames.length !== 3 ||
      cameraFrames.some((frame, i) => frame !== cameraFrames[0] + i) ||
      JSON.stringify(cameraObservations.map(row => row.render_frame)) !== JSON.stringify(cameraFrames) ||
      (camera.captures ?? []).length !== 0 || cameraObservations.some(row => row.valid !== true ||
        row.observation_boundary !== 'headless-process-no-image' || row.vehicle_epoch !== 1 ||
        !(row.native_arm_child_error_m <= .001) || !(row.hit_length_m >= row.spring_length_m - .01)))
    failures.push('missing first three consecutive native-arm reconstruction observations');
  const contact = summary.contact_shading ?? {};
  if (contact.enabled_by_setup !== (vehicle === 'endurance-sedan') || contact.supported_renderer !== false)
    failures.push('headless contact-shading selection/scope mismatch');
  if (vehicle !== 'graybox') {
    const budgets = JSON.parse(fs.readFileSync('tools/vehicles/vehicle_contract.json', 'utf8')).budgets;
    const inventories = Object.values(summary.runtime_resource_inventory ?? {});
    const lods = new Set(inventories.map(row => row.ActiveLod));
    if (!lods.has(0) || vehicle === 'endurance-sedan' && blockout !== 'true' && (!lods.has(1) || !lods.has(2)) ||
        inventories.some(row => row.DrawnTriangles > budgets.triangles_lod0_max ||
          row.ActiveMaterialResources > budgets.materials_max || row.ActiveTextureResources > budgets.textures_max))
      failures.push('actual active runtime resource budget missing or exceeded');
  }
  let previousRebaseCount = -1;
  let previousRebaseFrame = -1;
  for (const stage of ['natural-rebase', 'forced-rebase']) {
    const observed = summary.rebase_observations?.[stage];
    const frames = observed?.process_frames ?? [];
    if (!observed || new Set(frames).size < 3 || observed.rebase_count <= observed.baseline_rebase_count ||
        observed.rebase_count <= previousRebaseCount || frames[0] <= previousRebaseFrame)
      failures.push(`missing separate process-frame rebase observations: ${stage}`);
    previousRebaseCount = observed?.rebase_count ?? -1;
    previousRebaseFrame = frames.at(-1) ?? -1;
  }
  if (summary.completed_stages.some(s => s.resets < 0 || s.rebases < 0 || !Number.isInteger(s.vehicle_epoch)))
    failures.push('invalid instance-scoped reset/rebase accounting');
  const processResult = JSON.parse(processText);
  if (processResult.status !== 'passed' || processResult.exit_code !== 0 || processResult.timed_out)
    failures.push('process result did not pass');
  const events = frameText.trim().split(/\r?\n/).map(line => JSON.parse(line));
  const frames = events.filter(f => f.kind === 'physics-frame');
  failures.push(...checkStaticRide(events, summary));
  if (frames.length !== summary.physics_frames) failures.push('frame inventory count mismatch');
  for (const stage of expected) if (!frames.some(f => f.stage === stage)) failures.push(`no captured frames: ${stage}`);
  for (const stage of ['keyboard-acceleration','keyboard-braking','controller-acceleration','controller-braking','reverse','steer-left','steer-right','suspension','collision','natural-rebase'])
    if (frames.filter(f => f.stage === stage).some(f => f.frozen)) failures.push(`driving stage frozen: ${stage}`);
  if (expected.includes('lod-driving')) {
    const lodFrames = frames.filter(f => f.stage === 'lod-driving');
    if (lodFrames.some(f => f.frozen) || JSON.stringify([...new Set(lodFrames.map(f => f.lod))].sort()) !== '[0,1,2]')
      failures.push('actual driving LOD crossing evidence missing');
  }
  if (!frames.some(f => f.stage === 'controller-acceleration' && f.input_device === 'Controller' && f.input.Throttle > 0.1))
    failures.push('controller InputMap did not reach conditioned throttle');
  if (!frames.some(f => f.stage === 'keyboard-acceleration' && f.input_device === 'Keyboard' && f.input.Throttle > 0.1))
    failures.push('keyboard InputMap did not reach conditioned throttle');
  const resume = events.find(f => f.kind === 'save-resume-reconstruction');
  if (!resume || resume.state.previous_vehicle_epoch !== 0 || resume.state.vehicle_epoch !== 1 ||
      !frames.some(f => f.vehicle_epoch === 0) || !frames.some(f => f.vehicle_epoch === 1))
    failures.push('save/resume reconstruction epoch not recorded');
  for (const [input, rightSign, upSign] of [['right-down', 1, -1], ['left-up', -1, 1]]) {
    const direction = events.find(f => f.kind === 'camera-direction' && f.state.input === input)?.state;
    if (!direction || direction.stabilization_degrees !== 0 ||
        !(direction.right_dot * rightSign > 0.1) || !(direction.up_dot * upSign > 0.1))
      failures.push(`actual cockpit forward-vector direction not proven: ${input}`);
  }
} catch (error) { failures.push(`invalid structured evidence: ${error.message}`); }
const gate = {
  schema_version: 1, task_id: 'P1-018', vehicle, status: failures.length ? 'failed' : 'passed',
  scope: `official-engine ${blockout === 'true' ? 'blockout ' : ''}functional integration, not final visual or performance approval`,
  started_utc: started, finished_utc: new Date().toISOString(),
  platform: process.platform, node: process.version,
  command: `./scripts/verify-endurance-sedan.sh --vehicle ${vehicle}${blockout === 'true' ? ' --blockout' : ''}${outputRoot ? ' --output-root ' + outputRoot : ''}`,
  scenario_command_exit: Number(exitText), run_save_path: path.resolve(out, 'run-save.json'), failures, outputs, summary_revision: summary?.git_revision ?? null,
  human_approval: null
};
fs.writeFileSync(path.join(out, 'gate.json'), JSON.stringify(gate, null, 2) + '\n');
if (failures.length) { console.error(failures.join('\n')); process.exit(1); }
console.log(`CANNONBALL_ENDURANCE_SEDAN_GATE_OK vehicle=${vehicle} stages=${expected.length}`);
NODE
  if [[ "$variant" == "endurance-sedan" && "$blockout" == "false" ]]; then
    presentation_output="$output/presentation"
    mkdir -p "$presentation_output"
    set +e
    CANNONBALL_GODOT_LOG_FILE="$presentation_output/engine.log" \
    CANNONBALL_SCENARIO_RESULT_FILE="$presentation_output/process.json" \
    CANNONBALL_SCENARIO_TIMEOUT_SECONDS=240 \
      ./scripts/run-scenario.sh --fixture representative-corridor --engine-fixed-fps 120 \
        --sedan-presentation-profile --vehicle=endurance-sedan \
        --run-save-path="$presentation_output/run-save.json" \
        --sedan-evidence-dir="$presentation_output" >"$presentation_output/transcript.log" 2>&1
    presentation_exit=$?
    set -e
    node - "$presentation_output" "$presentation_exit" <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const [out, exit] = process.argv.slice(2);
const expected = ['contract','view-front','view-rear','view-left','view-right','view-top','view-underside',
  'view-front-three-quarter','view-rear-three-quarter','turntable','cockpit','view-footwell','view-rear-cabin','inspection-keyboard','inspection-controller',
  ...['Door_FL','Door_FR','Door_RL','Door_RR','Hood_Hinge','Trunk_Hinge'].flatMap(name => ['open-'+name,'close-'+name]),
  'lights-off','headlights','brake-lights','reverse-lights','left-indicator','right-indicator','hazards',
  'wipers-sweep','wipers-park','steering-small-right','controls-left','controls-right','instruments-forward','instruments-reverse',
  'instruments-low-fuel','instruments-damage','instruments-cooling','instruments-tires',
  'instruments-panel-open','instruments-park-brake','mirrors-configuration','lod-near','lod-middle','lod-far','lod-return'];
const failures = []; const outputs = {};
const read = name => { const file = path.join(out,name); if (!fs.existsSync(file)) { failures.push('missing '+name); return ''; }
  const bytes = fs.readFileSync(file); outputs[name] = crypto.createHash('sha256').update(bytes).digest('hex'); return bytes.toString('utf8'); };
const logs = read('engine.log') + '\n' + read('transcript.log');
const text = read('presentation-summary.json'); const framesText = read('presentation-frames.jsonl'); const processText = read('process.json');
const savePathLine = logs.split(/\r?\n/).find(line => line.startsWith('CANNONBALL_AUTOMATION_SAVE_PATH '));
try {
  if (path.resolve(JSON.parse(savePathLine?.slice('CANNONBALL_AUTOMATION_SAVE_PATH '.length)).path) !== path.resolve(out, 'run-save.json'))
    failures.push('run save was not isolated to its evidence directory');
} catch { failures.push('automation save-path record missing or invalid'); }
if (Number(exit) !== 0) failures.push('presentation command exit '+exit);
if (/(?:^|\n)(?:ERROR|WARNING|SCRIPT ERROR):|Unhandled exception|Fatal error|AccessViolationException|SIGSEGV|Segmentation fault|Leaked unsafe reference|ObjectDB instances leaked|resources still in use/i.test(logs)) failures.push('engine diagnostic');
if (!logs.includes(`CANNONBALL_SEDAN_PRESENTATION_OK stages=${expected.length} posed=true rendered=false`) || !logs.includes('CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true')) failures.push('completion or controlled shutdown marker missing');
for (const stage of expected) if (!logs.includes(`CANNONBALL_SEDAN_PRESENTATION_STAGE_OK stage=${stage} posed=true`)) failures.push('missing stage '+stage);
try {
  const summary = JSON.parse(text), result = JSON.parse(processText);
  if (result.exit_code !== 0 || result.timed_out || result.status !== 'passed') failures.push('process failed');
  if (summary.status !== 'passed' || summary.rendered !== false || JSON.stringify(summary.expected_stages) !== JSON.stringify(expected) ||
      JSON.stringify(summary.completed_stages.map(stage => stage.stage)) !== JSON.stringify(expected) || summary.completed_stages.some(stage => stage.status !== 'passed')) failures.push('presentation inventory mismatch');
  if (summary.frames_sha256 !== outputs['presentation-frames.jsonl']) failures.push('frame hash mismatch');
  const frames = framesText.trim().split(/\r?\n/).map(line => JSON.parse(line));
  if (frames.some(frame => frame.frozen !== true || frame.source_geometry_visible !== false)) failures.push('posed fixture isolation mismatch');
  for (const stage of expected) if (!frames.some(frame => frame.stage === stage)) failures.push('missing frame state '+stage);
} catch(error) { failures.push('invalid evidence: '+error.message); }
fs.writeFileSync(path.join(out,'gate.json'), JSON.stringify({task_id:'P1-018',status:failures.length?'failed':'passed',
  scope:'Headless posed state/semantic checks. Native mirror pixels, visible captures and performance are separate required gates.',
  utc:new Date().toISOString(),platform:process.platform,node:process.version,scenario_command_exit:Number(exit),run_save_path:path.resolve(out,'run-save.json'),expected_stages:expected,outputs,failures,human_approval:null},null,2)+'\n');
if (failures.length) { console.error(failures.join('\n')); process.exit(1); }
console.log(`CANNONBALL_SEDAN_PRESENTATION_GATE_OK stages=${expected.length} rendered=false`);
NODE
  fi
done
