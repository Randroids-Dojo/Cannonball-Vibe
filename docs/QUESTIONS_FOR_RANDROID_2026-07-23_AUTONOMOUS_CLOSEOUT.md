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
P0-019 is already `verified_local`; no additional dynamics choice is being
requested here.

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

