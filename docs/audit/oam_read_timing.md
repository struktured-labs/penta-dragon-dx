# mGBA Lua OAM read timing — resolved (and the real bug it uncovered)

**Resolution 2026-06-18:** the "per-byte drift in 40-slot loop" theory was
WRONG. Switched dump_oam to `emu:readRange(0xFE00, 0xA0)` (atomic block
read returning a string). That eliminated my probe-vs-runner discrepancy,
which then revealed a **real game-side issue**: Sara's HW OAM slot 1 attr
ALTERNATES between pal 2 (Sara W, correct) and pal 6 (Gargoyle, wrong)
every few frames during the gargoyle_miniboss save.

**Hard evidence:** dump-every-frame trace on
`level1_sara_w_gargoyle_mini_boss.ss0` over 1166 frames showed slot 1 attr
= 0x02 in 490 frames and 0x06 in 676 frames (≈42/58 split). Slot 0/2/3
all stayed at pal 2. Only slot 1 alternates.

This is the same kind of alternation pattern we documented for boss arena
BG attrs (`project_arena_position_sweep.md` — Sara's right-half OBJ slot
gets the boss palette written by ??? mid-frame). The screenshot still
shows Sara as predominantly peach/pink because:
1. LCD renders one specific frame's HW OAM; ~42% chance that snapshot is
   the correct pal2 frame.
2. Persistence-of-vision averages the alternating sprite colours, so the
   user perceives "slightly purple-tinged peach" rather than "flickering
   between peach and blue-gray".

## What's confirmed

1. **Visual = correct.** Screenshot-pixel sampling of `gargoyle_miniboss.png`
   at game coords (72,64)-(88,80) shows (247, 173, 90) peach + (74, 8, 0)
   dark red + (16, 16, 0) near-black. Those match Sara W's OBJ palette
   (`OBP2 = 0000 2EBE 511F 0842`). They do NOT match BGP6/OBP6 (blue-gray
   ~165,165,181).

2. **Single-slot probe = correct.** A focused probe reading ONLY slot 0
   and slot 1 attr at frame 60 (via `-t` state load + same Lua "frame"
   callback timing as the test runner) reports `slot0=0x02 slot1=0x02`
   consistently across f60/62/65 (`/tmp/match_test_runner.log`).

3. **40-slot dump = WRONG.** The test runner reads ALL 40 OAM slots in a
   loop (160 sequential `emu:read8` calls per sample). At frame 60+ in
   gargoyle save, slot 1 attr comes back as `0x06` (boss palette).

## Hypothesis

`emu:read8` is not atomic relative to the emulator core's frame loop —
between iterations of the OAM dump, the core may advance scanlines, and
the game's main-loop OAM rebuild can update HW OAM mid-dump. Slot 0 gets
read at LY=144 (post-recolor), slot 1 gets read at LY=145+ where the game
has had time to overwrite slot 1's attr.

The consensus filter (5 samples in frames 58–68) does NOT fix this because
each sample suffers the same mid-dump drift in the same way — majority
vote across 5 identical-bias samples still loses.

A pre-read busy-loop also doesn't help (the drift is during the dump,
not before it).

## What we ruled out

- Lua `emu:loadStateFile` vs `-t` state-load: both produce the same OAM
  behaviour at frame 60+ in single-byte probes.
- Frame-callback timing relative to VBlank IRQ: LY=144 at callback fire,
  which is post-IRQ — single reads are clean.
- The colorizer logic: trace through `bg_experiment.py.create_tile_based_colorizer`
  for tile 0x25 goes `CP 0x30 carry → low_tiles → CP 0x20 NC → sara_palette`
  → A = D (Sara form palette) = 2 for Sara W. No path produces pal 6 for
  this tile sequence.

## What was fixed (test harness)

- `dump_oam` in `scripts/run_color_regression.py` switched from a 40-slot
  loop of `emu:read8` calls to a single `emu:readRange(0xFE00, 0xA0)`
  block read + Lua string indexing. This is the **atomic block-read
  primitive** mGBA Lua exposes; eliminated the per-byte drift hypothesis
  and made probe results reproducible.

