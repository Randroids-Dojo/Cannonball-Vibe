# Questions for Randroid

This is the short human-inbox for questions uncovered during autonomous work.
None of these blocks the current technical implementation because each has a
recorded working default in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

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
complete.

## Representative route map sanity review (P0-004) — rejected

Human rejection recorded 2026-07-16. The deterministic 60-second capture passed
its four-chunk technical streaming smoke, but the roadway disappeared from most
sampled frames, the vehicle appeared suspended against empty space, terrain and
scenery were insufficient for seam or placement review, and the route was not
geographically recognizable. See the
[review record](audits/2026-07-16-p0-004-route-sanity-review.md).

The committed official fixture contains 0.226102 unique route miles. The ledger's
100-mile command therefore performs 443 repetitions and 1,772 verified shard
reads of the same immutable package as a repeated transport stress; it does not
claim 100 unique drivable miles. A longer locked corridor remains necessary for
representative long-route streaming and local-origin evidence.

After diagnosing camera framing, streamed road geometry, and fixture traversal,
create a replacement deterministic 60-second capture with:

```bash
GODOT_BIN=/absolute/path/to/Godot CANNONBALL_CAPTURE_FPS=60 \
  CANNONBALL_CAPTURE_FRAMES=3600 ./scripts/capture-scenario.sh \
  /tmp/p0-004-route-review.avi --short-corridor-soak
```

The replacement must keep the roadway visible, show terrain and scenery across
every chunk boundary, and make route shape, grade, seams, placement, and obvious
geographic mistakes reviewable. The headless 100-mile transport command remains
technical stress evidence and is not the visual approval mechanism.

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

Decision recorded 2026-07-16: GitHub Releases are the authoritative durable
store. Assets are content-addressed and checksum-verified; artifacts exceeding
the per-file limit are deterministically split with a checked reconstruction
manifest. Local and CI copies remain disposable caches.
