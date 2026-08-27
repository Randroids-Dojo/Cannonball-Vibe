# ADR-0025: Continuous mainline integration with post-merge adversarial review

- Status: Accepted
- Date: 2026-08-26
- Amends: ADR-0003 (integration mechanics only), ADR-0008 (narrows merge-gate
  scope)

## Context

Delivery is single-owner and agent-executed. The pre-merge gate stack —
CodeRabbit review plus six required status contexts — cost agent sessions in
merge babysitting and produced a documented pattern of review-service
timeouts resolved by fallback reviews and administrator bypass. The live
ruleset had also drifted from its decision record: three PlayGodot contexts
became required without an ADR, and squash-only enforcement (2026-07-19)
forced recent merge-commit merges through bypass. Development should continue
without waiting for human feedback outside the ADR-0003 human approval
boundaries, with breakage detected and repaired by agents.

## Decision

- Integration is PR-only and merges exclusively through auto-merge on green:
  squash only, zero required approvals, no pre-merge human or service review.
  CodeRabbit is retired.
- The only required merge contexts are `M0 (ubuntu-latest)` and
  `M0 (windows-latest)`.
- All other suites — PlayGodot semantic UI, deterministic long-route, assets,
  unsigned exports, source retention, and the Windows soak — become
  post-merge tripwires. The `Mainline health` workflow
  (`.github/workflows/mainline-health.yml`) watches their mainline runs and
  maintains one canonical open issue labeled `red-main` while any watched
  workflow is failing.
- Fix-forward only: never revert, never force-push, never bypass-merge to
  land work. A red main preempts all new task selection; repair lands as new
  commits through the same PR flow. Administrator bypass is reserved for
  governance operations.
- Post-merge adversarial review replaces pre-merge review: mainline commits
  are reviewed from the cursor recorded in
  `docs/audits/mainline-review-log.md`, and actionable findings are filed as
  ledger tasks or open questions, never as merge blocks.
- ADR-0008 is narrowed: its rendered-UI suites (and the other suites above)
  remain required for task completion and evidence on their declared
  platforms, but no longer block merge.
- ADR-0003 human approval boundaries are entirely unchanged.
- The ruleset's `code_quality` rule is removed; quality findings belong to
  the post-merge adversarial review.

## Consequences

- Integration no longer waits on review latency; agents arm auto-merge and
  move to the next task.
- There is a bounded window in which unreviewed or tripwire-failing code is
  on main; the red-main flow and fix-forward law are the accepted repair
  mechanism.
- Strict up-to-date enforcement stays off and there is no merge queue, so
  two independently green PRs can merge into a combined state never tested
  together; push-to-main CI plus the red-main tripwire detect it.
- Watched workflow `name:` fields are load-bearing for the
  `workflow_run` filter in `mainline-health.yml`; renaming one silently
  detaches the watcher.
- `source-retention.yml` is not health-watched (its path filter would let a
  stale red run hold the signal open with nothing to re-trigger it); its
  failures surface on the PRs that touch its paths.
- A Windows-soak failure clears on the next daily cron or a manual
  `gh workflow run windows-stress.yml` after the fix.

## Rejected alternatives

- **Direct push to main:** loses the PR unit of integration that required
  status checks and the evidence trail key off, for negligible additional
  throughput over auto-merge.
- **Keep all six contexts required pre-merge:** serializes every merge on the
  slowest suite and preserves the babysitting cost this decision removes.
- **Revert-first red-main policy:** discards in-flight intent; fix-forward
  keeps diagnosis and repair in the same continuous flow.
- **Keep CodeRabbit as advisory:** retains an integration with a documented
  timeout history that no longer gates anything.
