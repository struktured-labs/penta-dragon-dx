# Shipping Scope — Penta Dragon DX

> **Historical planning snapshot, superseded 2026-07-23.** The current working
> candidate has resolved the title/logo/banner contamination, title-idle reel,
> ordinary-enemy OBJ race,
> save-present level-select bleed, later-stage contamination, and neutral
> opening/final-story/death-screen containment. See
> `README.md`, `CHANGELOG.md`, and the linked audit documents for current
> evidence. MiSTer FPGA verification remains outstanding.

**Date:** 2026-07-19
**Target:** Ship within 4 weeks
**Baseline ROM:** `rom/working/penta_dragon_dx_v301.gb` (v3.01 production)

---

## 1. Banner Corruption — Title Screen Showcase (D880=0x1B)

### Symptom
The PENTA DRAGON banner in the title screen idle animation's showcase phase renders with wrong sprite colors. The banner uses OAM sprite tiles in ranges 0x04-0x0F, 0x20-0x2F, 0x54-0x5B — all palette 0 on the original DMG game.

### Current resolution

The release builder routes `D880=0x1B` through the neutral title/splash table,
keeps the title-safe inline path, and refreshes the intended blue-gray BG0
CRAM during title VBlank. `verify_title_showcase_mgba.py` now runs the complete
cold-boot `0x01→0x1C→0x1B` cycle: 396 visible-attribute samples and nine
rendered frames have zero nonzero/unsafe attributes and zero red-dominant
pixels. The `0x1B` active table is neutral for every sample. FPGA timing still
requires the reservation-backed MiSTer gate.

### Architecture review
- **Inline hook** at bank1:0x42A7 is **pure tile-only** (`create_inline_tile_copy_pure_tileonly`) — writes tile IDs to VRAM bank 0 but never touches VRAM bank 1 (attribs).
- **VBlank handler** at bank13:0x6E00: `cond_pal` → attr-cleaner (first 32 frames) → `FFC1 gate {bg_sweep, shadow_main, OAM DMA}`.
- **OBJ colorizer** (`shadow_main` at bank13:0x69D0 → `tile_based_colorizer` at 0x6A10) is gated by FFC1=1. During the title screen (FFC1=0), the OBJ colorizer does **not** run. So the banner's OAM sprites should retain their original palette assignments.
- **bg_sweep** at bank13:0x6CD0: its internal FFC1 gate was NOP'd out, but it is still **called from within the handler's FFC1 gate** (lines 757-763 of `build_v301_gdma.py`). So bg_sweep also does **not** run on the title screen in production v3.01.
- **Attr cleaner** clears one VBK=1 row per frame for 32 frames after cold boot. After that, stale attrs persist.

