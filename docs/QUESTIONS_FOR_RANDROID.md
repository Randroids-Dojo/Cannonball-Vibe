# Questions for Randroid

This is the short record of questions and human gates surfaced during autonomous
work. Answered items preserve final choices, while rejected or open gates state
what must change before the next review. Unresolved choices and working defaults
remain in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md); rejected human gates may block
their task or milestone.

## Adopt PlayGodot after the spike? (Q-011) — answered

The official-Godot spike now has a stable-ID semantic query, bounded signal
waits and input, verified screenshots, capability negotiation, hostile-request
tests, and a CLI. The local macOS suite completed three consecutive full
16-test runs with zero failures in 28.67 seconds, and the live suite now passes
on GitHub-hosted macOS, Linux, and Windows. P0-007 has also produced
fixture-scoped Linux and Windows packages whose PCK inventory, shipping-binary
scan, and hostile startup probe prove that PlayGodot does not ship or activate.
The working default is to keep PlayGodot debug-only and optional until the one
remaining product fact exists:

1. The first representative interactive menu shows lower diagnosis cost or a
   unique defect compared with CLI evidence plus Computer Use.

Decision recorded 2026-07-16: make PlayGodot required project infrastructure
once that representative-menu comparison satisfies the acceptance threshold.
It remains debug-only, non-shipping, and non-blocking until the comparison is
complete. See [ADR-0008](decisions/ADR-0008-required-playgodot-after-ui-value-gate.md).

## Representative route map sanity review (P0-004) — approved

Human rejection recorded 2026-07-16. The deterministic 60-second capture loaded
and verified all four chunks and passed its technical streaming smoke, but the
roadway disappeared from most sampled frames, the vehicle appeared suspended
against empty space, terrain and scenery were insufficient for seam or placement
review, and the route was not
geographically recognizable. See the
[review record](audits/2026-07-16-p0-004-route-sanity-review.md).

The committed official fixture contains 0.226102 unique route miles. The ledger's
100-mile command therefore performs 443 repetitions and 1,772 verified shard
reads of the same immutable package as a repeated transport stress; it does not
claim 100 unique drivable miles. A longer locked corridor remains necessary for
representative long-route streaming and local-origin evidence.

The diagnosed failure was endpoint overshoot: the high-speed soak exhausted the
363.876-meter road while the chase camera continued following the vehicle. A
separate moderate-speed render-integrity traversal now completes at 300 meters:

```bash
GODOT_BIN=/absolute/path/to/Godot CANNONBALL_CAPTURE_FPS=60 \
  CANNONBALL_CAPTURE_FRAMES=4800 ./scripts/capture-scenario.sh \
  /tmp/p0-004-render-integrity.avi --render-integrity
```

The replacement keeps the roadway, graybox terrain shoulders, and scenery
visible through all three chunk seams while all four chunks remain loaded. Its
exact artifacts, 45-frame adversarial review, and automated comparisons are in
the review record. This fixes the short-fixture rendering defect but cannot
clear the representative geography gate. Final approval requires a separate
capture of a longer locked corridor that makes route shape, grade, seams,
placement, and obvious geographic mistakes reviewable. The headless 100-mile
transport command remains technical stress evidence and is not the visual
approval mechanism.

