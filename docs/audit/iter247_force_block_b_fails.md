# iter 247 — force-block-B-only DMA fails to fix the lag

## Context
iter 246 found that the HRAM DMA routine alternates source between
0xC0 (block A) and 0xC1 (block B) via FFCB. Per-frame probe showed
HW OAM = pal 2 ONLY on frames where FFCB=01 (block B). Hypothesis:
block A is being written pal 4 between shadow_main and DMA.

iter 247 tested this hypothesis by patching HRAM 0xFF87-88 from
`C6 C0` (ADD A, 0xC0) to `3E C1` (LD A, 0xC1), forcing DMA to ALWAYS
read from block B.

## Implementation

`scripts/diagnostics/probe_force_block_b.lua` writes 0x3E to 0xFF87
and 0xC1 to 0xFF88 at frame 1 (after savestate load), then samples
HW OAM per frame.

The HRAM bytes after patch:
```
F0 CB        LDH A, [FFCB]    ; still toggles (harmless)
3C           INC A
E6 01        AND 0x01
E0 CB        LDH [FFCB], A
3E C1        LD A, 0xC1       ; PATCH: was C6 C0 (ADD)
E0 46        LDH [FF46], A    ; always DMA from 0xC1 (block B)
```

(First attempt used `C6 C1` = ADD A, 0xC1, which made A alternate
between 0xC1 and 0xC2 — destination 0xC2 is uninitialized WRAM,
visible as garbage tiles e.g. HW0=0x27. Corrected to `3E C1` /
LD A, 0xC1 for constant source.)

## Result

| frame | FFCB | HW0 | HW2 |
|---|---|---|---|
| f1 | 01 | 04 | 00 |
| f6 | 00 | 04 | 24 |
| f11 | 01 | **02** | **22** |
| f13 | 01 | **02** | **22** |
| f15-160 | 00/01 | 04 | 24 (until f160) |
| f160 | 00 | 04 | 22 |
| f180-280 | 00 | **04** | 22 |

Pattern: **HW0 stays at pal 4 for the entire 300-frame test**, with
brief pal-2 windows only at f11/f13. HW2 transitions to pal 2 at
f160 — but slot 0 NEVER transitions in 300 frames with this patch.

## Conclusion

Forcing block-B-only DMA does NOT fix the lag. The race is deeper
than block-A-vs-block-B alternation.

The data suggests block B's slot 0 attr is ALSO pal 4 most of the
time at DMA-execution time, despite iter 245's frame-callback sample
showing block B's slot 0 = pal 2.

**This implies the shadow OAM is BEING UPDATED between mGBA's frame
callback (at LY=144 / VBlank start) and the DMA execution (which
happens later within the same VBlank handler).**

Specifically:
- frame N: VBlank IRQ fires at LY=144
- mGBA frame-callback samples HW OAM + shadow OAM → sees shadow=pal 2
- VBlank handler runs combined handler:
  - bg_colorizer
  - shadow_main: writes pal 2 to block A and B
  - **WHATEVER WRITES PAL 4 to shadow happens here** (unknown)
  - DMA copies (raced) shadow → HW OAM = pal 4
- VBlank handler RETs

The unknown writer must run between shadow_main's RET and the DMA's
CALL 0xFF80 within the combined handler. The bytes between those two
calls are just `CD 80 FF` — no other writes.

Wait — between shadow_main and DMA there's literally nothing. So
shadow_main must itself be writing pal 4 sometimes (not always pal 2).

That requires re-examining shadow_main's colorizer logic. The
colorizer uses tile-to-palette mapping. For tile 0x24 (Sara head),
the mapping is sara_palette = D (Sara form palette = 2). UNLESS D
isn't 2.

D is set at shadow_main's entry:
```
F0 BE          LDH A, [FFBE]
B7             OR A
20 04          JR NZ, +4
16 02          LD D, 2          ; Sara W
18 02          JR +2
16 01          LD D, 1          ; Sara D
```

FFBE = 0 in stage 1 → D = 2 (Sara W). Confirmed via probe.

So D = 2 in shadow_main. sara_palette path writes pal 2. Should be
deterministic.

## What else could write block B's slot 0 attr to pal 4?

The bg_colorizer runs BEFORE shadow_main in the combined handler.
If bg_colorizer writes pal 4 to block B's slot 0, shadow_main
overwrites it with pal 2. So bg_colorizer ordering wouldn't matter.

UNLESS bg_colorizer doesn't run, OR shadow_main is preempted, OR...

Actually — what if shadow_main's colorizer at 0x6A10 EARLY-RETs?
Let me check: colorizer terminates loop on B=0. If B somehow doesn't
reach 0 (e.g., gets corrupted), it could loop forever. Or RET early.

The colorizer's RET path: after the loop completes (B=0), it does
RET (per bg_experiment.py line 164: `emit([0xC9])`).

But within the loop, the only RET is none — it loops until B=0.

OK so shadow_main writes pal 2 to ALL 40 slots in both blocks if it
completes. If it's not completing, it'd hang (no infinite loop guard).

## Next steps

We've ruled out:
- DF1F gate (drained)
- FFC1 gate (always 1)
- Double-buffer source race (both blocks, both shadow blocks pal 2 at sample)
- Block A overwriting (force-B doesn't fix)

The race is somewhere else. Candidates:
- mGBA frame callback isn't at LY=144 as expected — maybe BEFORE VBlank handler
- DMA HW interactions with mid-execution writes
- A WRITE I haven't found yet

For now, abandon the HRAM patch route and look at where the GAME's
OAM update code lives. Maybe the GAME itself writes pal 4 to shadow
OAM in its main loop, BEFORE our shadow_main runs. The colorize chain
fires AT VBlank start, but the GAME might write OAM in its main loop
which is RUNNING when VBlank fires.

If game's main loop writes pal 4 to shadow OAM block A (or B) FIRST,
then our shadow_main runs and overwrites with pal 2. Then DMA reads
pal 2. HW OAM = pal 2.

But probe shows HW OAM = pal 4 after VBlank. So shadow_main's pal 2
write isn't winning.

I'm stuck. The bug requires deeper instrumentation (e.g., breakpoints
on memory writes to 0xC003 to see who writes what when).

NO ROM change committed this iter — patch was diagnostic only.
