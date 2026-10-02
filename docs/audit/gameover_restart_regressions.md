# Game Over recovery and ceiling regressions

Reported during Rivalmage play, ROM SHA-256
`b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350`:
corrupted Game Over, broken title colours, then missing level on a new run.
Sara W also appeared to penetrate a black ceiling; the exact room is pending.

## Automated recovery gate

`gameover_restart` in the release matrix runs
`scripts/diagnostics/verify_gameover_restart.py ROM --output tmp/FRESH-DIRECTORY`.
It cold-boots and requires two complete death/Game Over/title/new-game cycles.
HP is set to zero once per life; normal game code owns every transition.
There are no scene, VRAM, bank or initialization repairs and no savestate reload.
Timeouts, missing checkpoints, changed room/camera, changed level graphics,
changed packed room data, changed title/level pixels and noncanonical Game Over
screens fail. Raw tile graphics and both bank-zero tilemaps accompany
native screenshots and a per-frame state trace. The receipt identifies ROM,
probe, verifier and captured artifacts. All emulator launches use single-flight.

The full roster now also includes `gameover_spike_restart` and
`gameover_saved_spike_restart`. Each run uses isolated SRAM. The saved-game
fixture sets the native save-present flag before game start, allowing checks
of both the score selector and the plain Stage 01 splash. Blank images fail.
Title pixels are matched across the native animation sequence; gameplay uses
exact saved terrain/color/priority plus rendered pixels outside native sprite
bounds, so Sara's animation phase does not hide terrain corruption.

Candidate `c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d`
passes all three routes and the full 90-gate emulator matrix. Its known-broken
e709 parent fails Game Over capture 1. See
[the investigation](gameover_restart_investigation.md) for exact artifacts and
the current-source publication rerun. Physical replay remains pending; emulator
evidence is not a MiSTer playtest.

## Ceiling case

`check_ceiling` in the new verifier compares a native frame against a reviewed
background frame under an explicit solid-ceiling mask. Its negative controls
reject a sprite pixel inside the ceiling and reject an empty mask. A scene-
specific fixture and input route still need the location from the recording.
Do not use an arbitrary top-screen strip: some rooms allow travel north.
Visual occlusion and collision penetration are separate issues. A collision
case additionally needs the player's world-position trace and the stock ROM's
solid-boundary result under the same inputs. This case is pending, not passed.

Run the visual assertion with `python3 scripts/diagnostics/verify_ceiling_capture.py
--frame tmp/frame.png --background tmp/background.png --mask tmp/ceiling-mask.png`.

## Physical replay checklist

On the same ROM and core, record: cold title, initial room, death art,
Game Over, returned title, newly started room; repeat twice without resetting
the core. Check floor/walls, sprite visibility, colours, sound and controls.
Retain the OBS segment and core version with the ROM hash. Do not replace
this sequence with a fresh core reload, a boss-only death or a Continue test.
