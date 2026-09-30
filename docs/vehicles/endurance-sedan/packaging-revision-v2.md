# Meridian S8R packaging revision 2 — 2026-09-10

The first detailed evaluated source exposed physical intersections that the
early blockout could not exercise. The original specification is preserved in
`specification-v1.json`; `specification.json` now locks revision 2 before the
corresponding corrected construction. These are fictional engineering choices,
not corrections to Audi factory specifications or relaxed modeling tolerances.

Evidence is the frozen source05 and the independent triangle/solid witnesses
under `reports/p1-018/qa/production-surface-05/`. In particular, parked assembly
fit does not establish clearance through door, hood, trunk, wiper and suspension
travel. All revised assemblies must be rechecked in their actual evaluated poses.

| Assembly | Revised choice and reason |
| --- | --- |
| Front door hinges | Source X ±0.791 m, Y +0.690 m, Z 0.500 m; place the axis inboard and ahead of the moving door envelope. The first outside-axis placement swept inner door construction into the body. |
| Rear door hinges | Source X ±0.797 m, Y −0.607 m, Z 0.500 m; same inboard mounting principle. |
| Side mirrors | The complete housing, surface and camera follow the corresponding front door, as a door-mounted assembly. Parked world positions and 2.10 m overall width remain fixed. |
| Hood hinge | Source (0, +0.770, 0.945) m. A forward, lower pivot and shaped offset arms clear the cowl, dashboard and windshield. The hood skin remains Y +0.803 to +2.226 m. |
| Trunk hinge and skin | Pivot (0, −1.996, 0.956) m; skin Y −2.020 to −2.432 m. This leaves a fixed rear-deck strip between the backlight seal and moving closure. |
| Auxiliary reservoir | Original 0.90 × 0.48 × 0.28 m outer cell moves to (0, −1.92, 0.56) m, above the mufflers and behind the rear final drive. Nominal usable capacity remains 100 L. Gross modeled volume is verified separately. |
| Main reservoir | Two original underfloor lobes retain 75 L combined nominal capacity. Exhaust and longitudinal rails route around the reservoir envelope; the tunnel brace moves ahead of it. Fuel plumbing remains below the cabin floor and enters its sealed reservoir fitting. |
| Wipers | Blade/rail/clip assemblies move up the windshield plane while the parked pivot positions remain fixed. Elevated root arms pass over the other parked blade without moving the rubber away from the glass. |
| Wheel wells | Closed wheel-arch liners and inboard wheel tubs hide the rotating tires from the luggage/cabin spaces. Their real evaluated surfaces, all nearby engine/underbody assemblies and full tire travel require independent clearance verification. |

Length, body/mirror width, roof height, wheelbase, tracks, tires, brakes, spring
setup, fixed gameplay mass/CG and all driving limits are unchanged. The 2400 kg,
54% front, 0.55 m CG setup remains an explicit aggregate gameplay assumption;
this model does not calculate a validated component mass distribution. Moving
the 74.5 kg auxiliary fuel load alone would shift an otherwise fixed aggregate
CG about 3.7 mm rearward and 3.1 mm upward. No measured handling claim follows.

The engine, transmission, cooling, exhaust and fuel-transfer components are
inspectable modeled assemblies. They do not implement thermal, powertrain or
fuel-transfer simulation. Source rights, art direction, usability and enjoyment
approval remain pending.
