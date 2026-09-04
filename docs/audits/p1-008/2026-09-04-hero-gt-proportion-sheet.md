# Hero GT proportion sheet (third-generation model)

- Date: 2026-09-04
- Task: P1-008 (Q-020 Option A, project-original grand tourer)
- Purpose: the dimensional brief `tools/vehicles/hero_gt/spec.py` implements.
  Every number below is either sourced from a production car or derived from
  the physics contract in the way shown; the design is original and copies
  no single car.

## Fixed by the physics contract

| Quantity | Value |
| --- | --- |
| Wheelbase | 2.84 m |
| Track (front and rear) | 1.64 m |
| Wheel radius | 0.34 m (a 275/35 R20 measures 700 mm outside diameter, 96 mm sidewall) |
| Suspension rest length | 0.62 m |

## Reference cars (mm)

| Car | Length | Width | Height | Wheelbase | Overhang front / rear | Ground clearance | Tyres |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Aston Martin DB12 | 4725 | 1980 | 1295 | 2805 | 925 / 995 | 120 | 275/35 R21, 315/30 R21 |
| Aston Martin Vantage (2024) | 4465 | 1943 | 1273 | 2705 | | 94 | 275/35 R21, 325/30 R21 |
| Ferrari Roma | 4656 | 1974 | 1301 | 2670 | | 113 | 245/35 R20, 285/35 R20 |
| Ferrari 812 Superfast | 4657 | 1971 | 1276 | 2720 | | | 275/35 R20, 315/35 R20 |
| Mercedes-AMG GT (C192) | 4728 | 1984 | 1354 | 2700 | | | 295/30 R21, 305/30 R21 |
| Lexus LC 500 | 4770 | 1920 | 1345 | 2870 | 930 / 970 | 132 | 245/40 R21, 275/35 R21 |
| Chevrolet Corvette C7 | 4493 | 1877 | 1234 | 2710 | | 100 | |

Sources: manufacturer press kits and specification pages for the DB12,
Vantage and Roma; Wikipedia specification tables for the DB12, AMG GT, LC
and C7; the Lexus UK technical specification PDF for the LC overhangs;
tiresize.com for the 275/35 R20 dimensions. Ratios drawn from the table:
wheelbase is 0.57 to 0.61 of length; the front overhang is about a third of
the wheelbase and the rear slightly longer; body width is the mean track
plus 290 to 315 mm; height is 1.8 to 1.9 tyre diameters.

## Derived Hero GT envelope

| Quantity | Value | Derivation |
| --- | --- | --- |
| Front overhang | 0.93 m | 0.33 x wheelbase |
| Rear overhang | 1.00 m | 0.355 x wheelbase |
| Length | 4.77 m | wheelbase plus overhangs (wheelbase/length 0.595) |
| Width over arches | 1.95 m | track plus 0.31 m; the tyre outer face at 0.9615 m leaves 14 mm inside the arch lip |
| Height | 1.30 m | 1.91 tyre diameters |
| Ground clearance | 0.11 m | between the Vantage and the DB12 |
| Cowl (windshield base) | 0.97 m behind the front axle | the sheet proposed 1.10 m; the model uses 0.97 m for a more conventional cabin position |
| Windshield rake | 62 degrees from vertical | C4 Corvette 64 degrees, drag optimum near 25 degrees from horizontal |
| Roof peak | 1.30 m, 1.82 m behind the front axle | |
| Backlight | about 20 degrees from horizontal | fastback convention (Mustang, BMW 4-series) |
| Beltline | 0.98 m at the cowl rising to 1.03 m at the deck | |
| Rocker top / underside | 0.32 m / 0.13 m | |
| Arch radius | 0.395 m | 55 mm over the tyre; the sheet's 65 mm put the arch top above the 0.81 m fender crest, so the front fender crest was raised to 0.865 m |
| Arch blister | 40 to 45 mm proud of the door skin | |
| Panel gaps | 3 mm hood and doors, 4 mm bumper seams | factory specifications for current sports cars run 2 to 4.5 mm |

## Lighting and details

- Headlamps centred 0.66 m high and 0.72 m from the centreline, each unit
  0.32 m long wrapping from the nose back along the fender (FMVSS 108
  allows 22 to 54 in for the lamp centre).
- Tail lamp bar 60 mm tall across 1.70 m; the model places it at 0.80 m,
  below the bumper seam, so the bar cuts one panel.
- Quad exhaust tips of 90 mm at 0.52 m and 0.66 m from the centreline,
  0.30 m high.
- Plate 305 x 152 mm centred 0.52 m high.
- Mirror housings about 200 x 110 x 90 mm at the door front, 2.15 m over
  mirrors.
- Grille aperture 0.95 x 0.30 m centred 0.45 m high.
- Badges 140 mm on the nose and tail.

## Not sourced

Tumblehome (the inward lean of the side glass) had no published figure;
the model uses about 23 degrees from vertical, derived from a 1.86 m
beltline width and a 1.62 m width at the top of the glass at the B-pillar.
