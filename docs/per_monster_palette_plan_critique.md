# Architectural Critique: `per_monster_palette_plan.md`

**Scope**: Alignment of the per-monster-type palette plan with the existing O(1)
Shadow-OAM intercept system (commit `b5e8a0a`, `scripts/patch_oam_intercept.py`,
designed in `docs/o1_oam_intercept_plan.md`).

**Reviewed against**: `docs/o1_oam_intercept_plan.md`,
`docs/VBLANK_HOOK_LIMITATIONS.md`, `palettes/penta_palettes_v097.yaml`,
`palettes/bg_tile_categories.yaml` (obj_colorizer section),
`scripts/build_v301_teleport.py`, `scripts/build_v301_gdma.py`,
`scripts/patch_oam_intercept.py`, `scripts/bg_experiment.py` (colorizer/cascade
codegen). Claims below marked *verified* were checked against the working tree
on 2026-07-15.

---

## Verdict (executive summary)

The plan's **destination is architecturally correct** and its **route is not**.
The core insight — collapse the monster-type indirection at build time into the
existing flat `tile_id → palette` LUT — is exactly how the O(1) intercept is
already shaped, and per-monster colors then become a *pure data change* with
zero runtime cost. But the plan then contradicts its own insight by proposing a
runtime override-table chain, new bank-13 tables at addresses that are already
occupied, a trampoline address that violates the intercept's WRAM-residency
invariant, and a WRAM ring buffer that lands inside the intercept's own LUT
copy. It also never mentions the two systems it must coexist with: the
still-active VBlank cascade colorizer (dual-writer hazard) and the
`FFBF`/boss-CRAM-swap machinery. Finally, its tile-range data contradicts the
verified mappings in `penta_palettes_v097.yaml` in at least five places.

**Recommended shape**: keep Phase 1 (YAML) and Phase 5 (verification), replace
Phases 2–4 with a build-time overlay onto the existing 256-byte fused LUT, and
gate the whole effort behind repairing the currently-broken intercept build.

---

## Part 0 — Ground-truth corrections (factual errors in the plan)

These must be fixed before any phase begins, because several phases target
things that don't exist or are already occupied.

1. **`build_obj_pal_table()` is not in `build_v301_gdma.py`** (plan Phase 2).
   It is imported by `patch_oam_intercept.py` *from `build_v301_teleport.py`*
   — and it no longer exists there either. *Verified*:
   `import patch_oam_intercept` fails today with
   `ImportError: cannot import name 'build_obj_pal_table' from
   'build_v301_teleport'`. The committed O(1) intercept build is **bit-rotted
   at HEAD**: the teleport builder evolved past it (the `OBJ_STAMPER_ADDR`,
   `OBJ_PAL_TABLE_ADDR`, and `build_obj_pal_table` symbols were removed). The
   plan proposes extending a system whose build script cannot currently run.

2. **The trampoline is not "at bank0:$10D3" and cannot be "at bank13:0x6DB0".**
   The implemented hooks are `CALL`s at **0x10E4** (central emitter, at the
   attr write), **0x3487** (free-slot emitter), and **bank1:0x5221** — and the
   trampolines execute from **WRAM 0xDB80/0xDBB0/0xDBE0** (copied at cold-boot
   from bank13:0x6A70). WRAM residency is a hard invariant, not a convenience:
   at sprite-emission time the game's main loop has an arbitrary switchable
   bank mapped, so bank-13 code/tables are unreachable without a per-sprite
   bank switch, which `o1_oam_intercept_plan.md` explicitly rejects as erasing
   the savings. Any new table the trampolines read must be WRAM-resident and
   cold-boot-copied, like the existing LUT (ROM bank13:0x6B00 → **WRAM
   0xD900**, read via hardcoded `LD H, $D9`).

