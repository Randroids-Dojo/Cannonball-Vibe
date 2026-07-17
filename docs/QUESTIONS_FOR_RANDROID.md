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

## Representative route map sanity review (P0-004) — rejected

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

First diagnose camera framing, streamed road geometry, and fixture behavior,
then create a replacement deterministic 60-second render-integrity capture with:

```bash
GODOT_BIN=/absolute/path/to/Godot CANNONBALL_CAPTURE_FPS=60 \
  CANNONBALL_CAPTURE_FRAMES=3600 ./scripts/capture-scenario.sh \
  /tmp/p0-004-route-review.avi --short-corridor-soak
```

The short-fixture replacement must keep the roadway visible and show terrain and
scenery while all four chunks are loaded. It can prove the rendering defect is
fixed, but it cannot clear the representative geography gate. Final approval
requires a separate capture of a longer locked corridor that makes route shape,
grade, seams, placement, and obvious geographic mistakes reviewable. The
headless 100-mile transport command remains technical stress evidence and is not
the visual approval mechanism.

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

## Independent source recovery replica (Q-016)

An immutable release protects its tag and assets from modification, but an
administrator can still delete the entire release or repository. Select an
independent durable replica and restore procedure before claiming disaster
recovery for production source retention.
