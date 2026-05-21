# v3.01 Regression — Stuck on STAGE 01 Splash

**Status: OPEN. v3.01 cannot enter gameplay; v3.00 is still the working production.**

## Symptoms

Side-by-side stress test (4000 frames, with autoplay input pattern):

| ROM | FFC1 first | D880 distribution | FFBD distribution | Visual at f=3000 |
|---|---|---|---|---|
| vanilla A-fix | 510 | `0x02 × 350` (dungeon) | rooms 1/3/5/7 cycled | Sara walking in dungeon |
| v3.00 FIXED.gb | 510 | `0x02 × 318, 0x18 × 32` | rooms 1/3/5/7 cycled | Sara walking in dungeon |
| **v3.01 production** | **510** | **`0x00 × 350`** | **`5 × 350` (stuck)** | **STAGE 01 high-score splash** |

v3.01 reaches FFC1=1 at the same frame as vanilla (510), so the START press is processed.
But it never advances past the STAGE 01 splash → dungeon transition. FFBD=5 corresponds
to the splash screen state; D880=0x00 means no scene-context byte ever got published
(so the sound engine doesn't update either).

## Why the earlier probes missed this

`verify_gameplay_palette.py` checks only that:
- FFC1 reaches 1
- BG palette has ≥3 distinct words
- BG attr histogram uses ≥2 palette indices

All three are satisfied on the STAGE LOAD splash screen. The probe doesn't check that
the game progresses *past* the splash into dungeon play.

The visually-confirmed colorization screenshots in earlier iterations also captured
the STAGE LOAD screen with correct colors — but those WERE the splash, not gameplay.

## Suspect changes between v3.00 (works) and v3.01 (broken)

Per `build_v301_gdma.py` vs `build_v300_inline_hook.py`:

1. **Inline tile copy**: v3.00 does tile+attr inline (117 bytes at 0x42A7); v3.01 does
   tile-only inline (56 bytes) — attr work moved to VBlank attr_computation.
2. **Colorize handler timing**: v3.01 spends ~53K T per VBlank vs v3.00's ~40K T.
3. **bg_table**: v3.01 uses multi-room context-analyzed wall mapping; v3.00 uses older
   simpler mapping.
4. **FF99 fix**: v3.01 saves/sets/restores FF99 in colorize_handler; v3.00 does not.
   But this was added LATER — the regression is present BEFORE the FF99 fix too
   (per earlier per-row probe output).
5. **GDMA call**: v3.01 calls 0x6D80 (GDMA transfer) conditionally each frame.

Most likely root cause: **GDMA transfer is corrupting state** during the STAGE LOAD →
dungeon transition. The GDMA copies bank-2 buffer (initially garbage) into the
tilemap, which may overwrite something the game's transition code reads.

The STAGE LOAD screen uses the alternate tilemap region (0x9C00). The game's
transition routine likely sets LCDC bit 3 to switch tilemap region. If our GDMA
runs during that transition and writes to the wrong tilemap, the new dungeon
tilemap is overwritten by stale bank-2 data.

## Cliff is between 22 and 23 rows of attr_comp per frame

Further binary search by row count (each test: 4000-frame stress with autoplay):

| Rows per frame | FFBD distribution | Verdict |
|---|---|---|
| 1   | full cycle 1/3/5/7 | OK |
| 2   | full cycle 1/3/5/7 (earlier "broken" was autoplay-timing noise) | OK |
| 4   | mostly stuck at 5, some 1/3/7 visible | partial / unreliable |
| 8   | full cycle | OK |
| 12  | full cycle | OK |
| 16  | full cycle + mini-boss spawning | OK |
| 20  | full cycle + boss splash | OK |
| 21  | mostly cycle, ~57% FFBD=0 (game intermittently glitching) | partial |
| 22  | similar to 21, ~62% FFBD=0 | partial |
| 23  | stuck at 5 (350/350) | **BROKEN** |
| 24 (production) | FFBD=0 (348/350), D880=0x00 | **BROKEN** |

**The cliff is between 22 and 23 rows.** Each row adds ~2050T (DI window
+ EI gap). At 22 rows the handler uses ~45K T of the 70K T frame budget,
leaving ~25K T for the game's main loop — barely enough. At 23+ rows,
main loop is too starved to progress past the STAGE LOAD splash.

This explains the dependency on row count: the game's STAGE LOAD →
dungeon transition routine requires a minimum amount of main-loop CPU
per frame. Below ~25K T it can't make progress within a reasonable
number of frames.

## Fix candidates (in order of preference)

1. **Reduce to 18 rows** (matches visible viewport height; 6 rows
   off-screen never visible) — saves ~12K T/frame; well within safe
   budget; full visible colorization.
2. **Stagger: 12 rows per frame, alternating odd/even rows** —
   full 24-row coverage in 2 frames; 24K T/frame budget; smooth.
3. **Dirty-rect**: only write attrs for tiles that CHANGED since last
   frame — typically ~0-10 rows in steady state.

Going with #1 as the simplest fix.

| Variant | attr_comp call | attr_comp body | GDMA | Gameplay (FFBD cycle) | Result |
|---|---|---|---|---|---|
| production v3.01 | yes | full | yes | FFBD stuck at 5 | **BROKEN** |
| `_no_attr` | NO | n/a | NO | FFBD 1/3/5/7 cycling | OK |
| `_attr_no_gdma` | yes | full | NO | FFBD=0 for 348/350 | **BROKEN** (worse!) |
| `_call_only` | yes | bare `RET` | NO | FFBD 1/3/5/7 cycling | OK |

**Conclusion: the BODY of attr_computation is the culprit, not the GDMA copy.**
Just CALLing attr_comp with an empty body is fine.

The attr_computation body does:
1. Reads tile buffer at 0xC1A0-0xC3DF (576 reads)
2. Reads bg_table at bank13 ROM 0x70XX (lookups)
3. Writes to WRAM bank 2 0xD000-0xD2FF (576 writes after FF70=2)
4. Uses FFE0 as HRAM scratch (loop counter)
5. 24 DI windows × ~2000T each

One of these has a side effect on game state. Next binary search:
- Test #1: attr_comp with FFE0 scratch replaced by a register (no HRAM scratch)
- Test #2: attr_comp body but NO writes to bank 2 (just reads + FF70 toggles)
- Test #3: attr_comp body with only 1 row of work (vs 24)
- Test #4: attr_comp body with FF70 toggle removed (writes go to bank 1 by accident — would corrupt game state — should clearly distinguish bank 1/2 effects)

## Why production hasn't shown this

The MiSTer-deployed production ROM is `penta_dragon_dx_FIXED.gb` = v3.00, NOT v3.01.
v3.01 has never been deployed because of the earlier freeze (now fixed by FF99) and
because it wasn't hardware-verified. So no end-user has hit this regression.

But the v3.01 ROM in `rom/working/penta_dragon_dx_v301.gb` is broken for actual gameplay.
**Until this is resolved, v3.00 stays as production.**

## Honest update to earlier docs

`v301_gdma_freeze_diagnosis.md` declared the freeze RESOLVED. That is still true —
v3.01 doesn't *freeze* anymore. But it has a NEW regression (stuck on STAGE LOAD)
that the probes I built didn't detect.

The "BG tiling solved efficiently" claim in earlier iteration summaries was
overconfident. The freeze IS solved; full gameplay is NOT.
