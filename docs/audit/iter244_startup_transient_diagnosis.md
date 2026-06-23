# iter 244 — half-orange Sara is a startup transient, not per-frame flicker

## Context
iter 241-243 framed the bug as "121 ATTR changes per 540 frames on slot 2"
suggesting per-frame race. iter 244 took a closer look and found a
fundamentally different mechanism.

## Diagnostic: disable hwoam_recolor, observe behavior

Built `tmp/teleport_no_hwoam.gb` with hwoam_recolor's entry byte
replaced by RET (0xC9). Result:
- 0 ATTR changes across all 40 slots over 540 frames
- HW OAM stays at savestate-captured values (pal 4) constantly

This proves hwoam_recolor IS the active stamper. Without it, no stamps,
no alternation, just stuck at savestate-captured palette.

## Per-frame trace exposes the true mechanism

`scripts/diagnostics/probe_slot_attr_trace.lua` samples HW + shadow OAM
plus state context every frame for 60+ frames, then periodically.

On `stage1_entry_pink_renders.ss0`:
| frames | HW slot 0 | HW slot 2 | shadow slot 0 | shadow slot 2 |
|---|---|---|---|---|
| f60-f61 | pal 4 | pal 4 | **pal 2** | **pal 2** |
| f62 | pal 2 (one-frame flick!) | pal 2 (one-frame flick!) | pal 2 | pal 2 |
| f63-f179 | pal 4 | pal 4 | pal 2 | pal 2 |
| f180 | pal 4 | **pal 2 (transitions)** | pal 2 | pal 2 |
| f240 | **pal 2 (transitions)** | pal 2 | pal 2 | pal 2 |
| f300+ | pal 2 (stable) | pal 2 (stable) | pal 2 | pal 2 |

Key insight: **shadow OAM is correctly pal 2 from frame 60 onward**.
HW OAM lags behind by 120-180 frames before "catching up". And each
slot transitions INDEPENDENTLY (slot 2 fixes ~60 frames before slot 0).

## Fresh-boot test confirms it's not savestate-specific

`scripts/diagnostics/probe_fresh_boot_oam.lua` cold-boots, auto-inputs
the title sequence, and samples at f=500/1000/1500/1800/2000:
| frame | D880 | DF1F | HW slot 0 | HW slot 2 |
|---|---|---|---|---|
| 500 | 0x18 (splash) | 0x00 | empty | empty |
| 1000 | 0x02 (stage 1) | 0x00 | **pal 4** | **pal 4** |
| 1500 | 0x02 | 0x00 | pal 2 | pal 2 |
| 1800-2000 | 0x02 | 0x00 | pal 2 | pal 2 |

So even on FRESH BOOT (no savestate), stage 1 entry has the same
transient — HW OAM lags ~500 frames (~8 seconds) before stabilizing
at the correct pal 2.

## Why the iter 241 count of "121 changes" was misleading

The probe counted ATTR transitions including the bulk transitions at
f180 (slot 2) and f240 (slot 0). It also counted the rare single-frame
"flicks" (e.g., f62 where slot 0/2 briefly showed pal 2 then back to
pal 4). Most of the 121 counted events were these transient + the bulk
transition — NOT a sustained per-frame race.

The user's "half orange Sara" complaint is now interpretable as:
**"Sara looks orange (pal 4) for the first ~8 seconds of stage 1
gameplay, then becomes pink (pal 2) and stays pink."**

That's a much more focused bug than "constant flicker".

## Why does HW OAM lag behind shadow OAM?

Three candidate mechanisms (need further probing):

**(a) DMA gated by DF1F** — teleport_routine checks DF1F at the end.
If DF1F > 0, RET (skip JP to COLORIZE). The colorize handler does the
shadow→HW OAM DMA. If skipped, no DMA, HW OAM stays stale.
But probe shows DF1F=0 by f500 on fresh boot, yet HW OAM still pal 4
at f1000. So DF1F isn't the only gate.

**(b) VBlank budget overrun** — total VBlank work (palette loader +
scene_detect + lava override + colorize handler + hwoam_recolor) may
exceed the ~4560T VBlank window. If hwoam_recolor's writes happen
PAST VBlank, OAM is in active-rendering mode and writes silently fail.
This would explain the slot-independent transitions: hwoam_recolor's
loop processes slot 0 first (might write OK while still in VBlank),
slot 2 next (might write OK), but if budget runs out mid-loop, later
slots fail. As budget pressure eases (e.g., DF1D cooldowns expire),
more slots succeed each frame.

**(c) Double-buffer source race** — shadow_main colorizes TWO blocks
at 0xC003 and 0xC103. If DMA copies from a different block than the
one the colorizer just wrote, you'd get stale pal-4 in HW OAM. But
the probe only sampled 0xC003, not 0xC103 — needs verification.

## What this means for the user's bug

The user's "half orange Sara" is the f0-f240 (savestate) or f0-f500
(fresh boot) transient. It's IMMEDIATELY VISIBLE on gameplay start
and lasts 4-8 seconds before normalizing.

This is a much narrower failure window than "constant flicker". Fix
candidates can be evaluated by:
1. How fast does HW OAM converge to pal 2?
2. Does shadow→HW DMA actually fire every frame after stage 1 load?
3. Can we force hwoam_recolor to write earlier in VBlank (more budget)?

## Next iter recommendations

1. Add 0xC103 (second shadow block) to the trace probe — verify both
   shadow blocks have pal 2, OR identify which has pal 4.
2. Time the VBlank handler — instrument with LY-stamps at key points
   to determine if hwoam_recolor exits VBlank window.
3. If VBlank budget is the issue, consider reordering wrapper:
   move hwoam_recolor BEFORE teleport_routine's JP COLORIZE so it
   uses fresh shadow state, OR run hwoam_recolor only every other
   frame to halve T-cost per frame.

NO code change this iter. Pure RE + audit.
