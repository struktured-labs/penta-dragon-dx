# iter 278b/c — additional fix attempts (all reverted)

After iter 278's candidate J + pal_0 fallback both failed, attempted
two more angles in the same session. Both reverted.

## iter 278b — shift hwoam_recolor to start at slot 10

**Idea**: skip Sara's slot 0-9, only stamp slot 10-39. Sara would
inherit pal-2 from shadow_main's pre-DMA stamps; hwoam_recolor's
mode-locked race only affects slot 10+ (enemies/projectiles).

**Change**: `LD HL, 0xFE03 → LD HL, 0xFE2B` (slot 10 attr); `LD B, 40 → LD B, 30`.

**Result**: slot 2 race ELIMINATED (113 → 0) per probe. 

**BUT** — the critical test sweep showed Sara slot 0 = pal-1 (Sara
Dragon) instead of pal-2 (Sara Witch). The hwoam_recolor's stamping
of slot 0-3 with pal-2 is REQUIRED to correct a pal-1 transient that
arrives via shadow OAM / DMA. Without hwoam_recolor's slot 0-9 stamp,
Sara renders as Dragon (green) instead of Witch (pink).

Probe at savestate `level1_sara_w_alone.ss0` confirmed:
- FFBE=0 (witch form), FFBA=0 (no boss)
- HW OAM slot 0 attr=0x01 (pal-1, WRONG)
- Shadow A slot 0 attr=0x00 (pal-0, unstamped)

This means:
- shadow_main does NOT stamp shadow A slot 0 with pal-2.
- DMA copies shadow A → HW with pal-0.
- Some OTHER writer (game logic or STAT IRQ) writes pal-1 to HW slot 0.
- hwoam_recolor at B=40 OVERWRITES pal-1 with pal-2 (correct).

So hwoam_recolor's role is essential for slot 0-9. It's not just
about slot 10+ items as the iter 31 comment implies.

## iter 278c — pal_0 fallback (also see iter278_candidate_j_attempted.md)

Already documented in iter278_candidate_j_attempted.md.
Single-byte change at 0x6A37 (LD A, 4 → LD A, 0).
Slot 2 race 113 → 59 (48% reduction) BUT broke orc + spiral
(game legitimately uses tile-0x80+ → pal_4 for those sprites).

## Summary of all iter 276/277/278 attempts

| Iter | Approach | Race fix | Tests | Verdict |
|---|---|---|---|---|
| 276 | Deep RE — no code change | — | All pass | Audit only |
| 277 | B=40 → B=20 | 113→23 (80%) | 4 CRAM regressions | Reverted |
| 278a | Candidate J at 0x6B27 | 113→12 (89%) | spiral/gargoyle/soldier break | Reverted |
| 278b (pal_0 fallback) | LD A, 4 → 0 in colorizer | 113→59 (48%) | orc/spiral break | Reverted |
| 278c (slot 10+ only) | HL=0xFE2B, B=30 | 113→0 (100%) | Sara slot 0 = pal-1 | Reverted |

## Final state

Build state unchanged from iter 276. ROM and tests are in a known-good
test-passing state. The half-orange Sara race is genuinely visible
(22% of frames) but not fixable without:

1. **Dual-pointer colorizer** (~100 bytes new code) — read tile from
   SHADOW (never mode-locked), write attr to HW.
2. **Source pal-1 transient** — find the upstream writer that produces
   pal-1 on slot 0-3 (game logic? STAT IRQ?), patch it to write pal-2
   directly. Removes need for hwoam_recolor's post-DMA correction.
3. **Reduce VBlank work elsewhere** so hwoam_recolor reliably fits
   inside mode 1, preventing mode-lock contamination.

Any of these requires deeper investigation than fits an autonomous
loop iteration. Documented for future deep-RE sessions.
