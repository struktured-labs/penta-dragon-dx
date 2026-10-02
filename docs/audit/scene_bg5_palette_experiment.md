# Scene-local Stage 1 BG5 — opt-in prototype

`stage1_hazard_palettes.RotatingSpikeBody` in the palette YAML defines the
independent Stage 1 body/power-pickup row. `enabled: false` preserves the
existing builder behavior. Enable only in an isolated experimental build.
The initial colors equal the existing BG5 palette.

The selector uses the same scene classification as the existing tooth row:
`D880 & F7 == 02` (Stage 1 and its Gargoyle overlay). It changes only BG5's
source pointer; later scenes continue reading the primary BG5 row. It does
not separate power pickups from the spike body within Stage 1.

The 96-byte loader extension remains the same size. A helper plus eight-byte
row fits the spare main-loader allocation. No new idle polling, CRAM writes,
WRAM allocation, or emulator/game hooks are introduced. This is nevertheless
a ROM code change, not compatible with the current browser's data-only pin.

## Timing boundary

The previous non-BG7 source padding took 28 CPU T-cycles. The experimental
replacement takes 56 for non-BG5, 96 for non-Stage-1 BG5, and 104 for Stage-1
BG5. These are selector-only counts excluding the unchanged common copy
path. That is +28/+68/+76 T-cycles during pending uploads. The idle scheduler
is unchanged. HBlank waits can amplify an arrival-time difference, so these
counts do **not** prove no transition slowdown or flicker.

Four unit tests check allocation bounds, unchanged default behavior, invalid
row length, and actual selector bytecode over all 256 scene IDs and BG0–BG6.
They do not replace emulator/hardware verification.

Before enabling: isolated ROM build; visibly divergent Stage 1/later BG5
colors; both transition directions including Gargoyle; palette publication
timing; menu, death/Game Over/title/new-game recovery; and savestate restore.
Update the MiSTer browser's verified ROM profile and palette-source map only
after those checks. Nothing has been deployed to Rivalmage for this change.
