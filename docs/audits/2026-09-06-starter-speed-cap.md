# P1-017: Stock starter speed cap

Date: 2026-09-06. Owner request: implement the capped top speed on the starter
vehicle setup. Dependencies: completed P0-019. Balance follow-up: Q-046.

## Scope and tuning

The initial starter cap is **125 mph (55.88 m/s)**, provisional tuning within
the previously discussed 120–130 mph range. It is vehicle configuration in
engine-independent `VehicleSetup`, separate from the three assist profiles.
Positive engine drive tapers linearly over the last 1 mph. While any tire has
road support, `_IntegrateForces` removes forward velocity above the cap along
the contact plane. This also governs overspeed restored from an older save or
gained downhill. It leaves road-normal suspension/impact motion, lateral slip,
reverse motion and airborne physics separate. This is an arcade governor,
not a gearing/power simulation; [Godot's rigid-body reference](https://docs.godotengine.org/en/stable/classes/class_rigidbody3d.html#class-rigidbody3d-private-method-integrate-forces)
identifies the physics-state callback as the appropriate direct-state seam.

Normal creation, restart and save/world reconstruction use the starter setup.
Explicit existing smoke/scenario profiles select `HighSpeedValidation`, a
250 mph test ceiling above the existing 200 mph corpus. That ceiling is not a
shipping upgrade or a selectable starting configuration. A separate 150 mph
fixture exercises configuration under the same level-road conditions.
There is no new save version: normal play currently has one fixed stock setup.
Persistent upgrades require their own run-state/save contract when implemented.

The owner's pre-existing heat/wear requirements are retained in the GDD.
Their unpublished Q-045 is renumbered Q-046 because the independently merged
atlas design claimed Q-045. Only the stock speed cap is implemented here.
Upgrade prices, heat/wear behavior, winnability, enjoyment and warning/recovery
comprehension remain open. Technical fixture success does not approve them.

## Verification contract

`StarterSpeedProbe` runs the actual vehicle, tire forces and Jolt physics at
120 Hz on an authored plane. Level and 8% downhill full-throttle runs last
30 seconds for each assist profile; the final five seconds must remain within
0.25 m/s below the cap, and measured forward speed may exceed it by no more
than 0.1 m/s (floating-point/contact-step tolerance). At least 99% of samples
must have tire contact and no automatic reset may occur. A 150 mph configuration
uses the same flat fixture. A steeper 20% downhill coasting case exercises the
governor with no throttle. Separate cases check braking, reverse, restored
overspeed, airborne motion, and lateral/vertical impact components.

The first downhill fixture drifted off its 100 m wide plane. Its failed result
is retained under `reports/starter-speed/failures/`. The fixture was widened to
2,000 m and its recovery reference corrected to the actual road plane. No
speed or contact assertion was relaxed. Measurements use signed speed along
the vehicle's forward direction projected onto that plane, matching the cap;
they do not misclassify lateral slip or falling velocity as forward speed.

The probe runs in `scripts/check.sh`, so Linux and Windows M0 exercise it.
The existing rendered controller restart test also checks normal-game setup
selection before and after restart. Unit tests cover taper boundaries, reverse,
configuration isolation and invalid values. Results and exact input/output
hashes are recorded in `evidence/M1/P1-017.json`.
