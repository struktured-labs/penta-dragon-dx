# Audit: Monster / OBJ Sprite Colorization

Static analysis only. Verified against the shipped binaries
`rom/working/penta_dragon_dx_FIXED.gb` (synced production v3.01),
`rom/working/penta_dragon_dx_v301.gb`, and
`rom/working/penta_dragon_dx_teleport.gb` — the OBJ colorizer + palette
tables are **byte-identical in all three** (verified by reading bank-13
bytes directly, below).

Source of truth:
- OBJ colorizer code generators: `scripts/bg_experiment.py`
  - `create_tile_based_colorizer` (lines 107-165)
  - `create_shadow_colorizer_main` (lines 168-187)
  - `create_palette_loader` (lines 190-250)
  - `load_palettes_from_yaml` → OBJ palette byte layout (lines 38-104)
- Build that places them: `scripts/build_v301_gdma.py` (lines 411-455)
- `scripts/build_v301_teleport.py` imports `build_v301` from gdma
  (line 41) and adds **only BG** per-arena colorization — OBJ path is
  unchanged.
- Palette colors: `palettes/penta_palettes_v097.yaml` (`obj_palettes`,
  `boss_palettes`).
- Subsystem doc: `docs/obj_colorizer.md`.

---

## (1) EXACTLY how OBJ palettes are assigned

### Mechanism: by sprite **tile ID range**, via inline CP/JR branching.

There is **no OBJ lookup table** and **no OAM-slot / entity-type
keying**. The `SCALABLE_PALETTE_APPROACH.md` 256-byte tile→palette LUT
was a *design proposal that was never adopted for OBJ*; the live code is
the hand-branched `create_tile_based_colorizer`. (A 256-byte LUT *does*
exist, but only for **BG** tiles at bank13:0x7000 — see
`create_bg_tile_table`, `BG_TABLE_BYTES`.)

Each VBlank, the colorize handler calls `shadow_main` at **bank13:0x69D0**,
which:
1. Reads `FFBE` (Sara form: 0=Witch → D=2, nonzero=Dragon → D=1).
2. Reads `FFBF` (boss flag). If nonzero, indexes the **boss_slot_table**
   at **bank13:0x68C0** with `(FFBF-1)` to get a boss palette slot into
   register E; else E=0.
3. Calls the inner colorizer at **bank13:0x6A10** twice, once for each
   shadow-OAM buffer: `HL=0xC003` (buffer 1) then `HL=0xC103` (buffer 2).
   (Note `0xC0xx`/`0xC1xx` are the shadow OAM buffers; the doc/memory map
   also lists them at 0xC000/0xC100 — same buffers, the colorizer just
   starts at the attribute byte +3.)

Inner colorizer (`bank13:0x6A10`) loops **40 OAM entries** (`LD B,0x28`;
shipped byte at 0x6A11 is `0x0A` in gdma but the frozen generator emits
`0x28` = 40 — see note below) and for each entry reads the **tile-ID
byte** (OAM offset +2), then dispatches purely on tile-ID magnitude:

```
tile == 0x00                      -> skip (invisible sprite)
boss active (E!=0) AND tile>=0x30 -> palette = E   (boss override)
tile 0x00-0x01                    -> palette 3   (Sara proj + crow)
tile 0x02-0x0F                    -> palette 0   (default/effects)
tile 0x10-0x1F                    -> palette 4
tile 0x20-0x2F                    -> palette D   (Sara: 1 or 2 by FFBE)
tile 0x30-0x3F                    -> palette 3
tile 0x40-0x4F                    -> palette 4
tile 0x50-0x5F                    -> palette 5
tile 0x60-0x6F                    -> palette 6
tile 0x70-0x7F                    -> palette 7
tile 0x80+                        -> palette 4   (fallback)
```