3. **Every proposed address collides with existing allocations** (*verified*
   against the bank-13 layout in both builders):
   - `monster_pal_table` at bank13:**0x6C00** (256 B → 0x6CFF) overlaps
     `cond_pal` (0x6C90) and `bg_sweep` (0x6CD0).
   - Override table at bank13:**0x6D00** (256 B → 0x6DFF) overlaps the
     `bg_sweep` tail and **0x6D80**, which the teleport build reuses for the
     live RLE posmap expander (`EXPAND_ADDR`).
   - Trampoline at bank13:**0x6DB0** — same occupied region, plus violates
     point 2.
   - Ring buffer at WRAM **0xD940** sits **inside the intercept's own WRAM LUT
     copy (0xD900–0xD9FF)**. Extending the system would corrupt the system.

4. **The fused LUT is 256 bytes, not 512.** `tile_id` is 8 bits; fusing
   tile→type→palette into tile→palette changes the table's *values*, not its
   size. The existing `build_obj_pal_table()` output was already exactly this
   256-byte fused table.

5. **The cycle model is borrowed from the wrong subsystem.** The intercept's
   cost is paid **per sprite emission in the main loop** (~80–130 T per
   emitted sprite per the o1 plan's audit), not per frame in VBlank. The
   plan's "~375 cycles for all 40 sprites", "1200 cycles total", and "53K
   VBlank budget" figures mix the dead GDMA-path numbers (CLAUDE.md: that 53K
   figure describes dead code) with a per-frame model that doesn't apply.
   The arithmetic errors don't change the conclusion (costs are affordable),
   but plans that reason from wrong budgets tend to make wrong trade-offs —
   as the override-table proposal does (see §3).

6. **Self-superseded design text.** The plan spends its first half on
   entity-table correlation (0xC200 structs, an OAM-slot ring buffer,
   Approach A vs B), then pivots mid-document to "actually, the entity type is
   inferrable from the tile ID" — which is correct, and which makes
   everything before it dead weight. The Approach A/B sections should be
   deleted (or moved to an appendix labeled "rejected: only needed if two
   monster types ever share a tile range"), so no implementer builds the ring
   buffer that the plan itself abandoned.

---

## Part I — Architectural soundness

### 1. Does the extension slot into the O(1) stamper trampoline naturally?

**The end-state does; the proposed mechanism doesn't.** Impedance mismatches:

- **Residency mismatch** (fatal as written): the plan puts the new tables and
  the modified trampoline in bank 13 (§Part 0.2–0.3). The intercept's entire
  design is that emission-time code touches only always-mapped memory. Phase 4
  ("update the cold-boot copy") half-acknowledges this, but Phase 3's
  described lookup chain (`check override[0x6D00]… else LUT[0x6B00]`) reads
  ROM addresses. In the real system both reads must be WRAM pages.
- **One trampoline vs three**: the plan describes modifying "the trampoline".
  There are three (sites 0x10E4, 0x3487, bank1:0x5221), each with its own
  displaced-instruction tail and its own register liveness contract, laid out
  in fixed 48-byte WRAM slots. Any runtime lookup change is a ×3 change and a
  slot-layout re-audit. A build-time data change is a ×0 change.
- **Register-budget mismatch**: the implemented trampolines are already
  thinner than the o1 plan's conservative contract (they clobber B/C without
  saving and return A = merged attr instead of the original). Extensions
  cannot assume free registers; each site needs a fresh liveness audit. This
  is the real cost of the override check, not the cycles (§3).
- **Dual-writer blindspot**: the plan never mentions that the VBlank cascade
  colorizer (`shadow_main` → `create_tile_based_colorizer` at bank13:0x6A10,
  OAM cap = 10) is still CALLed from the colorize handler every VBlank in the
  intercept build (only the O(40) *stamper* CALL was removed). Slots 0–9 get
  rewritten by the cascade after emission, so any tile whose per-monster LUT
  value differs from the cascade's range value will display cascade colors in
  slots 0–9 and LUT colors in slots 10–39 — and *change color when its OAM
  slot changes*. This codebase has hit the two-writers-disagree alternation
  bug twice already (bg_sweep vs inline hook; posmap vs tile hook). Per-monster
  values guarantee disagreement, because differentiating within a range is the
  whole point. The plan must decide the cascade's fate (recommendation in §6).

