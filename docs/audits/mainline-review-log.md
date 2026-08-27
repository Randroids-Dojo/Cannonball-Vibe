# Mainline adversarial review log

Append-only cursor for the post-merge adversarial review required by
ADR-0025. Each entry records the reviewed mainline range; the cursor for the
next review is the newest entry's head SHA. File actionable findings as
ledger tasks or `docs/OPEN_QUESTIONS.md` entries — never as merge blocks —
and reference their IDs here.

## 2026-08-26 — bootstrap

- Reviewed range: none (adoption of ADR-0025)
- Cursor head: `9276c07d774a4986fb7ef81da3e10a6c7a113ccb` (mainline head at
  adoption)
- PRs covered: none; all mainline history through PR #78 and the direct
  pushes preceding adoption predate this policy and were integrated under
  the pre-ADR-0025 gated flow.
- Findings: none