Apply step (`apply_palette`, 0x6A10 generator lines 153-154):
`A=[HL]; A &= 0xF8; A |= chosen_palette; [HL]=A` — i.e. it overwrites
only OAM attribute bits 0-2 (CGB OBJ palette select), preserving
priority/flip/VRAM-bank bits.

**NOTE on loop count discrepancy (real, worth a probe):**
`create_tile_based_colorizer` emits `06 28` (`LD B,40`) at offset 0, but
`build_v301_gdma.py` line 450 does `colorizer[1] = 0x0A`, overwriting it
to `LD B,10`. The shipped ROM confirms byte at 0x6A11 = `0x0A` (10).
So the **production OBJ colorizer only scans the first 10 OAM entries per
buffer (20 total across both buffers)**, not all 40. `docs/obj_colorizer.md`
documents `LD B,40` and a ~7200T cost — that doc is describing the
generator, not the shipped value. Real shipped cost is ~1/4 of that.
This 10-entry cap is a hard constraint on any "more monsters colored"
proposal: monsters in OAM slots 10-39 are **never recolored today**.

### The boss override path (FFBF) is a *separate* mechanism from tiles.
When a boss/mini-boss is on screen, **every** sprite with tile>=0x30 is
forced to the single boss palette slot (E), regardless of its own tile
range. So during a boss fight, *all* non-Sara, non-projectile sprites
collapse to one palette. Sara (0x20-0x2F) and projectiles (0x00-0x01)
are exempt.

### Palette RAM loading (which colors live in each OBP slot)
`create_palette_loader` (bank13:0x6900, called via conditional wrapper
cond_pal at 0x6C90) writes CGB OBJ palette RAM each frame:
- Copies the 8×8-byte `obj_data` block (bank13:0x6840) into OBP0-7.
- Dynamically overrides **OBP0** with projectile colors by form/powerup
  (Sara W/D, spiral/shield/turbo) — see `obj_data` OBP0 below.
- Overrides **OBP1/OBP2** with jet-form colors when stage flag set.
- When `FFBF!=0`, indexes boss_slot_table → slot, computes OCPS =
  slot*8 (fixed in v3.01: `ADD A,A x3`, bank13 ~0x6924, see comment at
  bg_experiment.py:236-243), and writes the boss's 4 colors
  (boss_palette_table @ bank13:0x6880, indexed by FFBF-1) into that slot.

---

## (2) Inventory of all 8 CGB OBJ palettes (verified bytes from FIXED.gb)

`obj_data` block @ bank13:0x6840 (BGR555):

| OBP | Name (YAML)          | Colors (trans,c1,c2,c3)        | Used by |
|-----|----------------------|--------------------------------|---------|
| 0   | EnemyProjectile      | 0000 7C00 5800 3000 (blue)     | tile 0x02-0x0F + 0x80+ fallback; **dynamically replaced** with Sara-projectile / powerup colors by palette_loader |
| 1   | SaraDragon           | 0000 03E0 01C0 0000 (green)    | Sara tiles 0x20-0x2F when FFBE!=0 (Dragon); replaced by SaraDragonJet (cyan) in bonus stage |
| 2   | SaraWitch            | 0000 2EBE 511F 0842 (skin/pink)| Sara tiles 0x20-0x2F when FFBE==0 (Witch); replaced by SaraWitchJet (magenta) in bonus stage |
| 3   | SaraProjectileAndCrow| 0000 001F 0017 000F (red)      | tile 0x00-0x01 (Sara shots) AND tile 0x30-0x3F (crows) — **shared** |
| 4   | Hornets              | 0000 03FF 00DF 0000 (yellow)   | tile 0x10-0x1F AND tile 0x40-0x4F AND 0x80+ fallback |
| 5   | OrcGround            | 0000 02A0 0160 0000 (green)    | tile 0x50-0x5F (orc/ground) |
| 6   | Humanoid             | 0000 7C1F 4C0F 0000 (purple)   | tile 0x60-0x6F (soldier/moth/mage); **also** boss slot for FFBF=1,3,5,7 |
| 7   | Catfish              | 0000 7FE0 3CC0 0000 (cyan)     | tile 0x70-0x7F (catfish); **also** boss slot for FFBF=2,4,6,8 |

