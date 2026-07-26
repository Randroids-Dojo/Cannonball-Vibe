# Controller and keyboard controls

The baseline uses Godot's standard Xbox-style gamepad names so ordinary XInput
controllers and Steam Input's **Gamepad** template share one layout. A Steam
Controller configured to emit WASD is a keyboard-emulation profile: left-stick up
will therefore look like the W key. Select Steam Input's Gamepad template so the
game receives independent trigger and stick axes.

## Driving

| Action | Keyboard | Controller |
| --- | --- | --- |
| Accelerate | W | Right trigger (RT) |
| Service brake | S | Left trigger (LT) while moving forward |
| Steer | A / D | Left stick X axis |
| Reverse | Q | Continue holding LT below 0.35 m/s; B is a secondary binding |
| Handbrake | Space | X |
| Recover at current route point | R | Y |
| Switch chase / cockpit camera | V | Right-stick click (R3) |
| Hold rear view | B | Left bumper (LB) |
| Free look | I / J / K / L | Right stick |
| Trip map | M | View / Back |
| Driver menu / pause | Escape | Menu / Start |
| Cycle assist | Tab | — |
| Suspend save | F5 | — |

RT and LT remain separate unipolar axes with the selected assist profile's
deadzone. LT applies the service brake above 0.35 m/s; while it remains held, it
hands off smoothly to reverse at or below 0.35 m/s. Reverse stays engaged through
near-zero speed noise and returns to braking only if forward speed exceeds
0.75 m/s, preventing chatter or an abrupt direction flip. B remains available as
a secondary direct-reverse binding, but it is not required. Left-stick Y is
intentionally unused while driving, so pushing the stick forward cannot
accelerate. Rear view is a player-controlled hold action; reverse does not force
a camera change. Releasing rear view returns promptly to the prior camera
orientation without changing camera mode or stored free look.

Recover and Restart Run are deliberately different. Recover is immediate and
keeps the current route progress, run clock, and camera mode. Restart Run is in
the driver menu and requires pressing confirm twice; it rebuilds the original
starting world and restores the deterministic seed, starting economy and vehicle
condition, route progress, run clock, motion, assist profile, and chase camera.
It does not delete or rewrite an existing suspend save.

## Menus and trip map

| Action | Keyboard | Controller |
| --- | --- | --- |
| Move focus | Arrow keys | D-pad or left stick |
| Confirm | Enter / Space | A |
| Back / close | Escape | B |
| Pan trip map | Arrow keys | Right stick |
| Zoom trip map | + / − | RT / LT |
| Previous / next map item | Page Up / Page Down | LB / RB |
| Recenter trip map | C | Y |

The gameplay and map meanings may share buttons because the trip map pauses
driving and clears held driving input before returning to the road. The mapping
keeps D-pad/left-stick focus, A confirmation, and B back consistent with standard
controller menus.

## Mapping rationale

- The primary driving contract is conventional and physically separated: RT go,
  LT brake, left stick steer.
- Y is a quick recovery action; the destructive full restart is protected inside
  the paused menu.
- R3 changes camera mode while LB is a temporary rear view, preventing mode and
  glance actions from being confused.
- Automatic reverse-camera behavior is intentionally omitted because it can
  disorient players and overwrite their chosen view at the moment they need
  predictable control.

The cockpit body and interior remain an accepted graybox placeholder for this
bounded controller tranche. The current acceptance covers an unobstructed driver
sightline, correct cockpit-only culling, chase visibility, and rear-look behavior;
it does not claim final cockpit art quality.
