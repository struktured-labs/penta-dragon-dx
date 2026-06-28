# iter 278t — STAT IRQ LY-dispatch with mode 1 source (attempted, reverted)

## Summary

After iter 278s2 failed (extending existing STAT IRQ stub broke parallax via
~132T addition exceeding iter 8's 30T threshold), implemented the workflow
synthesis's full recommendation: LY-dispatched STAT IRQ with mode 1 source
enabled at cold boot.

## Implementation

1. **STAT register probe** (key finding): game uses LYC=0 source ONLY
   (FF41=0xC1: bit 6 LYC enabled, bits 5/4/3 mode sources disabled).
   This means adding mode 1 source (bit 4) gives a SECOND STAT IRQ
   fire per frame at LY=144 (VBlank entry) without disturbing existing
   parallax.

2. **WRAM stub at 0xDB50** (~70 bytes): dispatch on `LDH A,[FF44]; CP 144`:
   - LY=144: 4-slot stamp (slot 0/1/2/3 attrs) + RETI
   - LY=0 (else): existing slot 1 stamp + JP 0x0853 (parallax chain)

3. **Cold-boot installer**: 3 lines added to teleport_routine's init
   block (gated by DF0E sentinel): `LDH A,[FF41]; OR 0x10; LDH [FF41],A`
   enables mode 1 source ONCE.

4. **STAT_STUB_MAX bumped** 36→80; STAT_STUB_ROM_ADDR relocated 0x53F2→
   0x6A70 (144-byte free run in bank 13).

## Visual Result

**Sara is PINK at f=60** on stage1_entry_pink_renders.ss0 (vs orange in
iter 278e baseline). LY=144 mode-1 path successfully stamps slots
0/2/3 in safe VBlank window.

## Hook Result

**39 regression tests FAIL** — far more than iter 278s2's 17. Includes:
- All 9 boss arena_content + arena_dispatch tests
- banner_bg_table_palettes (bg_table[0xE0]=p5 vs expected p6)
- cutscene_bg_table_palettes
- dungeon_uses_dungeon_table (bg_table[0xE0]=p5 vs p0)
- dungeon_table_items_and_font
- jet_form_visual_render
- lava_off_at_ffba0
- crow, etc.

## Root cause of regression

The LY-dispatch adds ~28T to the LY=0 (parallax) path:
- PUSH AF (16T) - same
- LDH A,[FF44] (12T) - NEW
- CP 144 (8T) - NEW
- JR Z, .mode_1 (8T not taken) - NEW
- continue to existing parallax stamp...

**+28T is RIGHT AT iter 8's 30T break threshold**. Parallax-scroll
handler's SCY/SCX writes shift by ~28T, breaking scanline timing.
Worse, the shifted timing affects scene_detect's bg_table load,
producing bg_table[0xE0]=p5 (banner_override remnants leaking) instead
of expected pal-0 (dungeon).

## Architectural conclusion

The autonomous-loop ceiling is HARD-BLOCKED at the LY=0 parallax path:
- Adding ANY dispatch logic before parallax adds 8+T → breaks parallax
- Adding the multi-slot stamp INSIDE parallax adds 132T → broke iter 278s2
- Adding work to the wrapper itself adds cycles → breaks CRAM phase
- Adding STAT IRQ at a DIFFERENT vector (mode 1 only) requires LYC=0
  parallax to coexist, which requires dispatch logic, which adds cycles

The visual proof (Sara PINK at f=60 in iter 278s/s2/t) confirms the
fix IS architecturally possible, but the implementation requires
either:

1. **Per-fire dispatch with <8T overhead** — would need raw assembly
   tricks (XOR-skip, conditional moves) below GB CPU instruction
   granularity. Not feasible.

2. **Dual IRQ vectors** — STAT IRQ has only ONE vector at 0x0048. Would
   require ROM-side patch to multiplex.

3. **Test-suite redesign** — relax parallax timing tolerance to accept
   28T shift. Would lose regression sensitivity.

4. **Deep game refactor** — patch parallax handler to be timing-tolerant.
   Beyond autonomous-loop scope.

## Build state after revert

Restored to iter 278p baseline (commit `2d94d67`):
- iter 278p: stage intro letter brightening (component 4 SHIPPED)
- iter 278l: cursor visible as 'A' character (component 3 SHIPPED)
- iter 278e: 75% Sara race reduction (components 1+2 partial)
- 170 byte-verifier locks pass
- All 116 BG regression tests pass

## /goal status — 11 distinct attempts

| Attempt | Approach | Outcome |
|---|---|---|
| iter 277 | B=20 hwoam_recolor | -480T → broke 4 CRAM |
| iter 278d | inline split-stamp +600T | broke many CRAM |
| iter 278g | CALL sara_stamp +24T | broke 22 CRAM |
| iter 278h | CALL sara_stamp + FFA9 invalidate | VBlank overrun |
| iter 278n | inline sara_stamp + NOP padding | 6-8 CRAM fails |
| iter 278o | iter 278n + test-side FFA9 force | 8 CRAM (game overwrite) |
| iter 278q | iter 278n + setBreakpoint protection | partial OBP-2 fix, FFC0 crashed |
| iter 278r | colorizer default → sara_palette | 10 enemy tests broke |
| iter 278s | hoist hwoam_recolor to first | **Sara PINK** + 16 tests broke (stale tiles) |
| iter 278s2 | STAT IRQ 4-slot extension | **Sara PINK** + 17 tests broke (+132T parallax) |
| **iter 278t** | **STAT IRQ LY-dispatch + mode 1** | **Sara PINK** + 39 tests broke (+28T parallax) |

Three of the last four attempts achieved VISUAL fix (Sara PINK) but
all broke parallax/timing tests. The fix IS achievable in theory; the
implementation costs cycles that cascade through tested invariants.
