# Questions for Randroid

This is the short human-inbox for questions uncovered during autonomous work.
None of these blocks the current technical implementation because each has a
recorded working default in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

## Adopt PlayGodot after the spike? (Q-011)

The official-Godot spike now has a stable-ID semantic query, bounded signal
waits and input, verified screenshots, capability negotiation, hostile-request
tests, and a CLI. The local macOS suite completed ten fresh-engine runs with
zero failures in 30 seconds. The working default is to keep this debug-only and
optional until three remaining facts exist:

1. the new CI job passes the live suite on macOS, Linux, and Windows;
2. P0-007 produces a real release package whose contents and startup behavior
   prove that no enabled server or rendezvous surface ships; and
3. the first representative interactive menu shows lower diagnosis cost or a
   unique defect compared with CLI evidence plus Computer Use.

When those facts exist, should PlayGodot become required project infrastructure
or remain an opt-in debugging tool? No answer is needed for current gameplay,
map, or release-pipeline work.

## Representative route map sanity review (P0-004)

After the official-corridor packaged streaming candidate is merged, please
inspect a rendered capture and approve whether the reconstructed road is
geographically recognizable and free of obvious map mistakes. This is the
required human gate for completing M2; automated topology, hash, size and
runtime checks cannot substitute for it.

The committed official fixture contains 0.226102 unique route miles. The ledger's
100-mile command therefore performs 443 repetitions and 1,772 verified shard
reads of the same immutable package as a repeated transport stress; it does not
claim 100 unique drivable miles. A longer locked corridor remains necessary for
representative long-route streaming and local-origin evidence.

Create a deterministic 60-second rendered review capture that traverses the
short corridor and crosses every chunk boundary with:

```bash
GODOT_BIN=/absolute/path/to/Godot CANNONBALL_CAPTURE_FPS=60 \
  CANNONBALL_CAPTURE_FRAMES=3600 ./scripts/capture-scenario.sh \
  /tmp/p0-004-route-review.avi --short-corridor-soak
```

Review `/tmp/p0-004-route-review.avi` for route shape, grade, seams, scenery
placement, and obvious geographic mistakes. Record approval or concrete issues
in this section; the headless 100-mile transport command remains technical
stress evidence and is not the visual approval mechanism.

## Source rights approval (Q-013)

Before public release, please approve or reject distribution of the exact NHPN
FeatureServer response and USGS 3DEP source artifacts recorded in
`data/sources/source-lock.json`. The working default permits internal builds and
tests under the agencies' documented U.S. public-domain terms, but does not
claim the required human rights approval.

## Production elevation resolution (Q-014)

Should geographically inspired production corridors use seamless 1/3
arc-second 3DEP elevation (about 10 meters and nationwide) or opportunistically
prefer 1-meter products where coverage exists? The working default is 1/3
arc-second because it is deterministic and has full CONUS coverage.

## Immutable source retention (Q-015)

Where should the large, exact source artifacts live when public URLs eventually
change? The working default is a content-addressed local/CI cache while the
lockfile preserves URLs and SHA-256 values. A durable release-artifact store
should be selected before production content publishing.