## What's NOT fixed (real game bug — future iteration)

Sara's OAM slot 1 alternation in boss fights. Root cause: somewhere in
the boss-fight path, slot 1's attr gets written to pal 6 (the gargoyle
boss palette E value) when it should stay pal 2 (Sara W form's D value).

## Iteration 3 findings (2026-06-18)

Deep probe at frames 250-400 (when HW slot 1 alternates) reveals the
ACTUAL flow:

- **Shadow A slot 1 attr**: pal 2 ALL frames (colorizer correctly paints
  Sara palette in shadow buffer A at C007).
- **Shadow B slot 1 attr**: pal 2 ALL frames (same for shadow buffer B
  at C107).
- **HW OAM slot 0**: pal 2 ALL frames (consistent with shadow).
- **HW OAM slot 1**: pal 2 OR pal 6, alternating (~42/58 split).

So the colorize handler IS doing its job. The DMA copies clean pal 2 to
HW OAM. **My HW-OAM recolor also writes pal 2.** But BETWEEN my recolor
(end of VBlank IRQ) and the Lua read (start of next frame), SOMETHING
overwrites HW OAM slot 1 attr with 0xFE (= pal 6 + flips + bank + priority
bits set). The "something" is the game's main-loop sprite-rebuild code
running OUTSIDE VBlank — it writes directly to `0xFE07` between IRQs.

The original NOP at `rom[0x06D5]` killed the game's OAM DMA, but there's
STILL a direct-write path somewhere that we missed. ROM-scan for `EA 07
FE` (direct LD [0xFE07], A) returns zero matches, so the write must be
indirect (LD [HL], A with HL set elsewhere — likely a strided OAM-rebuild
loop).

### Fix options

1. **Find and NOP the offending write.** Need mGBA memory watchpoint OR
   instruction-trace at LY != 144 (main loop scanlines). Lua exposure
   limited — may need an emulator-side script.
2. **Add a 2nd recolor pass on every scanline / mode 2 (OAM scan).**
   Triggered by STAT IRQ. Adds complexity + cycles but fixes it
   guaranteed.
3. **Disable the rogue path indirectly.** If the loop is part of
   `gargoyle_logic` (boss-specific), patch the boss-spawn routine to
   skip OAM rebuild.
4. **Live with it.** Persistence-of-vision averages the alternation —
   user perceives "slightly purple-tinged peach" not "flickering between
   peach and blue-gray". Real visual impact is small. Mark known-issue
   and move on.

Option 4 is the lowest-effort, and the user's visual complaint in this
session was about explicit "Sara half-orange" which was a DIFFERENT bug
(the earlier B=40 recolor issue, since fixed). The current alternation
is subtle enough that it may not have been noticed visually.

Recommended next: pursue option 2 (STAT-triggered re-recolor) on a future
iteration when there's a multi-hour window. For now, leave the 9 boss-
save OBJ tests excluded from the hook (they'd be 42/58 flaky against the
real alternation).

Until fixed, the 9 boss-save OBJ tests stay out of the pre-commit hook
because their YAML expectations (Sara=pal2) are objectively correct and
the game IS wrong — but the test would flicker pass/fail with the
alternation. Mark them as `known_flaky_until_alternation_fixed: true`
when widening the hook.

## Iteration 6 finding: same root cause family for non-boss enemies

Probe of `level1_sara_w_orc_healpotion1_poison_cure.ss0` over 491 frames
showed slot 4 (orc body tile 0x05) alternating between pal 0 (362 frames)
and pal 4 (129 frames). The test ACTUALLY fails on slot 12 (orc body tile
0x55 expected pal 5, got pal 0) because the colorizer assigns orc to
slots 10+ where my B=10 recolor doesn't reach — same DMA-race-residue
mechanism as Sara slot 1 in boss fights, just affecting non-Sara
sprites in higher slots.

So the "9 excluded OBJ tests" all share ONE underlying issue:
**sprites past slot 10 don't get re-colored by my HW recolor**, so the
game's main-loop OAM writes (which use default pal 0 or game-chosen pals
that differ from the colorizer's intent) win at LCD draw time.

The cleanest fix is option 2 from above (STAT-IRQ re-recolor — pure
re-stamp during HBlank, no need to expand B which would bring back Sara's
half-orange via slot 10-11 secondary sprites mapping tile 0x10-0x1F to
pal 4). This unifies the fix for ALL 9 excluded tests at once.

## Iteration 7: detailed STAT-IRQ implementation plan

Survey of the existing IRQ vectors (`rom/working/penta_dragon_dx_teleport.gb`):
```
0x0040 (VBlank): C3 D1 06 → JP 0x06D1 (game's existing VBlank handler, our trampoline hooks it)
0x0048 (STAT):   C3 53 08 → JP 0x0853 (ALREADY IN USE — sound/music timing handler)
0x0050 (Timer):  C3 B3 06 → JP 0x06B3 (game's timer / sound engine tick)
0x0058 (Serial): D9       → RETI (unused)
0x0060 (Joypad): D9       → RETI (unused)
```

So STAT can't be hijacked directly — the game has its own handler at 0x0853
(saves all regs, switches to bank 1, does sound work, switches bank back,
RETIs). Our STAT-IRQ re-recolor must CHAIN through it.

### Plan for next iteration(s)

1. **Author `stat_irq_handler` in bank-13 free space** (currently ~33 bytes
   available between 0x7FCD and POSMAP_PTR_TABLE 0x7FE0, plus 14 bytes after
   0x7FF2). Target size: ~30 bytes. Logic:
   ```
   stat_irq_handler:
     PUSH AF
     LDH A, [FFBE]        ; Sara form: 0=W, 1+=D
     OR A
     JR NZ, .dragon
     LD A, 0x02           ; pal 2 = Sara W
     JR .stamp
   .dragon:
     LD A, 0x01           ; pal 1 = Sara D
   .stamp:
     ; Re-stamp slot 1 attr (the dominant alternation slot)
     LD H, A              ; save pal
     LD A, [0xFE07]       ; current slot 1 attr
     AND 0xF8             ; clear pal bits
     OR H                 ; merge new pal
     LD [0xFE07], A       ; write back
     ; Also re-stamp slot 3 (same logic) and slots 10-15 (orc/soldier body)
     ; ... (further stamps via tile-range lookup for non-Sara slots)
     POP AF
     JP 0x0853            ; chain to game's STAT handler
   ```

2. **Patch IRQ vector 0x0048** to JP `stat_irq_handler` instead of 0x0853.
   1-byte change (the low byte of the JP target), but bank-13 is not always
   mapped — the handler must live in a bank that's permanently accessible.
   Bank 0 is always-mapped. Bank 13 is mapped during colorize chain but
   NOT during main loop (which is when STAT fires).
   
   So: install handler in bank 0 free space. Or in WRAM (0xDB00 landing pad
   has space if we move things around). WRAM is bank-agnostic.

3. **Enable STAT mode 0 (HBlank) interrupt**: set bit 3 of STAT register
   (0xFF41). Currently the game might enable STAT only for LYC match or
   mode 1; need to OR in bit 3. One-shot write at boot OR every VBlank.

4. **Performance check**: 144 STAT IRQs per frame × ~30 cycles per handler
   = ~4320 cycles overhead per frame. CGB at single-speed has ~70000 cycles
   per frame, so ~6% overhead. Probably tolerable in mGBA; real-hardware
   measurement needed before claiming OK on MiSTer.

5. **Verification**: rerun gargoyle_miniboss/spider_miniboss_*/moth/mage/
   metal_ball_mage_soldier and all 4 orc/soldier/catfish/orc_with_items
   slot-10+ tests. Expect: all 9 currently-excluded OBJ tests pass.

6. **Hook expansion**: once all 9 pass reliably, add them to
   `scripts/hooks/pre-commit`. Hook goes from 21 → 30 tests, ~70-80s.

Estimated total effort: 2-3 short iterations OR one long focused session.
Risk: the per-scanline overhead could push VBlank+colorize over budget
on real MiSTer hardware (the phantom-sound history shows this is sensitive).
Mitigation: gate the handler on `D880 < 0x16` (only run in dungeon + arena,
not menus/cutscenes) → cuts overhead during attract cycle.

### Bank-0 free space — confirmed location

ROM scan for runs of 0x00 (padding) >= 20 bytes in bank 0 (0x0000-0x3FFF)
found exactly ONE candidate: **0x0838 - 0x0852 = 27 bytes of 0x00**, sitting
IMMEDIATELY before the existing STAT handler at 0x0853. Perfect for a
fall-through prelude: install code at 0x0838, end at 0x0852, byte 0x0853
naturally starts the original handler. No JP-chain needed — saves 3 bytes.

### Prelude byte sequence (25 bytes, fits in the 27-byte window)

```
addr:  bytes               instruction              purpose
0x0838 F5                  PUSH AF                  save A (chain expects clean entry)
0x0839 E5                  PUSH HL                  save HL
0x083A F0 BE               LDH A, [FFBE]            Sara form: 0=W, 1+=D
0x083C B7                  OR A
0x083D 20 04               JR NZ, +4                if dragon, skip to .dragon
0x083F 3E 02               LD A, 0x02               (Sara W → pal 2)
0x0841 18 02               JR +2                    skip dragon path
0x0843 3E 01               LD A, 0x01               (Sara D → pal 1)
0x0845 67                  LD H, A                  H = pal
0x0846 FA 07 FE            LD A, [0xFE07]           current slot 1 attr
0x0849 E6 F8               AND 0xF8                 clear low 3 bits
0x084B B4                  OR H                     merge pal
0x084C EA 07 FE            LD [0xFE07], A           write back
0x084F E1                  POP HL                   restore HL
0x0850 F1                  POP AF                   restore A+F
0x0851 00                  NOP (padding)
0x0852 00                  NOP (padding)
0x0853 ...                 (original STAT handler — fall-through)
```

### Vector patch (1 ROM byte change)

```
0x0049: 0x53 → 0x38       (JP 0x0853 → JP 0x0838)
```

### Caveats to verify in next iteration

1. **Does STAT IRQ fire often enough?** The current STAT trigger (whatever
   it is — possibly LYC or mode 2 for sound timing) might only fire 1-2x
   per frame, which isn't enough to catch every game-write-vs-LCD-read race.
   Test: count STAT fires/frame with a probe.
2. **Does writing 0xFE07 during STAT IRQ break anything?** OAM is accessible
   during mode 0 (HBlank). If STAT fires during mode 1 (VBlank) too, OAM
   write is fine. If during mode 2 or 3, OAM is locked → write is dropped
   (no harm but no benefit).
3. **If STAT IRQ fires too rarely, enable STAT mode-0 bit (0xFF41 bit 3)**
   from the colorize chain — 1-time write at boot to add mode-0 trigger.
   But risk: amplifies STAT call rate from ~2/frame to ~144/frame → may
   break sound timing.

Recommended order for next iteration:
- (a) Install the 25-byte prelude (no STAT enable change).
- (b) Run gargoyle_miniboss test; if pal 6 frequency drops, prelude is
      firing. If it stays at ~58%, current STAT triggers aren't enough.
- (c) If (b) shows need for more triggers, enable mode-0 bit and measure
      phantom-sound risk via the existing D887 watchpoint Lua script.

## What's in the hook now

- 6 BG-table tests (banner/cutscene/splash/postboss/2 arena dispatches)
- 6 OBJ tests on STABLE scenes (non-boss `sara_w_alone`/`sara_d_alone`/
  `crow`/`sara_d_hornet_or_moth`/`jet_form_secret_stage`/
  `spiral_power_active`)
- 12 tests total, ~25-30s wall-clock.

(Iteration 5 expanded this further to 21 tests; iteration 8's STAT prelude
attempt is described below.)

## Iteration 8 — STAT prelude installed, measured, REVERTED

Installed the iteration-7-designed 25-byte STAT prelude at bank0:0x0838 +
vector patch 0x0049: 0x53→0x38. Measured both sides:

**WINS (real, measured):**
- gargoyle_miniboss slot-1 pal-6 frequency: 676/1166 (58%) → 5/1490 (0.34%)
- Slot 1 transitions: 233 → 10
- `moth_miniboss` test went from FAIL → PASS

**REGRESSION (also real, also measured):**
- `sara_w_alone` (D880=0x02, dungeon, FFBE=0): slots 0 and 2 (NOT touched
  by my prelude — it only writes to 0xFE07) now read pal 4 in the OAM
  dump for 86% of frames (1683/1950 frames pal 4 each).
- BUT screenshot still shows Sara correctly as pink (pal 2) — **the LCD
  draws correctly**; only the Lua OAM read is wrong.
- Consensus filter picks pal 4 as the mode → test fails.
- Pre-commit hook blocked the commit (working as designed).

### Hypothesis for the side-effect

My prelude adds ~30 cycles before the chained handler at 0x0853, which
delays the chained handler's `CALL 0x08F8`. Disassembling 0x08F8 reveals
it writes SCY (0xFF42) and SCX (0xFF43) — the BG scroll registers. So the
chained STAT handler is doing **per-scanline parallax scroll**. The 30-
cycle delay shifts WHEN the scroll write hits, which somehow interacts
with the game's main-loop OAM writes such that the Lua OAM-read window
captures pal-4 transient values in slots 0/2 (even though the LCD draws
the correct pal-2 a few cycles later).

### Fix paths for iteration 9+

1. **Gate the prelude on FFBF != 0** (only run during boss fights). The
   sara_w_alone test has FFBF=0 → prelude wouldn't fire → test stays
   passing. Boss saves have FFBF != 0 → prelude fires → alternation fix.
   Need ~5 extra bytes of gating; over the 27-byte ROM budget.
   **Solution: relocate the prelude to WRAM** (0xDB?? area, copied from
   ROM at boot like the levelsel stub). WRAM is bank-agnostic + size
   unconstrained.
2. **Investigate the timing side-effect**: trace what writes to slot 0/2
   between my prelude and the chained handler. Maybe a way to neutralize
   the side-effect without WRAM relocation.
3. **Accept the trade**: install the prelude, exclude `sara_w_alone` from
   the hook. Net hook coverage: -1 + several (boss tests now pass) = net
   positive. But hides a real test regression — not great practice.

**Recommendation:** Option 1 (WRAM relocation + FFBF gate) — cleanest and
addresses the root cause (timing impact in dungeon scenes is unwanted).
Iteration 9+ task.

## Iteration 10 SUCCESS + iteration 11 LIMIT

**Iter 10 (52c7f0b) WIN:** Ungated WRAM STAT-IRQ stub (28 bytes at 0xDB50)
re-stamps OAM slot 1 every IRQ. gargoyle_miniboss pal-6 frequency dropped
**62% → 0.13%**. sara_w_alone still passes (no parallax-timing regression
that iter-8 ROM-prelude had). Hook expanded 21 → 23 tests (+moth,
+gargoyle_miniboss).

**Iter 11 FOUND THE LIMIT:** Extending the WRAM stub to ALSO re-stamp
slot 0 (and 2/3 via loop) regresses gargoyle to ~100% pal-6. The cycle
overhead of the additional re-stamps makes STAT IRQ take longer →
chained parallax handler at 0x0853 runs later → LCD scanline timing
disrupted → consensus filter catches a TOTALLY different (mostly pal-6)
state in slot 1.

Tested variants that all regressed gargoyle:
- 4-slot loop (Sara slots 0,1,2,3): 36 bytes, 99.9% pal-6
- 2-slot unrolled (slots 0,1): 35 bytes, 99.9% pal-6
- The single-slot version (28 bytes, slot 1 only) is the ONLY one that
  fits the STAT-IRQ timing budget without disrupting the chained handler.

So the additional 5 boss-save OBJ tests (spider_*, mage, orc, soldier,
metal_ball_mage_soldier) cannot be unlocked via STAT-IRQ stub extension.
Each needs a different approach:
- spider_*: game-side fix (boss code writes pal 1 to Sara slots)
- mage/orc/metal_ball_*: slot 0 transient — needs a separate IRQ trigger
  OR a structurally different stub
- soldier: slot 12+ DMA-race — outside the colorizer's B=10 cap

These five remain known limitations.

## Iteration 12: spider boss "real visible game bug" — REVISITED iter 100

### Original (incorrect) finding
Probe of `level1_sara_w_spier_miniboss.ss0` over 1491 frames:
- All 4 Sara slots (0-3) = pal 1 (SaraDragon GREEN) for 100% of frames
- FFBE=0 (Sara WITCH form — should be pal 2 pink)
- Screenshot confirms: Sara visually renders GREEN in spider miniboss

### Iter 100 (2026-06-20) revisit — the "bug" is the savestate, not the game
Re-probe with the LIVE spider savestate
`level1_sara1_shield1_item_spider_miniboss.ss0` (the one currently used
by `spider_miniboss_sara_w` in the test YAML):
- Slot 0-3 attrs read **0x32** (pal 2 + flags) at f=60–300, drifting to
  **0x22** (also pal 2) by f=600. All correct pal 2 (Sara WITCH).
- Screenshot at f=600 visually confirms Sara is **pink/peach** (Sara W
  palette), NOT green. Spider miniboss is colorizing CORRECTLY in
  current builds.

The original iter-12 finding was specific to the FROZEN savestate
`level1_sara_w_spier_miniboss.ss0`. Per iter 53's documented
`project_df1f_savestate_transient`: that savestate has DF1F=0xFF
(uninitialized WRAM after ROM-source state load), which gates JP
COLORIZE for the first ~255 frames after load. The colorizer literally
doesn't run during the test window, so Sara slot attrs stay at whatever
the savestate's HW OAM had — which happened to be 0x01 (pal 1) for that
particular capture.

The LIVE savestate (taken from active gameplay) has DF1F=187 < 0xFF,
so the colorizer runs normally and writes pal 2 to Sara slots within
~one frame of load.

**Conclusion**: spider miniboss Sara rendering is NOT a game bug. It's
a savestate-specific artifact of the DF1F gate. The test YAML already
uses the LIVE savestate (the iter-54 switch) — spider_miniboss_sara_w
test passes today.

### Original (now-deferred) fix paths kept for reference

1. **Find and NOP the game's spider-boss OAM write** — requires
   disassembly + identifying which routine writes pal 1 to Sara slots
   during spider scene. Most reliable fix.
2. **Run my re-stamp from a MUCH more frequent trigger** — e.g., LYC
   match at Sara's Y position (LY=80) so re-stamp fires per-frame at
   the exact moment LCD is about to draw Sara. Untested viability.
3. **Game-side patch**: find the spider-boss sprite-init code that
   sets attr=0x01 and change to attr=0x02 (Sara W) or compute from
   FFBE. Cleanest but requires disassembly to locate.

This is queued for future iteration alongside the mage/orc slot-0
transient (similar root cause family — game-side writes too frequent
for my IRQ-driven stamps to catch).

## Iteration 13 — Title menu CRAM patch attempted + reverted

Pivoted to a separate visible improvement: making the title menu text
darker/more readable (light blue on white was hard to read). Implemented
a 16-byte `build_title_menu_override()` at bank13:0x7FCE that fires when
D880=0x1C and writes BGP0 color 1 = 0x0000 (black) via BCPS/BCPD.

Verified CRAM dump: color 1 = 0x0000 ✓ (override took effect).

**REVERTED:** screenshot showed the menu with a glitched red background
instead of the original clean white-with-light-blue-text. The CRAM
write from my override (via BCPS auto-increment) somehow interacts
poorly with cond_pal (the hash-cached palette loader) or bg_sweep —
possibly the auto-increment leaves BCPS pointing at color 2 lo byte,
which then gets written by some other downstream code with the wrong
value. Or the CALL adds cycles that push colorize+bg_sweep past VBlank
into rendering window.

Without override: menu renders as user originally saw it (white BG,
visible light-blue text — readable, just light-colored).
With override: red BG floods everything.

For now: leave title menu alone. The user has not complained about
title legibility and the safe baseline is acceptable. Future iteration
could investigate the BCPS auto-increment interaction OR rewrite to
write all 4 colors explicitly (set BCPS without auto-inc, write each
color).

No code changes this iteration. Documented for next session.

## Iteration 14 — Colorizer tile 0x10-0x1F → sara_palette attempted + reverted

Tried a 1-byte ROM patch to colorizer at offset 49: change JR NC offset
from 0x0B (jump to pal_4) to 0x1B (jump to sara_palette). This would
route tiles 0x10-0x1F (Sara's secondary body sprites per iteration-1
audit) to Sara's form palette (D = 2 W or 1 D) instead of pal_4 (Hornet
orange).