### 2. Fused 256-byte LUT vs two-table (tile→type, type→palette)

**Fused, unambiguously — and it is not a new design, it is the current one.**
`build_obj_pal_table()` already emits the fused table; the plan's "Optimized
Implementation" section independently reinvents the existing architecture.
The two-table runtime chain buys nothing:

- The stated benefit — "new monsters added → just add an entry to the yaml,
  no code changes" — is a property of *both* designs. YAML edits are
  build-time edits either way; the type→palette indirection is naturally a
  Python/codegen concept, not a runtime one.
- The runtime costs are real and triplicated: a second WRAM page (unallocated,
  unaudited), a second dereference in all three trampolines, growth against
  48-byte slots, and a second 256-byte cold-boot copy in the first-VBlank
  window that CLAUDE.md documents as fragile (the WRAM-bank-2 zeroing that
  pushed `palette_loader` CRAM writes into mode 3 and whitened Sara was
  removed for exactly this reason).
- The only future justification for runtime type indirection would be two
  monster types **sharing** a tile range while needing different palettes.
  Per `penta_palettes_v097.yaml`, tile ranges are type-unique. YAGNI.

One correction to the plan's framing: the LUT codegen belongs in the
**teleport/intercept layer** (where `build_obj_pal_table` lived), not
`build_v301_gdma.py` — the GDMA builder's OBJ path is the cascade, and its
0x6B00 slot holds `create_tile_to_palette_subroutine()` (code) until the
intercept patch overwrites it with the table.

### 6. Plan's tile-range mapping vs the existing cascade (split at 0x30, CP ranges)

They **conflict by construction** while both writers run. The cascade is a
coarse range function (≥0x30: `<0x40→3, <0x50→4, <0x60→5, <0x70→6, <0x80→7`,
default 4; <0x30: Sara/projectile/effects routes); the LUT is a per-tile
tabulation. Today they can be kept equivalent; with per-monster values they
*intentionally diverge*, and the cascade cannot express the divergence (a
CP-cascade for scattered per-tile assignments blows past its byte budget — and
`VBLANK_HOOK_LIMITATIONS.md` documents that in-loop table lookups crash in the
VBlank hook context, which is precisely why per-monster color was impossible
before the intercept existed).

Also note: the o1 plan's own LUT spec disagrees with the shipped cascade for
0x40–0x7F (it shifts every bucket down one: `$30-$4F→3, $50-$5F→4, …` vs the
cascade's `0x40-0x4F→4, 0x50-0x5F→5, …`). One more datapoint that tables
transcribed by hand drift; the fix is single-sourcing, not care.

**Composition recommendation**: one source of truth, one writer.
- Extend the *existing canonical* `bg_tile_categories.yaml → obj_colorizer`
  section with a per-monster `overrides:` block — do **not** create a second
  YAML (`monster_palette_map.yaml`) whose ranges overlap the first. Two
  palette YAMLs with overlapping tile domains is how the orc/hornet swap in
  the plan happened (§5-data below).
- Generate the fused LUT from `obj_colorizer` ranges + overlay, and extend the
  existing regression guard (`verify_yaml_drives_obj_colorizer.py`) to assert
  `LUT[t] == cascade(t)` for every tile *not* in an override, and
  `LUT[t] == override(t)` for every tile that is.
- In the intercept build, decommission the cascade as an attr writer (see §5
  for what replaces its boss duty). Until that's done, per-monster values will
  visibly fight it in slots 0–9.

### 7. Phase ordering: before or after the O(1) trampoline work?

**After — with a repair step in front.** Concretely:

1. **Repair the intercept build** (it fails at import today — §Part 0.1).
   Re-home `build_obj_pal_table` + the `OBJ_*` constants (either restore them
   to `build_v301_teleport.py` or, better, move them into
   `patch_oam_intercept.py`, which is their only consumer). Add a trivial
   import smoke-test so builder refactors can't silently orphan the patch
   script again.
2. **Land and verify the intercept alone**, with today's LUT values (which
   should be probe-verified equivalent to the cascade). This isolates the
   *timing* risk — the intercept moves OAM palette writes from VBlank to
   emission time, touching the exact dimension (OAM/DMA ordering,
   `docs/audit/obj_enemy_color_race.md`, hwoam floor-through) that CLAUDE.md
   gates behind mGBA-pixel + MiSTer verification.
