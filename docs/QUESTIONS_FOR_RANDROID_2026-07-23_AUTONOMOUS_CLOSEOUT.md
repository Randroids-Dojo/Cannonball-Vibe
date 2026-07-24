# Questions for Randroid — autonomous closeout

Date: 2026-07-23

Autonomous implementation and machine verification have reached the current
human and dependency boundaries. Please record decisions in the original
question documents so the open-question register remains authoritative.

## 1. Q-029 — camera comfort and readability

P0-017 still needs the owner review described in
[QUESTIONS_FOR_RANDROID_2026-07-20_HANDLING_GATES.md](QUESTIONS_FOR_RANDROID_2026-07-20_HANDLING_GATES.md).

This is now the critical M0 dependency chain:

`Q-029 approval → P0-017 complete → P0-018 complete → P0-019 complete → P0-020 machine corpus`

Please complete the five-minute chase and five-minute cockpit review and
record `Q-029: A`, `Q-029: B`, or `Q-029: C — <finding>` in that document.
P0-017, P0-018, and P0-019 are already `verified_local`; no additional input
or dynamics choice is being requested here.

## 2. Q-028 — polished trip overview

P0-013 remains in progress after the requested polish pass. Please review the
updated build using
[QUESTIONS_FOR_RANDROID_2026-07-19_TRIP_MAP.md](QUESTIONS_FOR_RANDROID_2026-07-19_TRIP_MAP.md)
and record the Q-028 decision there.

## 3. P0-020 — sustained handling sessions

No session is requested yet. After Q-029 closes the P0-017/P0-018/P0-019
dependency chain, P0-020 will prepare its checksum-locked handling corpus and
review captures. The required separate 30-minute keyboard and controller
sessions remain a human gate and must not be inferred from the P0-019
automated result.

## 4. Q-020 — Hero GT art direction and rights

P1-008 passes its autonomous source, export, import, rig, LOD, collision,
capture, and clean-checkout gates. It remains `in_progress` for the final
vehicle silhouette, cockpit/chase visibility, damage presentation, and exact
project-original rights approval.

Please record the selected Q-020 option in
[QUESTIONS_FOR_RANDROID_2026-07-18_AUTONOMOUS.md](QUESTIONS_FOR_RANDROID_2026-07-18_AUTONOMOUS.md).

## 5. Q-021 and Q-022 — representative region and target PC

P1-010 passes the deterministic regional-environment fixture gates, and
P1-009 passes its current procedural road/sign fixture gates. Both remain
`in_progress` because fixture performance is not a production target-hardware
approval.

Please select the representative-region direction and minimum Windows target
in
[QUESTIONS_FOR_RANDROID_2026-07-18_AUTONOMOUS.md](QUESTIONS_FOR_RANDROID_2026-07-18_AUTONOMOUS.md).
The same Q-022 target will own vehicle, road, sign, terrain, vegetation,
material, texture, and renderer-budget ratification.

## 6. Q-024 and sign-font provenance

P1-009 now has distinct procedural M1-1 and M1-4 shield silhouettes,
geometric lane arrows, destination hierarchy, stable semantic IDs, and a
day/night review sheet. It intentionally retains Godot's fallback font because
no redistributable production sign-font package has been approved.

Please record the Q-024 visual-language choice, font-provenance choice, and
Q-022 renderer target in
[QUESTIONS_FOR_RANDROID_2026-07-23_P1-009_SIGNAGE.md](QUESTIONS_FOR_RANDROID_2026-07-23_P1-009_SIGNAGE.md).

## No action requested yet

- Do not run the P0-020 30-minute sessions until Q-029 closes the dependency
  chain and the machine corpus is prepared.
- P0-015 traffic cannot start until P0-020 is complete.
- P1-005 recovery-replica provisioning remains correctly deferred while its
  ADR-0010 activation condition is not triggered.
- P1-003 public promotion remains blocked on M5 art tasks, signing
  credentials, release-channel selection, and explicit public-release
  approval.
