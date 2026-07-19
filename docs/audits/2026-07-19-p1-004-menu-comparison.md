# P1-004 Representative Menu Comparison

## Outcome

P1-004 is complete and ADR-0008's activation threshold is satisfied. The modern
PlayGodot addon is required for interactive rendered-UI surfaces on official
Godot 4.7.1. It remains debug-only, authenticated, loopback-only, capability
constrained, and absent from release packages.

## Representative surface

The production `PrototypeHud` now contains a driver menu with Resume Drive,
Driving Options, and Trip Overview actions. Escape opens and closes it, opening
places keyboard focus on Resume Drive, and the selected action updates a visible
status. The menu and its controls expose unique stable automation IDs and the
root exports bounded normalized test state. Opening pauses the scene tree and
the always-processing HUD resumes it when the menu closes, matching Q-019's solo
mode working default.

The PlayGodot live test performs the complete interaction through the official
engine: open, signal wait, root description, focus inspection, button selection,
status assertion, scoped screenshot, resume, close signal, and closed-state
assertion. The test does not use raw node paths, display text, coordinates, or
arbitrary property and method access as authority.

## Comparison

| Capability | PlayGodot | Computer Use |
| --- | --- | --- |
| Operate official Godot 4.7.1 window | Yes | Yes |
| Capture visible menu pixels | Yes, viewport or stable-ID crop | Yes, whole window |
| Identify menu and buttons | Stable automation IDs | No in-game accessibility nodes exposed |
| Assert focus | `menu.driver.resume` | Not exposed |
| Assert selected status | Normalized text and root state | Pixels only |
| Wait for open/close | Correlated `visibility_changed` signal | Capture after input |
| Select an action without coordinates or text | Stable automation ID | No |

Computer Use returned nine accessibility entries for the open game window, all
belonging to window chrome or the application menu. None contained the rendered
Driver Menu, Resume Drive, Driving Options, Trip Overview, focus, or selected
status. It remains valuable because its screenshot proves what the player sees
and its OS-level key input proves real window focus.

The observed Computer Use open-plus-state operation took 1,859 ms and the
close-plus-state operation took 1,835 ms. PlayGodot's transcript recorded 26 ms
of in-process server work for the complete semantic flow, including a 20 ms
open signal and 6 ms menu crop. These numbers are diagnostic rather than a
synthetic throughput benchmark because the two layers perform different capture
work. The adoption result rests on unique semantic coverage, not timing alone.

## Artifacts

- [PlayGodot node crop](../images/p1-004-playgodot-menu.png), SHA-256
  `159098bdb9899a3445b65b25bbaf6ec0aa137d87058ea62ba8f374552508886e`
- [Computer Use window capture](../images/p1-004-computer-use-menu.jpg), SHA-256
  `165a21185e63aba36256676881b7249cf7a57264cde2392e53b085607079e90f`
- Local transcript `/tmp/cannonball-playgodot-closeout-1784478538/round-trip.jsonl`,
  SHA-256 `5ffdf71a84eb8d96fc59e255bdd8f6250bb87de94fff9b81110bcd1edfbe0706`

## Verification

- `./scripts/verify-playgodot.sh`: passed; 16 tests in 10.55 seconds.
- Official Godot: `4.7.1.stable.mono.official.a13da4feb`.
- P0-007 release closeout already proves Linux and Windows release PCKs contain
  zero PlayGodot resources and expose no listener, rendezvous, or startup path.
- The CI matrix runs the live suite on macOS, Linux, and Windows.
- Replacement CI run
  [29695072840](https://github.com/Randroids-Dojo/Cannonball-Vibe/actions/runs/29695072840)
  passed the semantic suite on all three platforms plus Linux and Windows M0
  and 500-mile jobs. Every companion asset, export, clean-machine, and review
  check also passed.

The first hosted closeout run found that the menu-crop assertion assumed one
fixed logical-to-render scale. Local macOS rendered the 600-pixel logical menu
to 400 pixels, while hosted macOS rendered it to 321 pixels. The assertion now
keeps a meaningful nondegenerate lower bound without prescribing platform
scale; the stable bounds, pixel integrity checks, content assertions, and
cross-platform screenshots remain authoritative.

## Adversarial review

- Pausing cannot deadlock the test client: the HUD and PlayGodot server both use
  always-processing mode, and the live test resumes through the focused button.
- Closing the menu unpauses before hiding it and exports a closed, unpaused
  semantic state, so the label cannot claim Resume while simulation remains
  stopped.
- Menu selection uses unique automation IDs; no display text, child index, raw
  scene path, or coordinate is authoritative.
- Screenshot assertions permit platform render scaling while still requiring a
  substantial crop, valid PNG bytes, stable semantic bounds, and expected menu
  content.
- Normal startup and release boundaries are unchanged: there is no autoload,
  startup requires the explicit debug flag and token, and P0-007 package
  inspection remains the release authority.
- The complete PR has no unresolved review thread, and CodeRabbit's latest check
  completed successfully.

No unresolved actionable finding remains in this comparison. The broader
question of whether an MCP adapter adds independent value remains Q-012 and is
not required for PlayGodot adoption.
