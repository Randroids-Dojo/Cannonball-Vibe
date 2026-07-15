# M0 handling and continuity target sheet

M0 retires two risks: whether 200 mph control can remain readable, and whether
route position can remain independent from local physics coordinates.

## Human handling session

Run each assist profile for at least 30 minutes with keyboard and controller.
Record:

- time spent above 160 mph and peak stable speed;
- uncommanded spins, resets, and road departures;
- steering reversals per minute and time spent at full steering lock;
- whether loss of control had a visible cause;
- voluntary continuation after 30 minutes.

Initial pass criteria:

- 200 mph is reachable on a straight;
- the player can make small lane corrections without oscillation;
- every loss has a recognizable warning or input cause;
- no collision tunnels through the road;
- frame rate remains at least 60 fps on the M4 development machine.

`Accessible`, `Balanced`, and `Raw` are live vehicle tunings and can be
cycled with Tab. Balanced is the default.

## Automated continuity session

Run:

```
GODOT_BIN=/path/to/Godot ./scripts/check.sh
```

The smoke driver must print `CANNONBALL_READY`, write a valid suspend save, and
finish with `CANNONBALL_SMOKE_OK`. M1 expands this to a 500-mile traversal and
records frame-time percentiles, chunk-build latency, memory high-water mark,
origin-rebase count, road-gap checks, and save/resume comparisons.