A new longer candidate is now ready. It uses 15.372898 unique miles of locked
US 36 geometry, 45 connected edges, 49 chunks, nine distributed rendered
viewpoints, and a checksum-locked 3DEP profile conditioned to a 7 percent maximum
grade. Every chunk rendered successfully, the 36-frame adversarial pass found no
empty-space or seam regression, and the source-derived route overview makes the
candidate's shape and elevation profile inspectable. Review the
[overview](images/p0-004-representative-corridor-overview.svg), contact sheet,
and movie identified in the [review record](audits/2026-07-16-p0-004-route-sanity-review.md#longer-representative-candidate).

Project-owner approval recorded 2026-07-17: the longer candidate looks good
enough for the current graybox milestone. This clears the P0-004 representative
geographic sanity gate and unblocks dependent work. The approval is not a claim
of final road, terrain, background, or production-art fidelity; those remain
separate M2 and M5 delivery tasks and human gates.

## Source rights approval (Q-013) — answered

Human approval recorded 2026-07-16: public distribution is approved for the
exact checksum-locked NHPN and USGS 3DEP government data and project-derived
artifacts. Distribution must include source credit, provenance, and a
no-endorsement statement, and must not use agency logos.

## Production elevation resolution (Q-014) — answered

Decision recorded 2026-07-16: use seamless 1/3 arc-second 3DEP as the required
deterministic baseline, with locked 1-meter upgrades allowed per corridor after
coverage, seam, visual/grade value, package-size, and acquisition-time gates
pass.

## Immutable source retention (Q-015) — answered

Decision recorded 2026-07-16: GitHub Releases are the authoritative primary
store, with repository release immutability enabled and verified. Releases are
assembled and verified as drafts before publication locks their tags and assets
and creates attestations. Assets are content-addressed and checksum-verified;
artifacts exceeding the per-file limit are deterministically split with a
checked reconstruction manifest. Local and CI copies remain disposable caches.

## Independent source recovery replica (Q-016) — answered

Decision recorded 2026-07-16: use versioned object storage with enforced Object
Lock, preferring Vercel integration where it satisfies the recovery contract.
Research found that Vercel Blob permits object overwrite, object deletion, and
whole-store deletion and does not expose the required WORM retention controls.

The implementation design, if needed, is a dedicated AWS S3 bucket with
Versioning and `COMPLIANCE` Object Lock. Upon P1-005 activation, Vercel must use
short-lived OIDC credentials for independent, read-only monitoring, but neither GitHub nor
Vercel would be a restore dependency. See
[ADR-0009](decisions/ADR-0009-s3-object-lock-recovery-replica.md).

Follow-up decision recorded 2026-07-16: do not provision that recovery plane
while retained sources remain public, checksum-locked, and reliably
reacquirable. P1-005 is conditional backlog and activates before the project
retains unique, privately licensed, legally critical, expensive-to-reconstruct,
or unreliable-to-reacquire source material. See
[ADR-0010](decisions/ADR-0010-defer-independent-source-replica.md).

## Future M5 visual choices (Q-020 through Q-022) — not blocking current work

[ADR-0012](decisions/ADR-0012-agentic-visual-asset-pipeline.md) now separates
the visual milestone into an agentic asset pipeline, one production-ready
rigged hero vehicle, a modular highway kit, and a regional terrain and
background system. Three human choices remain, but their working defaults let
the prerequisite engineering continue:

1. **Hero vehicle:** which original fictional grand tourer concept and creation
   or commissioning path should become the first production car? The default is
   an unbranded modern grand tourer built around the stable semantic rig; a
   clearly licensed temporary model may validate the pipeline only.
2. **Representative region:** which 300–500 mile region and visual language
   should define the polished slice? The default is a Colorado mountain-to-
   plains corridor extending the current proof geography.
3. **Target hardware and budgets:** what minimum PC should ratify production
   mesh, material, texture, memory, draw-call, LOD, and streaming budgets? The
   default is to enforce static and memory budgets in CI, measure rendering on
   declared available Windows hardware, and ratify a minimum PC before M5
   promotion.

No answer is required to complete the route-semantics work or to build the
asset-pipeline fixture. The choices become blocking before the corresponding
production art is selected or promoted. Full evidence requirements live in
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

## High-speed route-context readability (P1-007) — ready for review

The deterministic route-context implementation has completed its technical
acceptance. The five-frame
[contact sheet](images/p1-007-route-context-contact-sheet.png) covers concurrent
US 36 and US 287 markers, exit 42A with route shields and services, an ordinary
US 36 marker, the I-25 South transfer with right-lane guidance, and the I-25
numbering reset. The local 60 FPS review movie is
`/tmp/p1-007-route-context.avi` with SHA-256
`4a766ec01b9abfc58adf3d9b3a6a5d743af1a0a6c3b6ee2e66afd400ad5de50f`.

One human gate remains: are the marker identities, mile values, exit number,
route shields, destinations, services, and lane guidance readable early enough
for the current graybox milestone? Approval completes P1-007. Rejection should
identify the specific frame and unreadable field so the next capture can target
the defect. This gate does not ask for production sign or environment art.
The requested signage realism and legibility quality pass is now an explicit
P1-009 acceptance requirement rather than an implicit polish note.
