# Performance / Slowdown Audit — TELEPORT build colorize chain

Static analysis (no emulator). ROM analyzed: `rom/working/penta_dragon_dx_teleport.gb`
(rebuilt from `scripts/build_v301_teleport.py`). Base compared: `rom/working/penta_dragon_dx_v301.gb`.
Cycle counts are single-speed CGB T-cycles (frame = 70,224T; VBlank window ≈ 4,560T = 10 lines × 456T).

## TL;DR

- **The dead position-sweep at bank13:0x7100 is NEVER CALLed.** Whole-ROM scan finds
  ZERO callers/jumpers to 0x7100. The live colorize handler at 0x6E00 calls the
  tile-ID `bg_sweep` at **0x6CD0**, not the position sweep. The RLE expander (0x6D80)
  is only reachable from inside the dead 0x7100 routine, so it is dead too. Good —
  no unnecessary per-frame cost from that path.
- **scene-detect fast-paths correctly now.** Its cache byte is at **0xDF0D** (verified
  in ROM: `LD HL,0xDF0D; CP [HL]; RET Z`), which is BELOW bg_sweep's `0xDF10–0xDF2F`
  scratch buffer, so it is no longer clobbered every frame. The 256-byte table copy
  (~10,400T) only runs on an actual D880 scene change, not per frame. The dungeon-
  flicker class of bug (colorize attr-write pushed to LY 24–35) is fixed.
- **The teleport build adds only ~330T/VBlank over base v301.** Of that, ~72T is the
  wrapper's extra button-half joypad reads (8 instead of 2), and the rest is the
  teleport routine body + scene-detect fast path (~256T).
- **The dominant per-frame cost is the same in base and teleport: `bg_sweep` (~5,500T,
  3 full 32-byte passes) inside the FFC1 gate.** This is the real lever, not anything
  teleport-specific.
- **No teleport-specific code pushes the colorize attr-write out of VBlank** (after the
  DF0D fix). The colorize chain already runs longer than the 4,560T VBlank window in
  BOTH base v301 and teleport — that is the documented pre-existing scroll-flicker
  characteristic (`docs/scroll_flicker_analysis.md`), not a teleport regression.

## Live call graph (verified by ROM byte scan)

VBlank IRQ at 0x06D1 → hook at bank0:0x0824:
```
0x0824 hook  : LDH A,[FF99]; PUSH AF; LD A,13; LDH[FF99]; LD[2100],A
               CALL 0x6F10 (wrapper)        ; file-off 0x0082E
               POP AF; LDH[FF99]; LD[2100]; RET
0x6F10 wrapper: PUSH BC/DE/HL; 8-read joypad debounce; CALL 0x6E80 (teleport); POP; RET
0x6E80 teleport: CALL 0x6FB0 (scene_detect) ; ... combo/debounce ... ; JP 0x6E00 (colorize)
0x6FB0 scene_detect: LD A,[D880]; LD HL,0xDF0D; CP[HL]; RET Z (fast) | else copy 256B→0xDA00
0x6E00 colorize : POP/VBK save; cold-boot init; CALL 0x6C90 (cond_pal);
                  attr-cleaner (first 32 frames only);
                  FFC1 gate { CALL 0x6CD0 bg_sweep; CALL 0x69D0 shadow_main; CALL 0xFF80 OAM-DMA }
                  VBK restore; RET
```

Whole-ROM CALL/JP scan results (file offsets):
| target | callers found |
|--------|---------------|
| position_sweep 0x7100 | **NONE (dead code)** |
| rle_expander 0x6D80 | only file-off 0x37138 — *inside* the dead 0x7100 routine → dead |
| bg_sweep 0x6CD0 | CALL @0x36E73 (colorize); two JPs @0x37111/0x37133 are *inside* dead 0x7100 |
| colorize 0x6E00 | JP @0x36F0D (teleport tail) |
| scene_detect 0x6FB0 | CALL @0x36E80 (teleport) |
| teleport 0x6E80 | CALL @0x36F41 (wrapper) |
| wrapper 0x6F10 | CALL @0x0082E (bank0 hook) |
| cond_pal 0x6C90 | CALL @0x36E27 (colorize) |