The patch installed cleanly (verified bytes 0x1B at offset 49). gargoyle
alternation preserved (0.13% pal-6). hornets test PASSED (Sara D
secondary tiles now correctly routed).

**REVERTED** because sara_w_alone test now FAILS — slot 3 with tile 0x23
(in Sara range 0x20-0x2F, untouched by my change) reports pal 4 in OAM
dump. My direct probe of slots 0-3 across frames 50-75 shows ALL pal 2.

Same root-cause family as iteration 8: the colorizer change introduces
a TIMING side-effect (cycles spent processing tile 0x10-0x1F via the
new sara_palette branch) that interacts with the Lua test runner's
sample-window catching slot 3 mid-transition. The LCD probably still
draws Sara correctly (per the direct probe), but the test reads see
a transient pal 4 in slot 3.

Trade-off rejected: -sara_w_alone vs +hornets is net -1 hook coverage,
and the visual benefit (Sara secondary sprites consistent with body)
is small.

Same pattern: any colorizer/STAT/prelude cycle change that affects the
chained handler timing tends to introduce a downstream OAM-read
inconsistency in some other save state. The 1-slot WRAM STAT-IRQ stub
from iteration 10 is the only such change that has survived hook
verification — and only because WRAM placement happens to have
consistent timing across LCD modes.

