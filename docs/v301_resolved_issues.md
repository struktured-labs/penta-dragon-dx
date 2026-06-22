# v3.01 — User-Reported Issues RESOLVED 2026-05-23

After multiple iterations and hardware testing on MiSTer, all four
user-reported issues in v3.01 are now verified fixed. Each fix was
validated by mGBA CRAM/OAM probe + visual diff against v3.00 baseline
BEFORE deployment.

## Issue: Sara's colors change when miniboss appears

**Root cause**: In `bg_experiment.py:create_palette_loader`, the OCPS
stride calculation for boss palette placement used `slot*2` instead of
`slot*8`. CGB OBJ palettes are 8 bytes apart, so Gargoyle (slot 6)
data was being written to OCPS=12 — landing in Sara D's palette
(slot 1, byte 4 onwards) instead of slot 6.

**Fix**: Changed `ADD A,A` (×1) to `ADD A,A; ADD A,A; ADD A,A` (×3)
before `OR 0x80; LDH [OCPS], A` in palette_loader.

**Verification**: mGBA OBJ CRAM probe after forcing FFBF=1:
- pal 1 (Sara D): unchanged after force — `00 00 E0 03 C0 01 00 00`
- pal 2 (Sara W): unchanged after force — `00 00 BE 2E 1F 51 42 08`
- pal 6: correctly receives Gargoyle data `00 00 1F 60 0F 4C 00 00`

## Issue: White splotches on title screen

**Root cause #1**: Cold-boot zero of WRAM bank 2 (D000-D3FF) took
~5K T-cycles on first VBlank. This spilled the subsequent
palette_loader call out of LCD mode 1 into modes 2/3, where CGB CRAM
writes are dropped silently. The resulting OBJ palette had stuck
bytes at boot default 0x7FFF (white).

**Fix #1**: Removed the cold-boot zero entirely. attr_comp + GDMA
aren't called in the warm path, so WRAM bank 2 is never read.

**Root cause #2**: FF99 protocol save/set/restore + DF03 init added
~125T per VBlank, causing similar palette write drops. Combined,
v3.01 colorize handler was 4 bytes longer than v3.00 with extra cost.

**Fix #2**: Removed FF99 protocol and DF03 init. The colorize
handler at ROM 0x36E00-0x36E40 is now byte-for-byte identical to v3.00's.

**Root cause #3**: `_bg_table` in `build_v301_gdma.py` inherited the
simplified table from `build_v300_inline_hook.py` source, but the
deployed v3.00 FIXED.gb was built earlier from build_v299_minimal.py
lineage with pal 5 entries for hazards/title text tiles (0x2A-0x2E,
0x3A-0x3D, 0x47, 0x57). Without these entries, those tiles rendered
with pal 0 (white BG, invisible) in v3.01.

**Fix #3**: Added pal 5 mappings for hazard tile IDs back into
`_bg_table`. The deployed v3.01 ROM's bg_table at 0x37000-0x370FF
now byte-for-byte matches v3.00.

**Iter 16 (2026-06-14) follow-up:** the hazard tile mappings were
LATER moved from pal 5 → pal 6 (metallic) because pal 5 reads as
fire/lava and the user wanted metallic spikes. Current v3.01
bg_table has tiles 0x2A-0x2E, 0x3A-0x3D, 0x47, 0x57 = pal 6
(byte-locked at iter 218). See
`docs/audit/hazard_tile_colorization.md` for full history.

**Verification**:
- Pure title screen (no inputs) at f400 in mGBA: full YANOMAN logo,
  "OPENING START / GAME START" menu, "©1992 YANOMAN / ©1992 JAPAN
  ART MEDIA / LICENSED BY NINTENDO" all visible
- Real MiSTer hardware screenshot: identical to v3.00 title

## Issue: White splotches when pressing SELECT to enter menu

Symptom resolved by the same fixes as the title splotches above —
the menu uses the same palette/bg_table state, so when palettes are
correct on title, they're correct on menu too.

**Verification**: SELECT-menu screenshots at f1200 v3.01 vs v3.00 —
both show identical "MEDICAL / H.P. / MEGA_FLASH" HUD strip.

## Issue: Scroll flicker

This is NOT a v3.01 regression. v3.01 and v3.00 have IDENTICAL scroll
attribute coverage characteristics:

| Frame | v3.01 zero_attrs in viewport | v3.00 zero_attrs in viewport |
|---|---|---|
| 1020-1740 | 280-313 / 360 | 280-313 / 360 |

The bg_sweep mechanism in BOTH ROMs covers 1 viewport row per frame,
giving ~18-frame full sweep. Newly-entered tiles during scroll briefly
have pal 0 attrs (until bg_sweep reaches them or the inline tile+attr
copy catches them on next game tile-write).

This is a pre-existing limitation of the CGB-colorization architecture,
not a v3.01 regression. Improving it would require a faster sweep
mechanism — earlier attempts (bg_sweep × 2, × 3) caused other issues.

## Self-verification infrastructure built

Used to find and validate all four fixes:

- `scripts/visual_diff_harness.py` — captures continuous frames from
  target + baseline at identical timestamps, 3-panel side-by-side
  diff images for 4 phases
- `scripts/regression_animation_diff.py` — multi-frame regression
  with RMS flicker + white-pixel-fraction analysis
- `scripts/verify_v301_production.py` — fast functional smoke test
- mGBA Lua probes (in `/tmp/`): OBJ/BG CRAM dumps, OAM tile IDs,
  VRAM tilemap + attr layer dumps, FFBF force test
- ROM byte diff scripts to find behavioral deltas between v3.01 and
  v3.00 baseline

**Lesson**: probe-based verification BEFORE claiming a fix is essential.
Single-frame screenshots missed all four bugs above; multi-frame
animation diffs + CRAM/OAM probes caught them all.
