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