Conclusion: 5 remaining boss-save OBJ failures + tile 0x10-0x1F
secondary-sprite improvement all need to wait for either (a) a
fundamentally different IRQ mechanism, or (b) game-side fixes that
attack the source of OAM writes. STAT-IRQ approach is exhausted.

## Iteration 15 (2026-06-18) — switched dump_oam to dedicated OAM accessor

**Hypothesis:** mGBA's `emu:readRange(0xFE00, 0xA0)` is the generic memory
accessor. There's also `emu.memory.oam:readRange(0, 0xA0)`, a dedicated
OAM-region userdata exposing read8/readRange. Theory: the dedicated
accessor takes a more atomic snapshot at the emulator-time point of the
Lua callback, possibly avoiding the cross-region timing drift that
iter 8/14 stumbled on.

**Result:**
- Switched the test runner's `dump_oam` to `emu.memory.oam:readRange(0, 0xA0)`.
- All 23 hook tests still pass — no regression.
- Re-ran iteration 14's colorizer patch (`colorizer[49]=0x1B`, redirecting
  tiles 0x10-0x1F to sara_palette) on top of the new accessor. `sara_w_alone`
  STILL FAILS on slot 3.

**Conclusion:** the iter-14 failure is NOT a Lua-sample-window artifact —
the colorizer change is a real regression. Some downstream interaction
(likely cycle-budget shift in the chained handler or attr buffer
write timing) genuinely flips slot 3 to pal 4 in `sara_w_alone`.

The OAM-accessor improvement is kept as a defensive infrastructure
upgrade even though it doesn't unlock any additional tests. It eliminates
"is this a probe-vs-runner discrepancy?" as a question in future
iterations.

