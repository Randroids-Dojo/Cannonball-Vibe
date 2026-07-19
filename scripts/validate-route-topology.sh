#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage="Usage: $0 --all-fixtures --evidence <path>"

if [[ $# -ne 3 || "$1" != "--all-fixtures" || "$2" != "--evidence" ]]; then
  echo "$usage" >&2
  exit 2
fi

evidence_path="$3"
case "$evidence_path" in
  /*|[A-Za-z]:/*) ;;
  *) evidence_path="$repo_root/$evidence_path" ;;
esac

reports_dir="$repo_root/reports/M2/P0-012"
mkdir -p "$reports_dir" "$(dirname "$evidence_path")"

commands_log="$reports_dir/commands.jsonl"
: > "$commands_log"

run_checked() {
  local id="$1"
  local log_path="$2"
  shift 2
  local command_text
  printf -v command_text '%q ' "$@"
  if "$@" 2>&1 | tee "$log_path"; then
    node -e 'const fs=require("fs"); fs.appendFileSync(process.argv[1], JSON.stringify({id:process.argv[2],command:process.argv[3].trim(),exit_status:0,log:process.argv[4]})+"\n")' \
      "$commands_log" "$id" "$command_text" "${log_path#"$repo_root/"}"
  else
    local exit_status=${PIPESTATUS[0]}
    node -e 'const fs=require("fs"); fs.appendFileSync(process.argv[1], JSON.stringify({id:process.argv[2],command:process.argv[3].trim(),exit_status:Number(process.argv[4]),log:process.argv[5]})+"\n")' \
      "$commands_log" "$id" "$command_text" "$exit_status" "${log_path#"$repo_root/"}"
    exit "$exit_status"
  fi
}

cd "$repo_root"

run_checked corpus-tests "$reports_dir/corpus-tests.log" \
  uv run --project tools/map_pipeline --frozen pytest \
  tools/map_pipeline/tests/test_pipeline.py \
  tools/map_pipeline/tests/test_validation_corpus.py \
  tools/map_pipeline/tests/test_semantics.py \
  tools/map_pipeline/tests/test_sharding.py -q

run_checked core-route-tests "$reports_dir/core-route-tests.log" \
  env DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln \
  --filter 'FullyQualifiedName~RouteChoiceCatalog|FullyQualifiedName~RouteSemantics|FullyQualifiedName~LaneGeometryProfile'

run_checked variable-lanes "$reports_dir/variable-lanes.log" \
  "$repo_root/scripts/run-scenario.sh" --fixture variable-lanes --profile topology

run_checked representative-interchanges "$reports_dir/representative-interchanges.log" \
  "$repo_root/scripts/run-scenario.sh" --fixture representative-interchanges --profile route-choices

run_checked route-context "$reports_dir/route-context.log" \
  "$repo_root/scripts/run-scenario.sh" --fixture route-context --profile signs

run_checked m0 "$reports_dir/m0.log" \
  "$repo_root/scripts/check.sh"

node - "$repo_root" "$reports_dir" "$evidence_path" <<'NODE'
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const cp = require("child_process");

const [repoRoot, reportsDir, evidencePath] = process.argv.slice(2);
const readJson = relative => JSON.parse(fs.readFileSync(path.join(repoRoot, relative), "utf8"));
const sha256 = filePath => crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
const relative = filePath => path.relative(repoRoot, filePath).replaceAll(path.sep, "/");
const exec = command => cp.execSync(command, {cwd: repoRoot, encoding: "utf8"}).trim();

function marker(logName, prefix) {
  const lines = fs.readFileSync(path.join(reportsDir, logName), "utf8").split(/\r?\n/);
  const line = lines.findLast(item => item.startsWith(prefix + " "));
  if (!line) throw new Error(`Missing ${prefix} in ${logName}.`);
  return Object.fromEntries(line.slice(prefix.length + 1).split(/\s+/).map(field => {
    const split = field.indexOf("=");
    return [field.slice(0, split), field.slice(split + 1)];
  }));
}

function number(value, field) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`Metric ${field} is not numeric: ${value}`);
  return parsed;
}

function requireMetric(condition, message) {
  if (!condition) throw new Error(message);
}

const topology = marker("variable-lanes.log", "CANNONBALL_TOPOLOGY_OK");
const interchanges = marker("representative-interchanges.log", "CANNONBALL_INTERCHANGES_OK");
const routeContext = marker("route-context.log", "CANNONBALL_ROUTE_CONTEXT_OK");
const topologyContract = readJson("data/routes/fixtures/validation/legal-variable-lanes.json").required_metrics;
const interchangeContract = readJson("data/routes/fixtures/validation/legal-interchanges.json").required_metrics;
const contextContract = readJson("data/routes/fixtures/validation/legal-route-context.json").required_metrics;

function continuationGeometryMetrics() {
  const packagePointer = readJson(".tools/scenarios/variable-lanes/current-package.json");
  const routePackage = readJson(path.join(
    ".tools/scenarios/variable-lanes",
    packagePointer.metadata_relative_path
  ));
  const edges = new Map(routePackage.edges.map(edge => [edge.edge_id, edge]));
  const movementsByPair = new Map();
  for (const connector of routePackage.semantics.junction_connectors) {
    const key = `${connector.from_edge_id}->${connector.to_edge_id}`;
    if (!movementsByPair.has(key)) movementsByPair.set(key, new Set());
    movementsByPair.get(key).add(connector.movement);
  }

  const direction = (before, after) => {
    const x = after.projected_x_meters - before.projected_x_meters;
    const y = after.projected_y_meters - before.projected_y_meters;
    const magnitude = Math.hypot(x, y);
    if (!(magnitude > 1e-9)) throw new Error("Continuation endpoint segment is zero length.");
    return [x / magnitude, y / magnitude];
  };
  const deflections = [];
  for (const [key, movements] of movementsByPair) {
    if (movements.size !== 1 || !movements.has("continuation")) continue;
    const [fromEdgeId, toEdgeId] = key.split("->");
    const fromSamples = edges.get(fromEdgeId).samples;
    const toSamples = edges.get(toEdgeId).samples;
    const incoming = direction(fromSamples.at(-2), fromSamples.at(-1));
    const outgoing = direction(toSamples[0], toSamples[1]);
    const dot = Math.max(-1, Math.min(1, incoming[0] * outgoing[0] + incoming[1] * outgoing[1]));
    deflections.push(Math.acos(dot) * 180 / Math.PI);
  }
  if (deflections.length === 0) throw new Error("Variable-lane package has no continuation pairs.");
  return {
    pair_count: deflections.length,
    maximum_source_deflection_degrees: Number(Math.max(...deflections).toFixed(6)),
    limit_degrees: topologyContract.maximum_continuation_deflection_degrees
  };
}

const continuationGeometry = continuationGeometryMetrics();

requireMetric(number(topology.min_lanes, "min_lanes") <= topologyContract.minimum_lane_count, "Minimum lane coverage failed.");
requireMetric(number(topology.max_lanes, "max_lanes") >= topologyContract.maximum_lane_count, "Maximum lane coverage failed.");
requireMetric(number(topology.transitions, "transitions") >= topologyContract.minimum_transitions, "Lane-transition coverage failed.");
requireMetric(topology.gore === String(topologyContract.gore), "Gore coverage failed.");
requireMetric(
  continuationGeometry.maximum_source_deflection_degrees <= continuationGeometry.limit_degrees,
  `Continuation deflection ${continuationGeometry.maximum_source_deflection_degrees} exceeds ${continuationGeometry.limit_degrees} degrees.`
);
requireMetric(topology.terrain_backdrop === String(topologyContract.terrain_backdrop), "Terrain backdrop coverage failed.");
requireMetric(number(topology.terrain_seams, "terrain_seams") >= topologyContract.minimum_terrain_seams, "Junction terrain-seam coverage failed.");
requireMetric(number(topology.rebases, "rebases") >= topologyContract.minimum_rebases, "Rebase coverage failed.");
requireMetric(number(topology.chunk_failures, "topology chunk_failures") <= topologyContract.maximum_chunk_failures, "Topology chunk failure.");

requireMetric(number(interchanges.plans, "plans") >= interchangeContract.plans, "Legal route-plan coverage failed.");
requireMetric(number(interchanges.connectors, "connectors") >= interchangeContract.minimum_connectors, "Connector traversal coverage failed.");
requireMetric(number(interchanges.grade_separated_crossings, "grade_separated_crossings") >= interchangeContract.minimum_grade_separated_crossings, "Overpass coverage failed.");
requireMetric(number(interchanges.minimum_clearance_m, "minimum_clearance_m") >= interchangeContract.minimum_vertical_clearance_meters, "Vertical-clearance gate failed.");
requireMetric(number(interchanges.parallel_carriageways, "parallel_carriageways") >= interchangeContract.minimum_parallel_carriageway_pairs, "Parallel-edge coverage failed.");
requireMetric(number(interchanges.self_intersections, "self_intersections") <= interchangeContract.maximum_self_intersections, "Self-intersection gate failed.");
requireMetric(number(interchanges.invalid_shortcuts, "invalid_shortcuts") <= interchangeContract.maximum_invalid_shortcuts, "Shortcut gate failed.");
requireMetric(number(interchanges.max_abs_grade, "max_abs_grade") <= interchangeContract.maximum_absolute_grade, "Grade gate failed.");
requireMetric(number(interchanges.max_abs_curvature_per_m, "max_abs_curvature_per_m") <= interchangeContract.maximum_absolute_curvature_per_meter, "Curvature gate failed.");
requireMetric(number(interchanges.minimum_sightline_m, "minimum_sightline_m") >= interchangeContract.minimum_sightline_meters, "Sightline gate failed.");
requireMetric(number(interchanges.save_resumes, "save_resumes") >= interchangeContract.plans * interchangeContract.save_resumes_per_plan, "Save/resume gate failed.");
requireMetric(number(interchanges.chunk_failures, "interchange chunk_failures") <= interchangeContract.maximum_chunk_failures, "Interchange chunk failure.");

requireMetric(number(routeContext.concurrent_markers, "concurrent_markers") >= contextContract.minimum_concurrent_markers, "Route-concurrency coverage failed.");
requireMetric(number(routeContext.distinct_mile_values, "distinct_mile_values") >= contextContract.minimum_distinct_mile_values, "Milepoint reset coverage failed.");
requireMetric(number(routeContext.exit_signs, "exit_signs") >= contextContract.minimum_exit_signs, "Exit-sign consistency failed.");
requireMetric(number(routeContext.transfer_signs, "transfer_signs") >= contextContract.minimum_transfer_signs, "Transfer-sign consistency failed.");
requireMetric(number(routeContext.chunk_failures, "context chunk_failures") <= contextContract.maximum_chunk_failures, "Route-context chunk failure.");

const corpusLockPath = path.join(repoRoot, "data/routes/fixtures/validation/p0-012-corpus-lock.json");
const corpus = JSON.parse(fs.readFileSync(corpusLockPath, "utf8"));
const commands = fs.readFileSync(path.join(reportsDir, "commands.jsonl"), "utf8")
  .trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
const reportFiles = fs.readdirSync(reportsDir).filter(name => name.endsWith(".log")).sort();
const reviewFiles = [
  "/tmp/p0-012-topology-review.avi",
  "/tmp/p0-012-route-choice-driving.avi",
  path.join(repoRoot, "docs/images/p0-012-validation-corpus-review.png")
];
for (const filePath of reviewFiles) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Missing required review artifact: ${filePath}`);
  }
}
const m0SummaryPath = path.join(repoRoot, "reports/m0/summary.json");
if (!fs.existsSync(m0SummaryPath)) {
  throw new Error(`Missing M0 summary from the recorded check: ${m0SummaryPath}`);
}
const gitRevision = exec("git rev-parse HEAD");
const godotVersion = exec("./scripts/godot.sh --version").split(/\r?\n/)[0];

const evidence = {
  schema_version: 1,
  task_id: "P0-012",
  milestone: "M2",
  status: "verified_local_pending_human_review",
  git_revision: gitRevision,
  platform: {os: `${os.type()} ${os.release()}`, architecture: os.arch()},
  recorded_at_utc: new Date().toISOString(),
  tool_versions: {
    dotnet_sdk: exec("dotnet --version"),
    uv: exec("uv --version").split(/\s+/)[1],
    godot: godotVersion.replace(/^Godot Engine v/, "")
  },
  deterministic_seed: 20260714,
  corpus_lock: {
    path: relative(corpusLockPath),
    sha256: sha256(corpusLockPath),
    corpus_id: corpus.corpus_id
  },
  input_artifacts: corpus.artifacts,
  scenario_arguments: [
    ["--fixture", "variable-lanes", "--profile", "topology"],
    ["--fixture", "representative-interchanges", "--profile", "route-choices"],
    ["--fixture", "route-context", "--profile", "signs"]
  ],
  commands,
  metrics: {
    legal_fixture_count: corpus.legal_fixture_paths.length,
    invalid_mutation_count: readJson(corpus.invalid_mutation_catalog).mutations.length,
    topology,
    continuation_geometry: continuationGeometry,
    interchanges,
    route_context: routeContext
  },
  acceptance_comparisons: [
    {criterion: "checksum-locked representative coverage", observed: `${corpus.legal_fixture_paths.length} legal fixtures and ${corpus.minimum_highway_transfer_forms} highway-transfer forms`, passed: true},
    {criterion: "continuity, curvature, grade, sightline, intersection, connection, completion, sign, and resume gates", observed: "all declared numeric and semantic scenario contracts passed", passed: true},
    {criterion: "continuation endpoint geometry", observed: `${continuationGeometry.pair_count} pairs; maximum source deflection ${continuationGeometry.maximum_source_deflection_degrees} degrees against ${continuationGeometry.limit_degrees}-degree limit`, passed: true},
    {criterion: "recursive approved-source, derived, and authored ancestry", observed: `${corpus.artifacts.length} locked artifacts with explicit provenance kinds`, passed: true},
    {criterion: "bot traversal and invalid mutation rejection", observed: `${interchanges.plans} legal plans and ${readJson(corpus.invalid_mutation_catalog).mutations.length} invalid mutations`, passed: true},
    {criterion: "human geographic plausibility and route-choice comprehension", observed: "review candidate prepared separately; approval remains pending", passed: false}
  ],
  output_artifacts: reportFiles.map(name => {
    const filePath = path.join(reportsDir, name);
    return {path: relative(filePath), sha256: sha256(filePath)};
  }).concat(reviewFiles.map(filePath => ({
    path: filePath.startsWith(repoRoot) ? relative(filePath) : filePath,
    sha256: sha256(filePath)
  }))).concat([{path: relative(m0SummaryPath), sha256: sha256(m0SummaryPath)}]),
  retry_count: 0,
  failure_history: [],
  recovery_result: {
    status: "not_needed",
    summary: "All recorded aggregate checks passed on their first execution."
  },
  adversarial_review: "docs/audits/2026-07-18-p0-012-validation-corpus-review.md",
  human_gate: {
    name: "Representative interchange and route-context geographic review",
    status: "pending",
    question_reference: "docs/QUESTIONS_FOR_RANDROID_2026-07-18_SYSTEMATIC_BACKLOG.md#q-025--p0-012-geographic-plausibility-and-route-choice-review"
  }
};

fs.writeFileSync(evidencePath, JSON.stringify(evidence, null, 2) + "\n");
console.log(`CANNONBALL_ROUTE_CORPUS_OK legal_fixtures=${corpus.legal_fixture_paths.length} invalid_mutations=${evidence.metrics.invalid_mutation_count} plans=${interchanges.plans} transfer_forms=${corpus.minimum_highway_transfer_forms} human_gate=pending evidence=${relative(evidencePath)}`);
NODE