3. **Resolve the dual-writer question** (cascade off / boss-only — §6, §5).
4. **Then flip the LUT data to per-monster.** At that point it is a
   YAML-plus-codegen change with zero new code in the hot path, trivially
   bisectable, and each monster's color is visually verifiable against a
   stable baseline.

Doing per-monster *first* would mean building it on the cascade — which the
VBlank crash constraints make impossible — or landing both the riskiest timing
change and the color remap in one step, un-bisectable when the golden check
shows flicker.

---

## Part II — Specific technical concerns

### 3. Is the override-table "+12 cycles" realistic?

**No, though the honest number is still small.** Problems with the claim:

- The quoted sequence (`LD A,[HL]; INC A; JR Z; DEC A`) assumes HL already
  points into the override table for free. At the actual interception points
  it doesn't: S1 enters with A = transformed attr, DE = entry+3, and the tile
  must be re-fetched from `[DE-1]`; the trampoline then builds `L=tile,
  H=$D9`. An override-first probe needs the second page's H load and, on
  fallthrough, a reload of H for the base LUT. Realistic marginal cost on the
  fallthrough path: **~32–36 T-cycles per emitted sprite** (≈8–9 M-cycles) —
  roughly 3× the claim in M-cycles, 25× off if "cycles" meant T. In absolute
  terms (~12–25 emissions/frame → ~0.4–0.9K T/frame of main-loop time) it is
  indeed negligible, so the claim's *conclusion* survives its *arithmetic*.
- The claim "existing trampoline paths unchanged" is false: all three
  trampolines get rewritten, each grows ~8–12 bytes against a 48-byte slot
  budget (S1 is already ~35 bytes; the Sara branch makes these tight), and the
  WRAM slot layout (0xDB80/0xDBB0/0xDBE0) likely needs respacing — note S3
  already ends around 0xDC0A, i.e. the current layout is *already* brushing
  against unaudited 0xDC00-page WRAM, worth flagging independently.
- The comparison that matters: the fused build-time design costs **zero**
  cycles, zero bytes, zero new WRAM, zero cold-boot copy time. A runtime
  mechanism whose only benefit is available at build time shouldn't spend any
  of those budgets.

### 4. Sara's dynamic palette: runtime FFBE vs the cascade's reg_d route

**The plan's "resolved at runtime from FFBE" is already implemented — as the
`0xFF` sentinel in the intercept trampolines.** All three trampolines do:
`CP $FF → LDH A,[FFBE]; OR A; → pal 2 if zero (Sara W) else pal 1 (Sara D)`.
*Verified*: this is byte-identical in mapping to `shadow_main`'s reg_d
computation (`F0 BE B7 20 04 16 02 18 02 16 01` → D=2 if FFBE==0 else D=1), so
the two mechanisms agree; the cascade's D is merely sampled once per VBlank
while the trampolines sample FFBE per emission (a benign ≤1-frame skew during
form transforms, and only while the cascade still runs at all).

Consequences for the plan:

- The YAML's `palette: sara_palette` entries should compile to **0xFF** in the
  LUT — reuse the existing sentinel, don't invent a parallel mechanism.
- The plan's **static W/D tile split must be dropped**. It splits 0x10–0x1F
  into sara_w (0x10–0x17) and sara_d (0x18–0x1F), but the shipped systems
  route all of 0x10–0x1F dynamically (iter 31: "Sara secondary body"), the
  sub-split is unverified, and — decisive — **0x10–0x1F is the documented,
  unsolved hwoam_recolor floor-through range** that CLAUDE.md hard-gates
  (B=20/iter-277 revert). If tiles already encoded the form, the sentinel
  would never have been needed; it exists because they don't. Leave every
  Sara tile at 0xFF and leave 0x10–0x1F alone in phase 1.
