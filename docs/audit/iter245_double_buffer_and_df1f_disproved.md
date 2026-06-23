# iter 245 — both shadow blocks correct, DF1F drained — narrows to VBlank-budget

## Recap
iter 244 identified three candidate mechanisms for the slot 0/2
startup-transient:
- (a) DF1F gate skipping JP COLORIZE
- (b) VBlank budget overrun — hwoam_recolor writes past VBlank
- (c) Double-buffer source race

iter 245 ran two probes to disprove (a) and (c).

## Probe A: double-buffer source check

`scripts/diagnostics/probe_double_buffer.lua` samples shadow OAM at
0xC003 (block A) AND 0xC103 (block B) PLUS HW OAM at 0xFE03/0xFE0B.

Result (every 10 frames from f60-250 on stage1_entry_pink_renders.ss0):
- shadow block A (0xC003 / 0xC00B): **always pal 2** — correct
- shadow block B (0xC103 / 0xC10B): **always pal 2** — correct
- HW OAM (0xFE03 / 0xFE0B): pal 4 → pal 2 transition at ~f180 (slot 2) / ~f220 (slot 0)

Mechanism (c) DISPROVED. Both shadow blocks are consistently pal 2;
there's no source-race feeding pal 4 into HW OAM.

## Probe B: DF1F + sentinel + debounce state per frame

`scripts/diagnostics/probe_df1f_per_frame.lua` samples:
- DF1F (colorize-skip counter)
- DF1D (re-fire sit-out)
- DF02 (cold-boot sentinel = 0x5A when booted)
- DF0C (combo debounce)
- DF00 (cond_pal cache)

Result from f60 to f240 on the same savestate:
- DF1F: **0x00 throughout** (no skip gate active)
- DF1D: 0x00 throughout
- DF02: 0x5A throughout (boot sentinel intact)
- DF0C: 0x00 throughout
- DF00: 0x05 throughout (cond_pal cache hit)

Mechanism (a) DISPROVED. DF1F is drained from frame 60+; the
colorize-skip gate is not preventing JP COLORIZE.

## What's left

Mechanism (b) — VBlank budget overrun — is the only remaining
candidate from iter 244's list.

Hypothesis: the combined colorize handler at COLORIZE_ADDR (0x6E00)
does:
1. cond_pal (palette loader)
2. shadow_main (set shadow OAM at 0xC003 + 0xC103)
3. **CALL 0xFF80** — OAM DMA (HRAM routine, ~160T)
4. bg_colorizer (BG tile colorization)
5. RET to wrapper

After RET, wrapper CALLs hwoam_recolor. If steps 1-4 take long enough,
the DMA at step 3 may already be past VBlank, but DMA writes to HW
OAM use a special bus mode that should work regardless. More likely
the DMA IS running every frame but the resulting HW OAM is then
OVERWRITTEN by hwoam_recolor's per-slot stamps, which DO run
in late-VBlank or active-display where OAM writes may be blocked.

Wait — that doesn't add up either. If hwoam_recolor's writes are
blocked, they wouldn't overwrite DMA's pal-2 result. They'd leave
HW OAM at the DMA-copied pal 2.

Unless hwoam_recolor's tail-jump to the colorizer's loop_start runs
the SAME logic as colorize handler's shadow pass — but on HW OAM at
0xFE03. The colorizer should set pal 2 for tile 0x24 (Sara). So
hwoam_recolor's stamps should be pal 2, matching DMA's pal 2.

So both DMA (step 3) and hwoam_recolor (after wrapper) should set
HW OAM to pal 2. Yet the probe sees pal 4 for ~180 frames.

## The mystery: what writes pal 4 to HW OAM?

There's an unaccounted-for writer to HW OAM. Candidates:
1. Game's own main-loop OAM updater (outside VBlank)
2. STAT IRQ handler (DOES write slot 1 attr; might write more)
3. Some other VBlank step after our wrapper returns
4. Initial savestate state PLUS DMA not actually running

Wait — if DMA isn't actually running, that would explain it!
The probe of `tmp/teleport_no_hwoam.gb` (hwoam_recolor RET'd out)
showed 0 ATTR changes. The savestate captured HW OAM at pal 4.
WITHOUT hwoam_recolor, no slot transitions = HW OAM stays at pal 4.

So WITHOUT hwoam_recolor: pal 4 constantly. WITH hwoam_recolor:
pal 4 then transitions to pal 2 around f180-240.

This means the DMA isn't fixing HW OAM either! Only hwoam_recolor's
stamps eventually win. The DMA must NOT BE FIRING during the lag window.

The CALL 0xFF80 should fire unconditionally. Unless the colorize
handler RETs before reaching CALL 0xFF80, due to cond_pal or
shadow_main jumping out (not RETurning).

## Next iter recommendation

Add execution-trace probes to verify whether the combined handler
actually reaches `CALL 0xFF80`. Options:
1. Watch the HRAM routine at 0xFF80 — instrument it with a count
   variable in WRAM (`INC [count]`). After 60 frames check WRAM count.
2. Trace LY at entry/exit of the combined handler — confirms whether
   it returns within VBlank or extends into active display.
3. Patch a `RET` instruction over the CALL 0xFF80 site (diagnostic
   inverse). If the bug ALREADY happens without DMA, hwoam_recolor
   alone is the only OAM update mechanism — confirming pure-stamp
   timing is the issue.

Recommend (3) — diagnostic patch like iter 244's hwoam-disable. Quick.