boss_slot_table @ bank13:0x68C0 = `[6,7,6,7,6,7,6,7]` (FFBF 1..8).
boss_palette_table @ bank13:0x6880 (overwrites the slot above):

| FFBF | Boss          | Slot | Colors |
|------|---------------|------|--------|
| 1 | Gargoyle (mini)  | 6 | 0000 601F 400F 0000 |
| 2 | Spider (mini)    | 7 | 0000 001F 00BF 0000 |
| 3 | Boss3 Crimson    | 6 | 0000 0CBF 0859 040F |
| 4 | Boss4 Ice        | 7 | 0000 7F94 668A 4940 |
| 5 | Boss5 Void       | 6 | 0000 70B4 584F 3C08 |
| 6 | Boss6 Poison     | 7 | 0000 0BC8 06C4 01C0 |
| 7 | Boss7 Knight     | 6 | 0000 0F1F 0A58 0150 |
| 8 | Angela (secret)  | 7 | 0000 7FFF 5AD6 318C |

### Summary by role
- **Sara (witch/dragon forms):** OBP1 (Dragon) + OBP2 (Witch). Jet
  variants reuse the same two slots in the bonus stage. **2 slots.**
- **Projectiles:** OBP0 (enemy + dynamic Sara/powerup) + OBP3 (Sara
  shots, but OBP3 is *shared* with crows). **~1.5 slots.**
- **Monsters (regular):** OBP3 (crow), OBP4 (hornet), OBP5 (orc),
  OBP6 (humanoid), OBP7 (catfish). **5 slots, but several shared with
  other roles.**
- **Bosses:** time-share OBP6/OBP7 (the slot is overwritten with boss
  colors while FFBF!=0). **0 dedicated slots** — they steal humanoid /
  catfish.

---

## (3) Are monster types SHARING palettes today? YES — heavily.

Distinct monster *types* the game uses (per tile-range table +
`obj_palettes` comments): crow, hornet, orc/ground, humanoid
(soldier+moth+mage **all collapsed into OBP6**), catfish, plus the
mini-bosses and 8 stage bosses.

Sharing in effect:
- **OBP3** is shared by *three* things: Sara's projectiles, crows, and
  (because 0x70-0x7F is documented as "special/catfish→pal3" in older
  YAML notes vs pal7 in code) at minimum Sara-shots + crows.
- **OBP6** is shared by humanoid + soldier + moth + mage **and** every
  odd-numbered boss (Gargoyle, Crimson, Void, Knight) via the FFBF
  override.
- **OBP7** is shared by catfish **and** every even boss (Spider, Ice,
  Poison, Angela).
- During *any* boss fight, the FFBF override forces ALL tile>=0x30
  sprites onto the single boss slot — so on-screen monsters lose their
  own colors entirely.

Net: there are ~7 distinct monster types but only 5 monster-ish slots,
and 2 of those 5 are time-shared with bosses, and 1 with projectiles.

---

## (4) Can we MAXIMIZE per-monster palettes? Feasibility + scheme

