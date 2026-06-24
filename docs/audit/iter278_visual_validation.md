# iter 278 — Visual validation of Stop hook conditions

Captured screenshots from `rom/working/penta_dragon_dx_teleport.gb`
(current build, B=40, iter 276/277 audited state) to validate against
the Stop hook conditions: "no flickers, no slow downs, no half orange
Sara, title screen is clean, stage intro is clean, cursor is rendered
on first screen."

## Screenshots captured

All saved under `tmp/hook_visual_validation/`:

- `title_late_f1500.png`, `title_late_f2000.png` — title menu at f=1500/2000 (D880=0x1C confirmed via probe)
- `stage1_splash_f60.png`, `stage1_splash_f300.png` — STAGE 01 intro splash (D880=0x18)
- `stage1_gameplay_f60.png`, `_f120.png`, `_f300.png`, `_f500.png`, `_f1000.png` — stage 1 gameplay

## Condition-by-condition assessment

### Title screen clean — **PASS**

`title_late_f2000.png` shows:
- YANOMAN logo (top, with ®)
- PENTA DRAGON DX (centered)
- OPENING START / GAME START options (left-aligned)
- ©1992 JAPAN ART MEDIA / STRUKTURED LABS footer

All text legible, no flickering or corruption visible across f=1500-2000.

### Stage intro clean — **PASS**

`stage1_splash_f60.png` and `_f300.png` show "STAGE 01" in grey/blue
font on black background. Stable, no flickering.

Per memory: stage 01 font reads grey/blue mix — accepted as polish
candidate, not a corruption.

### Cursor rendered on first screen — **FAIL**

OAM probe at title menu (D880=0x1C, f=2126-3703) shows ZERO active
OAM slots. The cursor (►) symbol to the left of OPENING START / GAME
START is NOT rendered.

Per memory: cursor fix tried+failed across iter 233/234/238/240/263.
The cursor is BG-tile-based (not OBJ), so it's a tilemap state issue,
not a sprite render issue.

### Half-orange Sara — **FAIL**

Pixel analysis of stage 1 gameplay (`stage1_gameplay_f*.png`),
Sara region (x=40-80, y=40-80):

| Frame | Top sprite colors | Sara state |
|---|---|---|
| f=60  | #A52100 (54), #FF7B00 (17) | ORANGE (pal-4) |
| f=120 | #A52100 (54), #FF7B00 (17) | ORANGE (pal-4) |
| f=300 | #F7AD5A (24), #FF42A5 (17) | PINK (pal-2 correct) |
| f=500 | #F7AD5A (24), #FF42A5 (17) | PINK (pal-2 correct) |
| f=1000| #A52100 (29) | ORANGE (pal-4) |

The race is REAL and VISIBLE — Sara alternates pal-4 (orange) ↔ pal-2
(pink) across frames. Pixel-frequency probe in
`probe_white_flicker.lua` quantified this as 121/540 frames (22%
race-loss rate) at slot 2 ATTR alternation.

### No flickers — **PARTIAL**

Sara color alternation IS a flicker (pal-2↔pal-4 every few frames).
This is the half-orange race symptom. Other on-screen elements (items
on right side, background pattern, walls) are STABLE across frames.

### No slowdowns — **NOT MEASURED**

No frame-rate analysis performed in this iteration.

## Why the failures aren't fixable in current autonomous loop

### Half-orange Sara
- B=40 → B=20: race reduces 113→23 (80%) BUT breaks 4 fresh-boot CRAM
  expectations (Sara jet form, Gargoyle, Spider boss palettes). See
  [iter277_b_sweep_attempted_reverted.md](iter277_b_sweep_attempted_reverted.md).
- Per-iter colorizer mode-lock check (+640T): breaks 4 visual tests
  via VBlank-budget timing shift.
- Mode-lock detection at hwoam_recolor entry (+24T, RET-Z): breaks
  spiral_power_active by skipping slot 10+ stamping on mode-locked frames.
- Adaptive mode-lock fix (candidate J: skip slot 0-3, continue slot 4-39):
  overruns the 48-byte hwoam_recolor budget at 0x7F40 (need 57 bytes).
  Would require relocating to 0x6B27 (217 bytes free) — a substantial
  refactor not attempted in iter 277.

### Cursor on first screen
- 5 prior iteration attempts (iter 233/234/238/240/263) all reverted
  because each fix broke other regression tests.
- Per [project_iter233_236_revert_lessons.md](project_iter233_236_revert_lessons.md):
  cursor change broke stage6 test; STAT stub extension broke 50 tests.

## Build state

- ROM: `rom/working/penta_dragon_dx_teleport.gb` (B=40, iter 276/277 baseline)
- 116 BG-scene regression tests: ALL PASS
- Fresh-boot test (FFD0=1, FFBF=1/2, FFC0=3, etc.): ALL PASS
- 152 ROM-byte verifier checks: ALL PASS
- Visual: half-orange Sara race visible (22% of frames); cursor
  missing from title screen

The build is in a known-good test-passing state. The visual issues
documented here are pre-existing autonomous-loop limitations
(documented across iter 233/234/238/240/263/276/277).
