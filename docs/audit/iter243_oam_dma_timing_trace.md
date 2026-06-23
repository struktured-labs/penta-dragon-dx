# iter 243 — OAM DMA timing window trace

## Context
Per iter 242's audit, the next step before any code-modification fix
attempt was: "trace the DMA window vs hwoam_recolor's CALL position
to assess feasibility of path B".

## VBlank wrapper execution order (verified via `scripts/build_v301_teleport.py:1183-1228`)

The teleport-routine wrapper at `bank13:WRAPPER_ADDR` runs from the
patched VBlank hook at `0x0824`. Per-VBlank order:

| Step | Code | Approx T-cost |
|---|---|---|
| 1 | PUSH BC/DE/HL (3× 16T) | 48T |
| 2 | 8-cycle debounced joypad read | ~100T |
| 3 | CALL teleport_routine (scene_detect + lava override + JP colorize+DMA) | ~variable |
| 4 | **CALL hwoam_recolor** (post-DMA OAM stamp) | ~variable |
| 5 | POP HL/DE/BC + RET | 30T |

hwoam_recolor IS positioned post-DMA by design. The comment at line
1220 reads: `# --- Post-DMA HW-OAM recolor (enemies; items 3,4,6,11) ---`.

So the original race documented in iter 241/242 ISN'T about
hwoam_recolor running before DMA — it runs *after*. The race must
involve a DIFFERENT OAM write path that runs *between* the wrapper's
RET and the next VBlank's `frame` callback observation.

## Candidate non-VBlank OAM writer: STAT IRQ stub

`scripts/build_v301_teleport.py:413-455` defines a WRAM-resident STAT
IRQ stub at `0xDB50`. It:
1. Reads FFBE (Sara form: 0=Witch, !=0=Dragon)
2. Sets B = 2 (Witch) or 1 (Dragon)
3. Reads slot 1 attr byte (0xFE07), clears pal bits, ORs in B
4. Writes back to 0xFE07
5. JPs to 0x0853 (original handler)

Critical observation: this stub is UNCONDITIONAL (no FFBF gate visible
in the current code). It runs on EVERY STAT IRQ — multiple times per
frame during HBlank (per scanline if the LCD STAT interrupt fires
that often).

The stub touches ONLY slot 1 — so it correctly keeps slot 1 stable
(probe confirms: slot 1 had only 4 ATTR changes over 540 frames).

But it does NOT touch slot 0 or slot 2 — which is consistent with
the probe finding 32 and 121 ATTR changes respectively on those
slots.

## The smoking-gun comment

`scripts/build_v301_teleport.py:418-421`:
> Iteration 8 demonstrated that an unconditional ROM-resident prelude
> (at 0x0838, falling through to 0x0853) introduced a ~30-cycle delay
> that shifted the chained parallax-scroll handler's SCY/SCX writes,
> which exposed a slot 0/2 transient pal-4 read in dungeon scenes
> (sara_w_alone OAM dump failed even though LCD rendered correctly).

**This documents the EXACT bug I'm now observing on the current
codebase.** The "slot 0/2 transient pal-4 read" is real and known.
The iteration-8 ROM-resident prelude attempt exposed it. The
iteration-10 WRAM-resident stub was supposed to AVOID it (per the
comment at line 432-437) but the probe shows it still occurs on
stage1_entry_pink_renders.ss0.

## What the parallax-scroll handler likely does

The chained parallax-scroll handler must be writing to OAM (or causing
a memory aliasing read of OAM via DMA register reuse) at HBlank
boundaries. The timing window where slot 0/2 momentarily shows pal 4
is precisely when this handler executes.

To confirm this, the next probe iteration should:
1. Hook the LCD STAT IRQ
2. Sample slot 0 and slot 2 attrs at the entry AND exit of the IRQ
3. Identify which IRQ (LY value) causes the pal-4 read

## Fix-path analysis update

Updating iter 242's two candidate fix paths with new information:

**Path A (patch ROM-source OAM bytes)**: The ROM-source OAM for Sara
secondary tiles 0x18/0x1B is correctly set elsewhere (per probe finding
that they DO display as pal 2 most of the time). The pal-4 read isn't
from ROM-source OAM — it's a transient HBlank-window artifact.
Path A is likely the WRONG approach.

**Path B (move hwoam_recolor CALL later)**: Already post-DMA. Can't
move later within VBlank without breaking other timing. Path B is
also likely the WRONG approach.

**Path C (NEW — STAT IRQ stub extension)**: Modify the STAT IRQ stub
to ALSO stamp slot 0 and slot 2 attrs (not just slot 1). This would
be the symmetric fix — if slot 1 is stable via the stub, extending
to slot 0+2 would close those gaps too.

Caveat: iter 235 already attempted this and broke 50 tests because
"slots 0+2 in non-Sara scenes (mini-boss, stage transitions, jet form)
legitimately hold non-Sara palettes". The extension would need to
gate by SCENE (e.g., only stamp during D880=0x02 dungeon).

**Path D (NEW — instrument the parallax handler)**: Before any fix
attempt, write a probe that hooks STAT IRQ entry and slot 0/2 attr
read at each LY value. This identifies the EXACT HBlank window where
the pal-4 read occurs. Without this, any fix is dart-throwing.

## Recommendation
Implement Path D next iter: a STAT IRQ-aware probe that pinpoints
the LY-specific moment when slot 0/2 attrs flicker to pal-4.
Then either fix the parallax handler OR add a scene-gated STAT IRQ
stub for slot 0+2 (Path C with iter 235 lessons applied).

NO code change this iter. Pure RE + audit.
