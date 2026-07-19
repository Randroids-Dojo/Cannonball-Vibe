# Modern highway visual standards baseline

Date: 2026-07-18

## Purpose

P1-009 needs a contemporary, recognizable Colorado freeway baseline without
turning a game renderer into a claim of traffic-control compliance. The kit is
therefore informed by current official standards, preserves semantic data and
automation IDs, and leaves exact typography, dimensions, placement engineering,
and final art direction behind a human quality gate.

## Current official references

- FHWA identifies the [MUTCD 11th Edition with Revision 1][fhwa-current] as the
  current national edition.
- Colorado's [current MUTCD page][cdot-mutcd] says the state adopted the 11th
  Edition and Colorado Supplement effective January 18, 2026, and links the
  governing [Colorado Supplement][colorado-supplement].
- [MUTCD Chapter 2E][mutcd-2e] specifies freeway and expressway guide-sign
  principles. The implementation-relevant baseline is white legends, symbols,
  arrows, and borders on green guide backgrounds; guide-sign visibility uses
  retroreflective or illuminated treatment; route shields retain their
  distinctive shapes; and blue is reserved for service and information uses.
- CDOT publishes a [2026 Sign Design Manual][cdot-sign-manual] and current
  [signing and pavement-marking resources][cdot-signing]. These are the next
  authority for a corridor-specific typography, layout, support, and placement
  pass.

## Decisions applied to the technical kit

1. Mainline destination and transfer boards use green, high-contrast faces with
   white borders and legends.
2. Exit-only lane panels use a distinct yellow hierarchy instead of encoding
   lane status only in body copy.
3. Fuel and food information uses separate blue service panels. A highway
   transfer does not use the service-blue treatment.
4. US and Interstate route references use different procedural silhouettes;
   Interstate shields also carry the red header cue.
5. Lane arrows, exit number, route shields, destinations, and service panels
   are separate semantic nodes under the stable sign root.
6. Pavement markings, signs, and raised markers use reusable emissive materials
   as the current game approximation of retroreflection.
7. The same procedural generator can swap between `production` and `graybox`
   material profiles through `--graybox-road-assets` without changing topology
   or automation IDs.

## Known gaps before production approval

- Godot's default font and the current procedural glyphs are not a substitute
  for a licensed, validated highway-sign type system.
- The boards are scaled for current gameplay review distances, not certified
  field installation dimensions.
- Shield silhouettes are project-original approximations and still need exact
  shape, spacing, numeral, and legal/brand review.
- Supports, breakaway hardware, bridges, overpasses, retaining walls, drainage,
  vegetation, terrain materials, weathering, decals, and regional roadside
  furniture remain production work.
- Day/night high-speed pop-in, renderer frame time, draw calls, texture
  residency, and minimum-PC budgets remain open under Q-022.

This baseline supports autonomous iteration and deterministic review. It must
not be described as MUTCD- or CDOT-compliant traffic-control engineering.

[fhwa-current]: https://mutcd.fhwa.dot.gov/kno_11th_Editionr1.htm
[cdot-mutcd]: https://www.codot.gov/safety/traffic-safety/assets/documents/mutcd
[colorado-supplement]: https://www.codot.gov/safety/traffic-safety/assets/documents/mutcd/colorado-supplement-mutcd_final-12302025.pdf
[mutcd-2e]: https://mutcd.fhwa.dot.gov/pdfs/11th_Edition/Chapter2e.pdf
[cdot-sign-manual]: https://www.codot.gov/safety/traffic-safety/assets/documents/Sign%20Design%20Manual.pdf
[cdot-signing]: https://www.codot.gov/safety/traffic-safety/design/signing-and-markings
