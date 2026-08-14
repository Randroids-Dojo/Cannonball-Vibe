# Ride-height oscillation while driving: root cause

Date: 2026-08-14

Reported: the car bounces up and down slightly while driving, as if the model
were hitting itself.

Tasks touched: P0-019 (vehicle dynamics), P0-021 / `tools/map_pipeline`
(elevation sampling)

## Outcome

The suspension is not at fault, and nothing is colliding. The road surface itself
undulates, and the suspension reproduces it faithfully. **The road takes its
elevation directly from bare-earth terrain with no vertical-curve grading**, so
it inherits terrain micro-relief that a real engineered highway would have cut
and filled away.

A second, smaller defect was found and fixed along the way: elevation was sampled
from the raster by nearest neighbour rather than interpolated. That is a genuine
fidelity bug, but measurement shows it is **not** the cause of the reported
bounce.

## Ruling out the suspension

The tuning is well damped and cannot self-oscillate. Spring 42,000 N/m against
1,450 kg over four corners gives a damping ratio of **0.70**, so a disturbance
settles in roughly one overshoot. Something had to be driving it.

The discriminating measurement was bounce frequency against speed, taken from
per-frame chassis and contact height over 30 s runs:

| Speed | Ride-height peak-to-peak | Peak frequency | Wavelength |
| ---: | ---: | ---: | ---: |
| 10 m/s | 0.005 m | 0.20 Hz | 50 m |
| 20 m/s | 0.024 m | 0.37 Hz | 55 m |
| 40 m/s | 0.059 m | 0.83 Hz | 48 m |

Frequency scales **4.17x for 4x speed** while the wavelength stays fixed near
50 m. Suspension resonance would sit at its natural 1.71 Hz regardless of speed.
The car is tracing the road.

The measurement is chassis height minus tyre contact height, so this is real
chassis motion rather than a visual-rig artefact. No collider is involved: the
chassis box retains 0.20 m of clearance even at full suspension compression, and
the suspension ray masks layer 1 while the vehicle sits on layer 2.

## The road follows raw terrain

Sampling the elevation raster densely along the route, the terrain's own
short-wavelength relief is **94.1 mm RMS** below an 80 m wavelength. The road
measured in game carries **41.7 mm RMS** in the same band, the difference being
attenuation from the 25 m centreline sampling acting as a low-pass.

So the road is a faithful, slightly smoothed rendering of bare terrain. Nothing
grades it. That is the bounce.

## The sampling defect, and why it is not the cause

`ElevationSampler.sample` used `rasterio`'s point `sample()`, which is nearest
neighbour with no interpolation. Every 25 m route vertex therefore took the value
of whichever cell centre it landed in, over a raster whose cells are 10.31 m.
Marching a 25 m step across 10.31 m cells beats against that grid, which is why
the dominant response sits near twice the sample spacing.

Measured at the sample points on the fixture route:

| Sampling | Short-wavelength RMS | Max step between samples |
| --- | ---: | ---: |
| nearest neighbour | 104.3 mm | 1336 mm |
| bilinear | 46.6 mm | 1053 mm |

That looked decisive, and this audit initially claimed it as the root cause.
Rebuilding the route package with bilinear sampling and re-running the same
capture at 40 m/s shows otherwise:

| Metric | Before | After |
| --- | ---: | ---: |
| Ride-height standard deviation | 6.0 mm | 5.3 mm |
| Road short-wavelength RMS | 44.6 mm | 41.7 mm |
| Ride-height peak-to-peak | 0.0590 m | 0.0711 m |

A 12% reduction in ride-height variation, not the ~55% the source-side numbers
suggested, and peak-to-peak did not improve at all. The reason is that the
in-game road was already smoother than the raw nearest-neighbour samples: the
runtime attenuates the staircase downstream, so most of what bilinear removes had
already been removed. The source-side comparison measured a quantity the driver
never experiences.

The fix is retained because it is correct — the road should interpolate between
cell centres rather than snap to them — but it is a fidelity improvement, not the
answer to the reported symptom.

## What would actually fix it

Grading the road profile: fitting vertical curves through the terrain rather than
following it sample by sample, which is what highway design does. That is a
change to route geometry policy, not a defect fix, and it has consequences this
audit does not decide:

- how much smoothing is authentic before the route stops matching real grades,
  which ADR-0024 and the P0-021 acceptance criteria speak to;
- whether smoothing may alter the authoritative route distance;
- whether a graded profile still satisfies "never infer false precision from
  coarse topology" under ADR-0017.

## Consequence of the retained fix

Elevation values change at every route sample, so every shipping FlatBuffer byte
and content hash changes. The representative-corridor package moved from
`route-v5-2497809086481e15` to `route-v5-c66ac9eeae94346a`. Route packages are
regenerated build outputs rather than committed content, but the merged Q-022
baselines were captured against the previous packages, and a future comparison
against them is no longer like-for-like.
