# Questions for Randroid

This is the short human-inbox for questions uncovered during autonomous work.
None of these blocks the current technical implementation because each has a
recorded working default in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

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