### Concurrency reality (how many sprite TYPES co-exist)
- CGB hardware has exactly **8 OBJ palettes** — a hard ceiling.
- Enemy entity slots: section descriptor loads **5 entity slots** at
  DC85+ per section (game_memory_map.md:193 "all 5 entity slots at
  DC85+"); mini-bosses occupy slots too. ENTITY_DATA_STRUCTURE.md sees
  "8-10 entities max" in the 0xC200 region but those map to a small
  number of *distinct types* on screen at once (a wave is usually 1-2
  enemy types + Sara + projectiles).
- So at any instant the live set is roughly: **Sara (1), Sara
  projectiles (1), enemy projectiles (1), + 1-3 enemy types**. That fits
  in 8 with headroom — the constraint is *total distinct types across
  the game*, not concurrency.

### Why "each monster its own palette" is FEASIBLE but bounded
- 8 slots, of which 2 are permanently Sara (OBP1/2) and ~1.5 are
  projectiles (OBP0 + half of OBP3). That leaves **~4-5 slots** for
  monsters at any time.
- The game has more than 5 monster *types* total, but they don't all
  co-exist. The tile-range scheme already gives each *tile band* its own
  slot. The real losses are: (a) humanoid sub-types share OBP6; (b)
  bosses steal OBP6/OBP7 from monsters; (c) crow shares OBP3 with
  projectiles; (d) only the first 10 OAM entries/buffer are scanned.

Conclusion: **partial / feasible** — we can give *more* monster types
distinct palettes, and can stop bosses from clobbering live monsters,
but a true 1:1 "every monster type its own dedicated CGB slot" is
impossible globally (only 8 slots). The right framing is *per-scene
maximization* using the per-arena infrastructure that already exists
for BG.

### Proposed concrete scheme

**A. Reclaim OBP3 for crows only; move Sara projectiles fully onto OBP0.**
Today OBP0 already carries Sara projectiles dynamically. Change the tile
colorizer so tile 0x00-0x01 → OBP0 (not OBP3). Then OBP3 becomes a
*pure monster* slot (crow / flying).
- Code: in `create_tile_based_colorizer` (bg_experiment.py:142), the
  `low_tiles` branch `CP 0x02; JR C, pal_3` → change target to `pal_0`
  (emit `AF` / select 0). Net cost: 0 bytes, retargets one JR.
- Frees one monster slot from projectile sharing.

**B. Stop bosses from clobbering live monster slots — give bosses their
own dedicated slot.**
Today boss_slot_table = `[6,7,6,7,...]`, so bosses overwrite OBP6/OBP7
(humanoid/catfish). Re-point all bosses to **one dedicated boss slot,
OBP5 is still monster-used; use OBP0's enemy-projectile? no.** The clean
move: since only ONE boss is on screen at a time and Sara owns 1/2,
projectiles own 0, repurpose the FFBF override to write boss colors into
a slot that monsters of the same scene don't use. Simplest robust
change: set `boss_slot_table` to all-`7` and make the inner colorizer's
boss override only fire for the boss's *own* tiles (see C) so OBP6 stays
free for humanoids during boss fights.
- Code: `load_palettes_from_yaml` builds boss_slot_table from YAML
  `slot:` fields (bg_experiment.py:85). Edit YAML `boss_palettes[*].slot`
  to a single agreed slot, or add a new dedicated slot.

**C. Make the boss override tile-scoped instead of "all tile>=0x30".**
Today (obj_colorizer.md:112): boss active → *every* tile>=0x30 gets the
boss palette. This is why on-screen monsters lose color during fights.
Replace the blanket override with a check for the boss's tile band only
(bosses use a known high tile range per arena — probe to confirm, then
gate the override to e.g. tile>=0x70 or a per-boss min-tile constant).
- Code: in `create_tile_based_colorizer` the `boss_palette` path is
  reached from `LD A,E; OR A; JR NZ, boss_palette` right after the
  `CP 0x30; JR C, low_tiles` gate (bg_experiment.py:128-130). Insert an
  extra `CP <boss_min>; JR C, normal_dispatch` before taking the boss
  branch. Costs ~4 bytes; everything downstream is forward-jump
  relative so it re-resolves automatically.

**D. Split humanoid sub-types (soldier / moth / mage) across slots.**
They currently all map to tile 0x60-0x6F → OBP6. If their tile IDs are
separable (probe needed: do soldier/moth/mage occupy distinct sub-bands
within 0x60-0x6F or distinct bands like 0x60-0x67 vs 0x68-0x6F?), add a
sub-range split: 0x60-0x67 → OBP6, 0x68-0x6F → a freed slot (e.g. the
OBP3 freed in A, or OBP0 when no projectiles). Add one `CP 0x68; JR C`
in the `pal_6` region.

**E. (Bigger, optional) Per-scene OBJ palette banks — mirror the BG
per-arena system.** The teleport build already swaps **BG** palettes per
arena via `ARENA_TILE_PAL` + scene_detect (build_v301_teleport.py:140,
165). Add a parallel `ARENA_OBJ_PAL` table indexed by scene/FFBA so each
stage's monster roster gets a tailored 8-slot OBJ set loaded by
`palette_loader`. This converts the global 8-slot limit into a
*per-scene* 8-slot budget, which is how you "maximize per monster" in
practice. Cost: one extra 8×8-byte table per scene in bank 13 + a
select-by-scene branch in the palette loader (analogous to the existing
boss-slot branch).

**F. Raise the OAM scan cap from 10 to (at least) the real max.**
build_v301_gdma.py:450 forces `LD B,0x0A`. Monsters in OAM slots 10-39
are never recolored. Raise to a value that covers actual concurrent
sprites (e.g. 20-24) — but this directly increases VBlank cost
(~80-100T per entry per buffer, ×2 buffers). Must be validated against
the v3.01 VBlank budget (docs/v301_performance.md: ~76% of frame
already used). This is the single change with real timing risk.

### Recommended minimal first step (low risk, high payoff)
Do **A + C + B** together: reclaim OBP3 as a monster slot, scope the
boss override to boss tiles only, and give bosses a non-monster slot.
That alone stops the two biggest "monsters lose their color" failure
modes (projectile sharing + boss clobber) with ~8 bytes of code change
and a YAML edit, no timing risk (no extra OAM scanning). E and F are the
"true maximization" follow-ups and carry the per-scene-table and
VBlank-budget work respectively.

---

## Exact change sites (file:line)
- Tile→palette branches: `scripts/bg_experiment.py:121-160`
  (`create_tile_based_colorizer`).
- Boss override gate: `scripts/bg_experiment.py:128-151`.
- OAM scan count override: `scripts/build_v301_gdma.py:450`
  (`colorizer[1] = 0x0A`).
- OBP color data & order: `scripts/bg_experiment.py:58-74` (obj_key_map)
  + `palettes/penta_palettes_v097.yaml` `obj_palettes`.
- boss_slot_table source: `scripts/bg_experiment.py:82-87` +
  YAML `boss_palettes[*].slot`.
- Per-scene OBJ table hook point: mirror BG path in
  `scripts/build_v301_teleport.py:140-230` (`ARENA_TILE_PAL`,
  `build_scene_detect`).
- Palette RAM loader (boss-slot OCPS math, where a per-scene OBJ select
  would slot in): `scripts/bg_experiment.py:232-249`.

## ROM addresses (bank 13)
- shadow_main: 0x69D0
- inner colorizer: 0x6A10 (loop-count byte at 0x6A11 = 0x0A shipped)
- boss_slot_table: 0x68C0 (8 bytes = 06 07 06 07 06 07 06 07)
- obj_data (OBP0-7 source): 0x6840 (64 bytes)
- boss_palette_table: 0x6880 (64 bytes)
- palette_loader: 0x6900
- cond_pal wrapper: 0x6C90
- BG tile→pal LUT (for contrast; BG only): 0x7000

## Probes needed (to firm up the scheme)
1. Confirm shipped OAM scan count behavior (B=10) vs intended — is the
   gameplay sprite set actually within the first 10 OAM slots, or are
   monsters silently uncolored? (mGBA OAM dump during a multi-enemy
   wave.)
2. Map actual on-screen tile IDs per monster type (crow/hornet/orc/
   humanoid sub-types/catfish) to confirm the tile-band table and find
   sub-bands for humanoid split (D).
3. Map each boss's sprite tile range to scope the boss override (C).
4. Measure VBlank headroom before raising the OAM cap (F).
