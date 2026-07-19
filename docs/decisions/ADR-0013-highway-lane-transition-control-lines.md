# ADR-0013: Highway lane-transition control lines

- Status: Accepted
- Date: 2026-07-19

## Context

The variable-lane review fixture exposed a road that was mathematically
continuous but visibly implausible. Its four-to-three-lane section removed an
interior auxiliary lane while preserving an outer exit lane. The generic
alignment algorithm averaged every persistent lane, shifted both through lanes
by 1.2 meters, and interpolated the outer lane across the disappearing lane.
The result contained overlapping lane intervals and read as two road slabs
forced together.

A fixed 120-meter eased transition made the failure more visible. At the
fixture's 70 mph design speed it was shorter than the high-speed lane-reduction
taper calculated from the MUTCD relationship, and smoothstep interpolation made
the peak lateral rate 1.5 times the nominal average.

## Decision

- Treat persistent general-purpose lanes as the roadway control line. Their
  centers do not move merely because an auxiliary, entrance, exit, or transfer
  lane changes outside them.
- Preserve physical lane identity across role changes. The representative
  four-to-three transition keeps the auxiliary physical lane as the transfer
  lane and removes the outer exit lane; it does not move the outer lane through
  an interior lane.
- Reject a generic lane-section transition that adds or removes an interior
  lane while a persistent lane remains outside it. A future authored lateral
  transition may support that case only with explicit correspondence semantics.
- Derive high-speed taper length from the full controlled lateral offset and
  design speed. At 45 mph or above use the MUTCD lane-reduction relationship
  `L = W S`, converting the lateral offset and result through feet. Do not
  silently shorten a designed taper to fit undersized adjacent sections.
- Interpolate the controlled edge linearly through the taper. This produces the
  surveyed constant-rate taper assumed by the length formula instead of an
  S-shaped flare with a steeper midpoint.
- End the normal broken lane divider before a lane-reduction taper and carry the
  transition with the solid edge line. Add exact render samples at taper start,
  midpoint, and end so a coarse 25-meter route sample cannot move the paint or
  pavement transition.
- Gate stable through-lane drift, minimum taper length, maximum lateral slope,
  monotonic width, lane interval tiling, and invalid interior drops in tests and
  the locked validation corpus.

The current procedural fixture conservatively uses the same speed-designed
length for exterior lane additions. Production entrance ramps, acceleration
lanes, mandatory exits, and lane drops will need explicit transition classes
and their applicable design/marking policies; they must not be inferred from a
lane-count delta alone.

## Consequences

- The rendered road, collision ribbon, markings, reflectors, and barriers share
  one stable cross-section profile at every sample.
- Lane-count changes can no longer disguise a lane-ordering error by spreading
  it over a longer distance.
- Lane sections must allocate the complete designed taper on both sides of the
  declared midpoint or fail actionably.
- Future production ramp geometry requires richer semantic transition records,
  but the graybox highway no longer accepts physically impossible lane paths.

## Design basis

- [MUTCD 11th Edition, Part 3, Section 3B.12](https://mutcd.fhwa.dot.gov/pdfs/11th_Edition/part3.pdf)
  specifies high-speed lane-reduction taper length with `L = W S`, requires the
  edge line through the transition, and ends the normal broken lane line before
  the taper.
- [FHWA Federal Lands PDDM, Chapter 9](https://highways.fhwa.dot.gov/federal-lands/pddm/Chapter_09.pdf)
  treats alignment and transition geometry as a designed continuous control
  surface rather than unrelated road-section endpoints.
- [FHWA acceleration-lane research](https://www.fhwa.dot.gov/publications/research/operations/16064/005.cfm)
  distinguishes a full-width acceleration lane from its terminal taper,
  supporting explicit entrance-transition semantics in later production work.

## Rejected alternatives

- **Longer taper without correcting lane identity:** hides the drift but retains
  overlaps and an impossible lane crossing.
- **Average every persistent lane:** lets an auxiliary or exit lane move the
  through roadway away from its control line.
- **Clamp to available section length:** silently violates the speed-designed
  taper and makes fixture spacing determine safety geometry.
- **Smoothstep width interpolation at the nominal taper length:** creates a
  bowed edge whose maximum lateral rate exceeds the locked design rate.
- **Draw the normal broken divider throughout every taper:** conflicts with
  lane-reduction marking practice and double-paints the zero-width endpoint.