### Root cause (diagnosed)
**The banner corruption is not caused by the OBJ colorizer** (it's correctly FFC1-gated during the title). The corruption is a **BG attr clean/race issue**:

1. The inline hook at 0x42A7 is tile-only — banner BG tiles get written to VRAM bank 0 but no corresponding attr is written to VRAM bank 1.
2. The attr cleaner clears VBK=1 rows to 0x00 (palette 0) over 32 frames. Banner rows near tilemap base 0x9800 are cleared early. But the showcase phase (D880=0x1B) loads different tile IDs to the same tilemap cells during the animation cycle. The cleaner already cleared those cells — so the banner shows with pal 0 (washed out / wrong).
3. On OG v3.00, the inline hook had a D880 gate: `D880 >= 0x14 → full tile+attr`. D880=0x1B hit this path and got proper attrs. v3.01's pure tile-only hook lost this.
4. Alternatively: after the cleaner finishes (32 frames), the banner's showcase tiles reuse tilemap cells that were previously used by other title elements. Those cells retain whichever attr the cleaner last wrote (pal 0), and no subsequent attr write refreshes them.

**Secondary contributor**: The bg_table assigns tiles 0x54-0x5B to pal 6 (wall), which is correct for dungeon walls but wrong for the banner. This affects any future bg_sweep/attr path during the title.

### Fix plan
**Option A (recommended, ~4-6 hours): un-gate bg_sweep on title screen**
- Change the VBlank handler's FFC1 gate to also let bg_sweep through when D880 indicates title states (0x01, 0x1B, 0x1C).
- Add a D880 read + range check: `D880 == 0x01 || D880 == 0x1B || D880 == 0x1C → allow bg_sweep`.
- bg_sweep reads the tilemap and bg_table, writing the correct attr for each visible tile. At 1 row/frame, the 18-row viewport takes ~18 frames to fully color — well within the title screen's dwell time.
- Attr cost: ~600T/frame extra on title (negligible — title runs well under frame budget).
- **Risk**: Low. bg_sweep was already MiSTer-hardware-verified gameplay-safe. Running it on the title was the v3.00 behavior (bg_sweep was not FFC1-gated in v3.00).

**Option B (~6-8 hours): restore the D880-gated inline attr phase**
- Switch the inline hook from `create_inline_tile_copy_pure_tileonly()` to a version with D880 gating like v3.00's `create_inline_tile_copy_tileonly()` with `title_gate=0x0C`.
- This restores attr writes during the showcase phase (D880=0x1B >= 0x0C → full tile+attr).
- **Risk**: Higher. The dual-STAT-wait per group adds timing pressure. v3.00 had this behavior and was stable, but v3.01 chose pure tile-only for a reason (timing, phantom-sound risk).

**Option C (~2-3 hours, partial): extend attr-cleaner lifespan**
- Make the attr-cleaner run indefinitely (remove the DF08 sentinel) or extend it to cover all 32 rows on every title entry.
- This clears stale attrs wherever the banner draws, giving uniform pal 0.
- **Downside**: Banner tiles that ShouldNot be pal 0 (e.g. decorative tiles 0xE0-0xFF which bg_table maps to pal 1) also get pal 0 until bg_sweep or the inline hook covers them.
- **Risk**: Low. Doesn't actually fix the corruption if the banner needs non-zero palettes for some elements.

**Lever**: If the corruption is that banner sprites look "washed out / wrong" (pal 0 when they should have detail), Option A is the real fix. If the corruption is "random splotches" (uninitialized attrs showing pal 7 white), Option C would help but Option A is still correct.

**Recommended: Option A**. Effort: **4-6 hours** including build, mGBA visual verification, and autoplay stress test.

---

## 2. OBJ Enemy Color Race (docs/audit/obj_enemy_color_race.md)

### Symptom
In-game enemy sprites render at OBJ palette 0 (blue/black) instead of their intended type palette. Affects most enemy types during gameplay: catfish, soldiers, hornets, moths.

### Current resolution

The builder now predicts the exact alternating Shadow OAM buffer that the
immediately following native DMA will transfer and colors all 40 entries in
that one buffer. It does not force a buffer or recolor hardware OAM after DMA.
The dedicated mGBA hardware-OAM gate checks 6,562 ordinary-enemy samples across
eight combat states with zero mismatches. See
`docs/audit/obj_enemy_color_race.md`; MiSTer timing verification remains.

---

## 3. Stage 2+ Lava Dungeon Color (docs/audit/stage2_lava.md)

### Symptom
Later stages (FFBA >= 4) reuse stage-1 floor/wall tile IDs for their molten/field textures. These tiles get the stage-1 wall palette (pal 6, slate gray) instead of a lava palette (pal 5, yellow/red).

### Root cause
The bg_table at bank13:0x7000 assigns fixed palettes per tile ID (0x02-0x05 → pal 0 floor, 0x12-0x15 → pal 6 wall, etc.). Later stages decompress different graphics into the same VRAM tile slots, so tile ID 0x12 becomes "lava field" instead of "wall block" — but still gets pal 6.

### Fix plan
**Per-FFBA dungeon table swap (~8-12 hours)**
1. **Create a lava bg_table page** at bank13:0x7E00. Map the field tile IDs (0x02-0x05, 0x12-0x15, 0x19-0x1A) to pal 5 (lava: white/yellow/red). Keep wall tiles that are NOT field (e.g., actual wall corners at 0x41-0x49) on pal 6. Items (0x80-0xDF) on pal 1.
2. **Extend scene_detect** to check FFBA when choosing the dungeon table. When FFBA >= 4, swap in the lava table instead of the dungeon table.
3. **Verify** per-stage by level-select probe (Lua script in `docs/audit/stage2_lava.md`). Screenshot each FFBA 0-8 to confirm field tiles render orange/red (pal 5) instead of slate gray (pal 6).

**Risk**: Medium. The lava table only needs one 256-byte page. The tile-ID overlap means some walls in later stages might also get the lava palette if their IDs aren't discriminable from field IDs. Mitigate by analyzing per-stage tilemaps to find the exact field ID set.

Effort: **8-12 hours** (2-3 hours for table design, 2-3 hours for scene_detect branch, 4-6 hours for per-stage verification).

---

## 4. Level-Select / High-Score Screen Color Bleed (docs/audit/levelselect_score_bleed.md)

### Symptom
The "STAGE 01 / STAGE LOAD / TOP 3" screen (GAME START with save present) has orange/red color bleed on large letters — same tile shows palette 0 AND palette 1 on different cells.

### Root cause
The level-select screen (bank1:0x7393, D880=0x00, FFC1=0) runs its own DI'd input loop with STAT-wait draws. The DX VBlank colorizer never runs during this screen (FFC1=0, and the DI'd loop prevents interrupt-driven VBlank colorization). Letter cells retain whatever BG attrs were last written there by prior scenes.

