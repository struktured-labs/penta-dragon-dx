# Level-select / high-score screen color bleed — resolved

## Symptom
The "STAGE 01 / STAGE LOAD / ◆ TOP 3 / 1ST 9999 SEC …" screen shown when you pick
**GAME START with a save present** has orange/red color bleed on the big "STAGE
NN" letters (same tile shows palette 0 AND palette 1 on different cells).

## Root cause (verified)
- This screen is the **level-select** routine `bank1:0x7393` (reached via
  `JP NZ 0x7393` at `0x3B47` when `DCFD != 0`). Its scene byte is **D880=0x00**
  (same as the title menu / boot / ending graphic) and **FFC1=0**.
- It draws the letters with the **direct tilemap writer (tile IDs only, no CGB
  attribute)** and runs its **own input loop (`0x73C3`) with interrupts disabled**
  for the STAT-wait draws — so the **DX VBlank colorizer never runs while it is
  on screen** (probe: cleaner sentinel `DF08` stays `0x00` for 50+ frames; only
  re-arms at ~f270 when the screen is leaving).
- Therefore the letter cells keep whatever BG attributes were last written there
  (by the title banner / prior gameplay via the inline hook) → same tile, mixed
  p0/p1 → bleed.
- **Confirmed**: manually clearing the attr plane (VBK=1, 0x9800-0x9FFF=0) on this
  screen makes the letters uniform p0. So the fix is "clear attrs here".

## Implemented fix

The release builder copies a 36-byte routine from bank 13:`0x53C2` to
WRAM `0xCFAA` during cold boot and redirects the original conditional jump at
bank 0:`0x3B47` to it. The routine:

1. preserves the registers consumed by the original menu path;
2. briefly disables the LCD during the existing screen transition;
3. clears `0x9800–0x9FFF` in VRAM bank 1;
4. restores VRAM bank 0 and LCDC; and
5. publishes the out-of-range palette phase `$A0`, then jumps to the untouched
   level-select routine at bank 1:`0x7393`.

This reaches the screen before its interrupt-disabled loop, where a VBlank
cleaner cannot. The title palette helper recognizes `$A0` and yields instead
of repeatedly writing CRAM over the selector. Natural Stage 1 entry replaces
the marker with the normal palette phase `$11`, so it cannot leak into
gameplay or a later returned title. The marker uses no stock state and does
not touch the title/reel timing counters.

## Verification

`scripts/diagnostics/verify_levelselect_screen.py` boots in mGBA, forces a
save (`DCFD=1`), presses DOWN to move from the default OPENING START to
GAME START, and waits for the score rows. At frame 283:

- the original colorizer-dark state is active (`D880=0`, `FFC1=0`);
- 55 score-screen cells are populated;
- all 360 visible attribute cells are palette 0; and
- the WRAM-copy sentinel is present (`DF0E=0x5A`).

## Note
OPENING START (DCFD==0) bypasses the level-select and is clean. The bleed is
only on the GAME-START/continue path.

Historical probes: `probe_scorescreen.lua`, `probe_levelselect2.lua`, and
`probe_scorefix_diag.lua`.