## Per-VBlank cycle estimate (gameplay, FFC1=1, no scene change — steady state)

| Component | T-cycles | Notes |
|-----------|----------|-------|
| hook FF99/bank save+restore (0x0824) | ~128 | entry+exit overhead |
| wrapper joypad (8-read) + CALL teleport | ~364 | **8 button reads** vs base's 2 |
| teleport body (incl scene_detect fast 80T) | ~256 | combo not pressed branch |
| cond_pal (cached) | ~200 | hash-cached palette load |
| attr-cleaner | ~12 | no-op after first 32 frames |
| **bg_sweep (1 row, 3× 32-byte passes)** | **~5,488** | **DOMINANT cost** |
| shadow_main (OBJ colorizer) | ~300 | |
| OAM DMA (0xFF80) | ~700 | DMA wait loop |
| colorize tail | ~40 | |
| **TOTAL / VBlank (steady state)** | **~7,500** | ≈ 164% of the 4,560T VBlank window |

Base v301 (no teleport, 2-read joypad): **~7,160T**. Teleport adds **~330T/VBlank**.

Vanilla DMG VBlank handler (incl. game's own VBlank work): ~3,000T (per `docs/v301_performance.md`).

### scene-detect cost split
- Fast path (scene unchanged, 99.9% of frames): **56T** (`LD A,[D880]; LD HL,0xDF0D; CP[HL]; RET Z`).
- Change path (arena entry/exit only): **~10,400T** one-time (256-byte ROM→0xDA00 copy). Spread over a single transition frame; acceptable.

### inline hook at bank1:0x42A7 (runs only during the GAME's tilemap copy, not every VBlank)
- Teleport build uses the FULL tile+attr copy (`create_inline_tile_copy_tileonly(arena_neutralize_d880=None)`).
  Verified in ROM: body starts `2E 00 11 A0 C1 3E 18` (no arena dispatch present).
- Structure: 24 rows × 6 groups; **per group does a TILE-phase STAT-wait AND an ATTR-phase STAT-wait**
  (4 STAT-poll blocks in the body = the v3.00-style **dual STAT-wait**). ROM scan: 2× `F0 41 E6 03 FE 03` (mode-3 waits) + 2× `F0 41 E6 03` (mode-0 waits) per group.
- Non-wait body ≈ 496T/group × 144 groups ≈ **71,000T** of pure work, PLUS **288 STAT-mode waits**
  (2 per group). A single-wait equivalent would be 144 waits — the second (attr-phase) wait is
  the documented main GB-speed-parity lever (`docs/v301_performance.md` correction banner).

## Question-by-question

### (1) Estimate vs base v301 / vanilla
Done above. Teleport ≈ 7,500T/VBlank steady state vs base ≈ 7,160T vs vanilla ≈ 3,000T.
Teleport's marginal cost over base is small (~330T); the whole-program cost is dominated by
`bg_sweep` (~5,500T) which is identical in base and teleport. The inline hook's dual STAT-wait
(during the game's own tilemap copy) is the largest cost-over-vanilla, also identical to base/v3.00.

### (2) Unnecessary per-frame cost
- **Dead position-sweep 0x7100: NOT CALLed.** Confirmed by whole-ROM scan (zero callers).
  No per-frame waste. The repoint of colorize's `CALL bg_sweep` to the position sweep is
  explicitly disabled in `scripts/build_v301_teleport.py:540` (`# [DISABLED: ...]`). The dead
  0x7100/0x6D80/posmap-table bytes are harmless ROM occupancy only.
- **scene-detect copy frequency: FIXED.** Fast-path `RET Z` works because the cache byte is at
  0xDF0D (outside bg_sweep's buffer). Per-frame 256B copies = 0 in steady state; copy runs only
  on D880 change.
- **Wrapper 8× FF00 read loop: PARTIALLY UNNECESSARY.** The button half reads FF00 eight times;
  the direction half reads it twice. Real hardware needs only a few NOPs/reads to debounce the
  matrix after switching the FF00 select line (vanilla DX reads twice — see base wrapper). 8 reads
  on the button half costs **96T**; 2 reads would cost 24T. **Trimming to ~3 reads saves ~60–72T/VBlank**
  with negligible debounce risk (the game's own joypad read at 0x0824→FF93 already works with 2).
- **bg_sweep per-frame cost: ~5,500T, the dominant lever.** It does THREE full 32-byte passes over
  one row every frame (Phase1 read tile IDs → DF10 buffer, Phase2 table lookup → DF10, Phase3 write
  attrs → VRAM). Phases 1+2 stage through the WRAM scratch buffer; they could be fused into a single
  read→lookup→write pass (save one 32-iter loop ≈ 1,300–2,000T) — see trims below. Not teleport-specific.

### (3) Anything pushing the colorize attr-write OUT of VBlank?
- **No teleport-specific spill after the DF0D fix.** scene-detect fast-paths, so no per-frame 256B copy.
- The colorize chain (~7,500T) legitimately exceeds the 4,560T VBlank window in BOTH base and teleport.
  bg_sweep Phase 3 attr-writes therefore land at ~LY 0–4 (very top of active display) and target the
  ONE swept row that is ahead of the raster, so it is not the flicker class. This is the pre-existing
  double-buffer scroll-flicker characteristic, documented and accepted in
  `docs/scroll_flicker_analysis.md` — present in v3.00/v3.01 alike, not introduced by teleport.
- The one teleport-introduced spill risk (scene-detect 256B copy at LY 24–35) is already eliminated
  by the DF0D move. Verified statically: only scene_detect touches DF0D, and DF0D < DF10.

### (4) Concrete safe trims (cycle estimates)
1. **Wrapper button-half reads 8 → 3.** Remove 5 of the 9 `F0 00` (LDH A,[FF00]) in the button half
   at bank13:0x6F23+. Saves **~60T/VBlank**. Lowest risk; keep ≥2–3 reads for matrix settle.
   (`scripts/build_v301_teleport.py` wrapper block, lines ~585–593.)
2. **Fuse bg_sweep Phase 1+2 into one pass.** Currently: read 32 tile IDs to DF10 (Phase1), then
   re-read DF10 and table-lookup back into DF10 (Phase2), then read DF10 and write attrs (Phase3).
   The inline hook already does the fused `[BC]` lookup in one pass; bg_sweep can do
   `read tile → table lookup → store palette` in a single 32-iter loop, eliminating one full
   32-iteration loop. Saves **~1,300–2,000T/VBlank**. Medium risk (touches the live sweep; verify
   attr correctness in mgba/MiSTer). Applies to BOTH base and teleport.
3. **(Optional) Gate scene-detect to gameplay only.** scene-detect runs unconditionally in the
   teleport routine even on title/menu (FFC1=0). It is only 56T fast-path, but moving its CALL
   inside an FFC1 check would shave it on non-gameplay frames. Saves ~80T on title/menu frames.
   Low value; low risk.
4. **Reclaim dead ROM (cleanliness, not cycles).** 0x7100 (position sweep, 159B), 0x6D80 (expander,
   30B), 0x7B00–0x7DF2 (754B posmaps), 0x7FE0 ptr table — all dead. No runtime cost; remove only if
   the bank-13 space is needed. Document as dead so it is not mistaken for live.

## Files cited
- `scripts/build_v301_teleport.py` — wrapper (lines 569–612), teleport routine (263–425),
  scene_detect (165–227), DF0D fix (106), position-sweep repoint DISABLED (540).
- `scripts/build_v301_gdma.py` — colorize handler (502–653), inline hook (84–268), bg_sweep call.
- `scripts/build_v296_phantomsafe.py` — `create_bg_sweep_viewport_gated` (63–153, the 3-pass sweep).
- `scripts/arena_position.py` — dead position sweep (153–264) and RLE expander (127–150).
- ROM addresses (bank 13 unless noted): hook bank0:0x0824; wrapper 0x6F10; teleport 0x6E80;
  scene_detect 0x6FB0; colorize 0x6E00; cond_pal 0x6C90; bg_sweep 0x6CD0; shadow_main 0x69D0;
  OAM-DMA 0xFF80; dead position-sweep 0x7100; dead expander 0x6D80; inline hook bank1:0x42A7.