- The trampolines *cannot* use the reg_d route: D is live emitter state at the
  hook sites (at the free-slot emitter D **is** the tile ID). Per-sprite FFBE
  reads are the correct trampoline-side mechanism and are safe in main-loop
  context — the `VBLANK_HOOK_LIMITATIONS.md` crash list (no PUSH/POP, no
  memory reads) applies to the old 0x0824 VBlank loop, not here.

### 5. Boss override (FFBF) interaction

**The plan is silent on FFBF, and the intercept currently has a boss hole it
would inherit and widen.** Ground truth:

- Boss coloring is two coupled mechanisms: (a) *attr override* — the cascade's
  high phase forces **every** tile ≥0x30 to `boss_slot_table[FFBF-1]` (E
  route) when FFBF≠0; (b) *CRAM swap* — `cond_pal`/`palette_loader` load the
  boss's colors into slot 6 or 7 while FFBF≠0.
- The trampolines implement **no FFBF logic**. So in the intercept build
  today, slots 0–9 (cascade) go boss-colored during minibosses while slots
  10–39 (trampoline) stay tile-colored — already inconsistent.
- Stage bosses are drawn on the **BG layer** (per the arena-table docs), so
  this is in practice a *miniboss* question (Gargoyle FFBF=1 → slot 6, Spider
  FFBF=2 → slot 7), where regular enemies and projectiles share the screen.