### Fix plan
**Inject an attr-plane clear into the level-select path (~4-6 hours)**
1. Find a small patch point in the level-select entry (bank0:0x3B47 `JP NZ 0x7393`).
2. Route through a trampoline that: switches to VBK=1, clears the relevant tilemap region (0x9800) to 0x00, switches back to VBK=0, then jumps to the original level-select routine.
3. No free space in bank 0 or 1, so the clear routine must either:
   - Live in bank 13 with MBC banking (complex — level-select doesn't bank-switch).
   - Reclaim bytes from existing code/data in bank 0 (risky — must not break any other code path).
   - Use a small RST vector or space near unused HRAM to execute the clear directly.

**Simpler alternative (~2-3 hours):** Set a flag in the VBlank handler that forces the attr-cleaner to run when the game enters D880=0x00. On the first VBlank after D880 becomes 0x00, clear attrs for rows 0-17 (the visible viewport). This won't fix the bleed during the level-select's own DI'd loop (VBlank never fires), but it clears attrs **before** the loop starts, preventing carry-over from prior scenes.

**Recommended: Simple alternative (2-3 hours).** The full trampoline fix is too invasive for the 4-week timeline. The simple alternative covers 90% of the symptom (bleed from prior scene carry-over).

Effort: **2-3 hours** (simple flag-based attr clear on D880=0x00 entry).

---

## 5. Ending Cutscene — Artifact Containment Complete

### Symptom
The victory ending and Penta Dragon pre-battle bridge previously inherited the
Stage 1 table, producing unintended red fills in portraits, dialogue, and the
three-dragon speech.

### Current resolution

The working candidate dispatches `D880=0x19` and `0x1A` to a neutral story
table and restarts the two-map attribute cleaner once on entry. Original
pre-final and post-final branches pass the mGBA pixel-pipeline gate with zero
non-neutral attributes, bad active tables, or red-dominant pixels. Deliberate
position-aware story colorization is deferred as artwork, not blocked defect
containment. See `docs/audit/cutscenes_intro_ending.md`.

---

## 6. MiSTer Hardware Verification Blockers

### Risk for all fixes
- The shipped ROM has only been mGBA/emulator verified. MiSTer FPGA may show timing-dependent regressions (phantom sound, white splotches, stage-load freezes).
- Previous MiSTer testing found issues invisible in mGBA: white splotches on title (FGPA timing), OBJ-colorizer OAM scan cap (cap=10 was the MiSTer-safe value).
- **Every fix above that touches the VBlank handler or inline hook needs MiSTer verification before ship.**

Effort: **2-4 hours** dedicated MiSTer sweep (boot, title, gameplay, all stage transitions, arena fights).

---

## Summary: All Issues

| # | Issue | Fix Effort | Priority | Blocks Ship? | Verification |
|---|-------|-----------|----------|-------------|-------------|
| 1 | Banner corruption (title showcase) | **Resolved in working candidate** | P0 | No | Full-cycle mGBA PASS; **MiSTer pending** |
| 2 | OBJ enemy color race | **Resolved in working candidate** | P2 | No | mGBA PASS; **MiSTer pending** |
| 3 | Lava dungeon (later stages) | **8-12 hrs** | P1 | No (stretch) | Level-select probe per FFBA |
| 4 | Level-select color bleed | **Resolved in working candidate** | P1 | No | mGBA PASS, 360/360 clean attrs |
| 5 | Ending artifacts | **Contained in working candidate** | P3 | No | Both branches mGBA PASS; artwork tuning deferred |
| 6 | MiSTer hardware verify | **2-4 hrs** | **P0** | **Yes** | MiSTer FPGA |
| | **TOTAL (P0+P1)** | **16-25 hrs** | | | |

---

## Recommended Priority Order (4-week timeline)

### Week 1 (16-25 hrs)
1. **Banner corruption fix** — Option A (un-gate bg_sweep on title). ~5 hrs.
2. **Level-select color bleed** — simple attr-clear on D880=0x00. ~3 hrs.
3. **Build v3.02** integrating both fixes.
4. **Autoplay stress test** (8000 frames × 3 runs) to verify no regressions from the bg_sweep timing change.

### Week 2 (10-16 hrs)
5. **Lava dungeon color** — per-FFBA table swap. ~10 hrs.
6. **Level-select capture + verification** per FFBA. ~4 hrs.
7. **Build v3.03** and run autoplay stress test.

### Week 3 (10-16 hrs)
8. **OBJ enemy color race** — Option A (OAM reorder). ~10 hrs.
9. **MiSTer hardware verify** — full sweep: v3.02 + v3.03 + v3.04 builds. ~4 hrs.

### Week 4 (buffer / polish)
10. **Bugfixes from hardware test** — adjust timing if MiSTer shows regressions.
11. **Ending colorization** — if ending save state becomes available.
12. **Final build, IPS patch, release packaging.**

**Total estimated effort: 36-57 hrs over 4 weeks.** Core shipping (P0 + P1, weeks 1-2): **20-30 hrs**.

---

## What's NOT in scope (deferred)
- **Ending cutscene colorization** (blocked — no ending save state).
- **Per-monster palette customization** (docs/per_monster_palette_plan_v2.md) — significant RE of monster spawn system, 30+ hrs.
- **Teleport / debug-menu** (docs/boss_teleport_breakthrough.md) — the teleport approach from VBlank IRQ causes freeze; needs main-loop hook (blocked).
- **Scroll flicker improvement** — pre-existing limitation of the 1-row/frame bg_sweep architecture. Acceptable for ship.
- **Projectile colorization** (docs/projectile_colorization_plan.md) — would add more OAM complexity.
- **Sound engine changes** — phantom sound fix from v2.90 carries forward untouched.