**Which should win?** The boss override should win **for the boss's own
tiles** (the CRAM swap assumes the boss's sprites point at the swapped slot);
per-type should win for everything else on screen — which is a genuine
*improvement* over today's "every enemy turns boss-colored" behavior. Two
additional constraints the plan must absorb:

- Any monster statically assigned pal 6 or 7 will change color whenever a
  miniboss's CRAM swap is active. The plan assigns crow→6 and soldier→7,
  silently re-coupling colors it set out to decouple. Either keep per-type
  assignments out of slots 6/7, or accept and document the coupling.
- The plan's `gargoyle_miniboss: palette: 7` contradicts `boss_slot_table`
  (Gargoyle = slot **6**); as written the Gargoyle would point at Spider's
  slot.

**Mechanism recommendation**: don't put an FFBF branch in the trampolines.
Reuse the proven scene_detect pattern — *patch the WRAM LUT on state change*:
when FFBF transitions, overwrite the WRAM 0xD900 entries for the active boss's
tile range with the boss slot, and restore them on exit. Once-per-transition
cost, trampolines stay byte-identical, and the "who wins" policy becomes an
explicit, testable table edit instead of implicit branch ordering.

### 8. The 0xFF sentinel + fallthrough vs the existing merge logic

**Compatible only under build-time guarantees the plan doesn't state — and the
fused design deletes the entire failure class.**

- **Sentinel collision**: 0xFF already means "dynamic Sara" in the base LUT;
  the plan overloads 0xFF to mean "no override" in the adjacent table. Two
  meanings, same value, same page-alignment idiom, three trampolines that must
  each check the right one first. This is a maintenance trap even when
  implemented correctly.
- **The merge does not sanitize**: the trampolines compute
  `(attr AND $F8) OR C` with **no `AND $07` on the palette value**. Any
  non-{0–7, 0xFF} byte that reaches the merge sets OBJ attr bits 3–7 —
  VRAM-bank select and X/Y-flip — producing flipped/garbage sprites, not just
  a wrong hue. And a 0xFF that slips past a missing `INC A` check in one of
  three trampolines becomes `OR 7` → pal 7. The BG side already shipped
  exactly this bug class (bg_table[0xFF] → pal-7 splotch, fixed in v3.01 by
  zeroing the sentinel).
- **Regression risk for unmapped monsters**: in the two-table design, safety
  for unmapped tiles depends on runtime fallthrough working in all three
  trampolines forever. In the fused design, safety is by construction: codegen
  starts from the current range map, overlays the per-monster entries, asserts
  every non-Sara value ≤ 7 and Sara tiles exactly 0xFF, and unmapped tiles are
  **byte-identical to today's ROM** — diffable in the build output before an
  emulator is ever launched.

### Data errors in the proposed `monster_palette_map.yaml` (blocking Phase 1)

Cross-checked against the *verified* mappings in `penta_palettes_v097.yaml`:

| Plan entry | Plan says | Verified reality | Consequence if shipped |
|---|---|---|---|
| orc | tiles 0x40–0x49 | 0x40–0x4F = **hornets** (pal 4); orc/ground = 0x50–0x5F (pal 5) | Hornets turn "orc blue" |
| hornet | tiles 0x50–0x57, "keep as-is" pal 4 | 0x50–0x5F = **orc** (pal 5) | Orcs turn hornet-colored; "keep as-is" is based on the wrong baseline |
| soldier | tiles 0x70–0x75, pal 7 "red" | soldier/humanoid = 0x60–0x6F (pal 6); 0x70–0x7F = catfish; pal 7 = **cyan**/Spider-boss slot | Wrong tiles, wrong slot, boss-CRAM coupling |
| crow | pal 6 "purple" | pal 6 is the **Gargoyle CRAM-swap slot** | Crows recolor during every Gargoyle fight |
| gargoyle_miniboss | pal 7 "red (boss slot)" | Gargoyle's boss slot is **6** | Gargoyle points at Spider's slot |
| projectile_sara | pal 3 "yellow" | pal 3 is **red** (and shared CRAM with crows today) | Comment/intent mismatch |
| projectile_enemy | tile 0x0F → pal 1 "red" | enemy projectiles = pal **0** (blue); pal 1 = **Sara D green**, dynamically swapped to Jet-cyan in bonus stages | Enemy shots render in Sara's palette and track her form swaps |
| sara_w / sara_d | static split of 0x10–0x1F by form | 0x10–0x1F routed dynamically as a block (iter 31); also the hwoam floor-through hard-gate range | Half of Sara's secondary body in the wrong form palette; touches a gated known issue |

Nearly every color comment in the plan matches the *old three-color VBlank
era* (`VBLANK_HOOK_LIMITATIONS.md`: "palette 7 orange boss") rather than the
v097 palette set. Phase 1 must start from v097 + the obj_colorizer YAML, and
the builder should validate the overlay against the palette YAML (names and
slots), not trust comments.

---

## Recommended revision of the plan

1. **Phase 0 (new)**: repair `patch_oam_intercept.py` bit-rot (re-home
   `build_obj_pal_table` + `OBJ_*` constants; add an import smoke-test). Land
   and verify the vanilla-LUT intercept per CLAUDE.md gates (5 probes +
   `verify_sprite_flicker.py` + mGBA golden check + cold-boot CRAM probe,
   MiSTer while it's online).
2. **Phase 1**: per-monster data as an `overrides:` extension of the existing
   canonical `bg_tile_categories.yaml → obj_colorizer` section (single source
   of truth; no second YAML). Correct the tile ranges against v097. Exclude
   0x10–0x1F and slots 6/7 from the first cut.
3. **Phase 2**: overlay the overrides onto the fused 256-byte LUT in
   `build_obj_pal_table()` at build time. No override table, no new addresses,
   no trampoline changes. Codegen asserts: values ∈ {0..7}, Sara tiles = 0xFF,
   non-override tiles byte-identical to the base table.
4. **Phase 3**: decommission the cascade as an attr writer in the intercept
   build; move miniboss handling to FFBF-triggered WRAM-LUT patching
   (scene_detect pattern). Extend `verify_yaml_drives_obj_colorizer.py` to
   guard the LUT.
5. **Phase 4**: verification per CLAUDE.md, plus one new probe: per-monster
   palette assertion on a gameplay state containing ≥2 differentiated monster
   types, run against hardware OAM through mGBA (never PyBoy-only, per the
   hard gate).

The plan's instinct — that the O(1) intercept finally makes per-monster color
*possible* after the VBlank-hook era proved it impossible — is right, and the
feature is worth building. It just needs to be built as data on top of the
system that exists, not as new machinery beside it.
