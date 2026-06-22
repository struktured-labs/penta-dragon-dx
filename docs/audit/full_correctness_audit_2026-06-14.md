# Full Correctness Audit + Cleanup — 2026-06-14

Static analysis only (no emulator). ROM bytes read from the two freshly-built
artifacts and the build scripts. Repo: `penta-dragon-dx-claude`, branch
`wip-arena-position-sweep`.

## 0. Build verification (both clean)

```
python3 scripts/build_v301_gdma.py      -> EXIT 0, wrote rom/working/penta_dragon_dx_v301.gb (262144 bytes)
python3 scripts/build_v301_teleport.py  -> EXIT 0, wrote rom/working/penta_dragon_dx_teleport.gb (262144 bytes)
```

No errors, no warnings, no failed asserts. The teleport build internally calls
`build_v301()` first (so it produces v301.gb as a side effect), then layers the
arena/teleport machinery on top and writes the separate teleport.gb.

`build_v301_gdma.py` reported:
- GDMA transfer: 46 bytes at 0x6D80
- attr computation: 57 bytes at 0x7100
- colorize handler: 128 bytes at 0x6E00
- inline tile copy: 117 bytes (82 free in the 199-byte 0x42A7 slot)

`build_v301_teleport.py` additionally reported the 9 arena bg_tables, scene-detect,
bg_sweep repoint to WRAM 0xDA00, the posmap RLE blob, RLE expander, position sweep,
the restored inline hook, teleport routine, and the safe-switching VBlank hook.

---

## 1. Dead code: position sweep + RLE posmaps + expander (CONFIRMED DEAD)

The "holy grail" position-sweep system is **built into the teleport ROM but never
reached by any control-flow path.** Verified by byte-level reference search over the
entire `penta_dragon_dx_teleport.gb`.

### Evidence

The colorize handler at bank13:0x6E00 (in BOTH ROMs) makes exactly these CALLs:

| offset | target | meaning |
|--------|--------|---------|
| +39    | 0x6C90 | cond_pal (palette loader, cached) |
| +115   | 0x6CD0 | **bg_sweep** (tile-ID sweep) — NOT 0x7100 |
| +118   | 0x69D0 | shadow_main (OBJ colorizer) |
| +121   | 0xFF80 | OAM DMA |

The colorize handler's `CALL bg_sweep` targets **0x6CD0**, not the position sweep at
0x7100. The build does this deliberately: `scripts/build_v301_teleport.py:539-541`
the "repoint colorize -> position sweep" step is commented `[DISABLED: Using standard
tile-ID bg_sweep directly for clean background/claws separation]` and just sets
`patched_sweep = True` without emitting the repoint.

Whole-ROM reference search (`0xC3`/`0xCD` + little-endian target):
- **refs to 0x7100 (position sweep entry): `[]`  → ZERO callers.**
- refs to 0x6D80 (RLE expander): exactly one, at file 0x37138 = bank13 logical 0x7138,
  which is **inside the position sweep body itself** (the possweep's `CALL expander`).
  Since possweep is unreachable, the expander is transitively dead too.
- refs to 0x6FB0 (scene_detect): one, at bank13 logical 0x6E80 = the teleport routine.
  scene_detect IS live (teleport routine runs every VBlank and calls it).

Confirming the bytes are physically present (so this is genuine dead weight, not
absent):
- TP 0x7100 = `fa 80 d8 d6 0c 38 06 fe 09 ...` (possweep: LD A,[D880]; SUB 0x0C; ...).
- TP 0x6D80 = `3e 02 e0 70 11 00 d0 2a 4f 2a 12 13 0d 20 ...` (expander).
- TP 0x7B00 = `05 00 0a 04 16 00 0a 04 ...` (posmap RLE: count,value pairs).
- TP 0x7FE0 = `00 7b 42 7b b8 7b 2e 7c 68 7c b2 7c e0 7c 30 7d b4 7d` (9 LE pointers).

### Why per-arena color still works without the position sweep

In the teleport build the inline hook at 0x42A7 is the **full tile+attr copy**
(byte-for-byte identical to the base build — verified `base[0x42A7:0x436E] ==
tp[0x42A7:0x436E]` is True, and it begins `2e 00` = `LD L,0`, i.e. NO arena
neutralize dispatch). The hook's attr phase does the fused `[BC]` lookup against
WRAM 0xDA00. `scene_detect` (0x6FB0, live) keeps 0xDA00 pointed at the correct
per-arena 256-byte table, and `bg_sweep` was repointed to also read 0xDA00 (build
line 481-487). So both attr writers agree on the same per-arena table → per-arena
coloring with no need for the posmap path. `arena_neutralize_d880=None` at build
line 546 is therefore correct and consistent: the tile-only arena path is also
unused.

### Wasted ROM bytes

| component | bytes | bank13 addr | underlying slot |
|-----------|------:|-------------|-----------------|
| position sweep code | 159 | 0x7100 | reuses dead attr_comp slot |
| RLE expander        |  30 | 0x6D80 | reuses dead GDMA slot |
| posmap RLE data     | 754 | 0x7B00–0x7DF2 | previously-unused ROM |
| posmap pointer table|  18 | 0x7FE0 | previously-unused ROM |
| **TOTAL**           | **961** (0.94 KiB) | | |

Nuance: possweep@0x7100 and expander@0x6D80 sit on top of slots that are ALREADY
dead in v3.01's warm path (attr_comp and GDMA — see §3). So removing them frees no
*incremental* live space; only the posmap RLE blob (754 B) + pointer table (18 B) =
**772 B** is space the dead system uniquely consumes. Bank 13 still has headroom
(494 B free gap between RLE end 0x7DF2 and the ptr table at 0x7FE0), so this is not
crowding anything out today.

### Recommendation: KEEP-AS-FALLBACK (do not remove yet)

- The system is inert (zero callers) so it cannot misbehave — it costs only 772 B of
  otherwise-free ROM and adds zero runtime cost.
- MEMORY notes the position-sweep was the documented "HOLY GRAIL" path
  (`milestone-arena-position-all9`, mGBA-verified) and re-enabling it is a one-line
  flip (uncomment the repoint at build_v301_teleport.py:539-541 + set
  `arena_neutralize_d880` to the arena base). Deleting it loses that turnkey fallback.
- If ROM space ever becomes tight, the cheapest removal is the 772 B posmap data +
  pointer table; the 159 B possweep and 30 B expander would re-expose the dead
  attr_comp/GDMA bytes underneath (no net gain unless those are also removed).
- ACTION if kept: add a one-line comment at the top of the possweep write block and
  at build line 539 noting "DEAD as of teleport-v8.x: inline hook+0xDA00 path is the
  live arena colorizer; possweep retained as opt-in fallback."

---

## 2. Which ROM is the shippable "production"? — BASE (v301.gb)

**Production = `rom/working/penta_dragon_dx_v301.gb`** (the `build_v301_gdma.py`
output). MEMORY confirms: "Production (MiSTer-deployed): v3.01 (2026-05-23 onwards)".
The teleport ROM is a **developer/preview tool** (SELECT+START cycles bosses) and is
explicitly described in its own header as a dev fixture ("HOW TO PLAY ... Cycles
boss").

### Does the BASE build include scene_detect + the 9 arena tables? NO.

Verified by reading the base ROM bytes:
- BASE 0x7200 (would be the Shalamar arena table) = `d7 bf eb ff fb fe fd 79 ...` —
  this is **untouched original Penta Dragon ROM data**, not a 256-byte palette table
  and not zeros. The base build never writes there.
- BASE 0x6FB0 (would be scene_detect) = all `00` (untouched / zero).
- BASE colorize handler has NO `CALL scene_detect`; its VBlank wrapper at 0x6F10
  calls the colorize handler directly (no teleport routine in between).

By contrast TP 0x7200 = the Shalamar table (currently all-zero in the committed
`arena_tables_data.py` slot for Shalamar, but the build path writes it), and TP has
scene_detect at 0x6FB0 (`fa 80 d8 21 0d df be c8 ...` = LD A,[D880]; LD HL,DF0D;
CP [HL]; RET Z).

**Conclusion:** Per-arena boss colors are TELEPORT-BUILD-ONLY. The shipped production
ROM (v301.gb) colorizes the dungeon and bosses with the single static dungeon
`bg_table` (0x7000) + OBJ colorizer; it does NOT swap palettes per boss arena. The
9-arena per-boss color work lives only in the teleport preview ROM and has not been
promoted to production (consistent with MEMORY: "MiSTer + production-promotion
pending" for the arena work).

---

## 3. Other dead code in the BASE production ROM (attr_comp + GDMA)

The base build still *writes* two routines that nothing calls in the warm path:
- `attr computation` (57 B @ 0x7100) — `create_attr_computation`.
- `GDMA transfer` (46 B @ 0x6D80) — `create_gdma_transfer`.

The colorize handler does NOT call either (its only CALLs are cond_pal, bg_sweep,
shadow_main, OAM — see §1 table). MEMORY already flags this: "v3.01 'GDMA' is a
MISNOMER: GDMA+attr_comp are dead code (never CALLed, verified)." This audit
re-confirms it at the byte level for the current build. ~103 B of dead code, but it
occupies the slots the teleport build later overwrites with possweep/expander, so it
is harmless. KEEP-AS-IS unless doing a broader bank-13 cleanup; if removed, also
delete the now-misleading "GDMA" naming in `build_v301_gdma.py` (filename + log
strings) to avoid future confusion.

---

## 4. Fragile spot: teleport fire-path scratch overlapping bg_sweep buffer

### The overlap (confirmed at byte level)

`bg_sweep` (build_v296_phantomsafe.py:123,132,145) uses **0xDF10–0xDF2F** (32 bytes)
as its tile→palette→attr scratch, every VBlank, inside the FFC1 gate. It also uses
DF01 (base_hi) and DF04 (row counter).

The teleport routine (disassembled from TP 0x6E80) touches these DF bytes:

| addr | role | inside DF10-2F? |
|------|------|-----------------|
| DF0E | landing-pad-copied sentinel (cold boot) | no (safe) |
| DF0C | combo debounce | no (safe) |
| **DF1D** | re-fire sit-out counter (30) | **YES** |
| **DF1F** | colorize-skip counter (60) | **YES** |
| **DF20** | saved main-loop PC low | **YES** |
| **DF21** | saved main-loop PC high | **YES** |

So four teleport scratch bytes live INSIDE bg_sweep's 32-byte buffer. CLAUDE.md's
rule "keep custom WRAM scratch out of 0xDF10–0xDF2F" is violated here.

### Why it survives today (the gating that saves it)

Verified the control flow from the ROM bytes:
1. The VBlank wrapper (0x6F10) calls the **teleport routine** (0x6E80) FIRST, and the
   teleport routine ends with `JP colorize` (0x6E00) — but only on the non-fire/non-
   skip fall-through.
2. **On a FIRE frame**: the routine writes DF1D=30, DF1F=60, DF20/DF21 (saved PC),
   then does the stack redirect and **RETs directly** (the lone `C9` at 0x6EF6, right
   after `... db 77`). It does NOT fall through to `JP colorize`. So colorize — and
   therefore bg_sweep — does NOT run on the fire frame. The four overlapping bytes are
   written on a frame where the clobberer is absent.
3. **On the following ~60 frames**: the end path
   (`FA 1F DF; B7; 28 05; 3D; EA 1F DF; C9`) sees DF1F>0, decrements it, and **RETs
   (skips colorize)**. bg_sweep is gated OFF for the entire DF1F countdown, so it
   cannot clobber DF1D/DF1F while they are live. DF20/DF21 are consumed by the landing
   pad on the very first post-RETI frame, so their lifetime is a single frame anyway.
4. Once DF1F reaches 0, the routine resumes `JP colorize` and bg_sweep runs again,
   reusing 0xDF10–0xDF2F freely — by which point none of the four bytes matter.

So the design is **correct but load-bearing on an implicit invariant**: "bg_sweep
never runs while any of DF1D/DF1F/DF20/DF21 holds a live value." This invariant is
enforced by the fire-frame RET + the DF1F skip-gate.

### Risk assessment

- **Severity: low for the shipped product** — none of this exists in the production
  v301.gb (the entire teleport routine is teleport-build-only). The fragility is
  confined to the dev preview ROM.
- **Severity: medium for the teleport ROM itself.** The invariant is brittle:
  - If arena init + settle ever exceeds the hard-coded 60-frame DF1F window
    (`LD A,0x3C` at 0x6EBE), bg_sweep resumes mid-init. DF1D (sit-out) could still be
    counting (it starts at 30, < 60, so normally finishes first — OK) but any future
    change that lengthens DF1D past DF1F, or a boss whose arena settle is slower on
    real hardware, would let bg_sweep stomp DF1D mid-countdown. Effect would be a
    premature re-fire enable, not a crash.
  - The constants (60 / 30) are empirical ("arena init takes ~10 frames in PyBoy, 60
    is a safe margin") and untested on MiSTer for the slowest boss.
- **Recommendation (only matters if the teleport build is ever promoted/shared):**
  relocate the four bytes OUT of 0xDF10–0xDF2F to the known-safe sub-buffer region
  near DF0C–DF0E that the flicker fix already established (e.g. DF06–DF09 if free, or
  extend below DF0C). This removes the hidden invariant entirely and matches
  CLAUDE.md's rule. Cost: 4 single-byte address edits in `build_teleport_routine`.
  Low effort, eliminates the only structural fragility found.

### Note on stale comments (cosmetic, not a bug) — RESOLVED iter 178

`build_v301_teleport.py` docstring (lines 31-35) and the build_landing_pad/
build_teleport_routine comments referenced **DF1E** as the sentinel and **0xDB00** as
the landing pad, but the emitted code uses **DF0E** (verified: copy-sentinel read at
0x6E83 = `FA 0E DF`, write at 0x6E9A = `EA 0E DF`).

**Iter 178 (2026-06-22):** updated the stale docstring + inline comments to
DF0E. ROM rebuilds byte-identical (sha256 dff74a5f) — no functional change,
only documentation accuracy. The "landing pad / stub copy sentinel" semantic
also clarified: DF0E is shared across landing-pad, levelsel-stub, and STAT-stub
copy blocks so the cold-boot section runs once.

---

## 5. Git hygiene — untracked / modified working files

`.gitignore` reviewed. Classification of the working-tree noise:

### Untracked Python scripts in scripts/ (all throwaway probes; imported by nothing)

Verified none are imported by any tracked module (grep over scripts/ + src/ = 0 hits
each). They are one-off capture/inspect/trace utilities:

| file | size | classify |
|------|-----:|----------|
| scripts/analyze_img.py | 390 B | DELETE or keep local (throwaway) |
| scripts/ascii_art.py | 340 B | DELETE (toy) |
| scripts/capture_frames.py | 503 B | DELETE (throwaway) |
| scripts/capture_shalamar_pyboy.py | 1.8 K | DELETE / keep local |
| scripts/capture_all_bosses.py | 2.1 K | KEEP if useful for re-probing arenas; else delete |
| scripts/capture_all_bosses_natural.py | 2.3 K | KEEP if useful; else delete |
| scripts/inspect_bg_sweep_bytes.py | 374 B | DELETE (ad-hoc; this audit reproduces it) |
| scripts/inspect_colorize_bytes.py | 526 B | DELETE (ad-hoc) |
| scripts/inspect_da00_table.py | 1.5 K | DELETE (ad-hoc) |
| scripts/inspect_shalamar_tiles.py | 2.2 K | DELETE (ad-hoc) |
| scripts/inspect_shalamar_vram_attrs.py | 1.8 K | DELETE (ad-hoc) |
| scripts/simulate_gameplay.py | 1.7 K | DELETE / keep local |
| scripts/trace_transition.py | 1.1 K | DELETE / keep local |

Recommendation: these are emulator-driven probe scripts (they import pyboy/PIL) and
the user's testing convention favors emulator-driven validation, so a couple of the
`capture_all_bosses*` ones may be worth keeping as tracked tools. The `inspect_*` and
`analyze_img`/`ascii_art`/`capture_frames`/`simulate_gameplay`/`trace_transition` are
single-use scratch — **delete or move to a gitignored `tmp/` / `scripts/diagnostics/`
scratch area.** Do NOT commit them to scripts/ root where they add clutter.

### Other untracked

| file | classify | reason |
|------|----------|--------|
| package-lock.json | DELETE | empty npm lockfile (`"packages": {}`, no deps); spurious — repo is Python (uv/pyproject.toml). Add `package-lock.json` to .gitignore if an MCP/node tool keeps regenerating it. |
| rom/working/live_palettes.txt | GITIGNORE | auto-generated by live_palette_editor.py ("# Auto-generated by ..."). Add `rom/working/live_palettes.txt` (or `rom/working/*.txt`) to .gitignore. |
| rom/working/penta_dragon_dx_teleport.gb.ram | GITIGNORE | emulator SRAM, transient |
| rom/working/penta_dragon_dx_v301.gb.ram | GITIGNORE | emulator SRAM, transient |

### Modified (already tracked) — should be gitignored, not committed

| file | classify | reason |
|------|----------|--------|
| rom/Penta Dragon (J).gb.ram | GITIGNORE + git rm --cached | battery SRAM; emulator-mutated every run → perpetual diff noise |
| rom/Penta Dragon (J).sav | GITIGNORE + git rm --cached | same |

These (and the ~20 other `.ram`/`.sav` files already in `git ls-files`) are emulator
saves that change on every play session. The `.gitignore` currently only ignores
`rom/working/*.sav` (working dir), not `*.ram` anywhere nor `rom/*.sav`. Recommend
adding `*.ram` and `*.sav` (with a `!` allowlist for any intentionally-pinned
checkpoint saves under `rom/versions/`) and `git rm --cached` the mutating ones. This
is pre-existing tech debt, not introduced by this branch — flag for the user but do
not bulk-remove without confirmation (some `rom/versions/*.sav` may be intentional
pinned checkpoints).

### .gitignore additions recommended — RESOLVED iter 179

```
package-lock.json
rom/working/*.txt
*.ram
# (optionally) rom/*.sav  with  !rom/versions/*.sav  if those are intentional
```

**Iter 179 (2026-06-22):** added `/package-lock.json`, `rom/working/*.txt`,
`rom/working/*.ram`, and a global `*.ram` to .gitignore. Verified
post-update git status no longer shows live_palettes.txt, the .ram files,
or package-lock.json as untracked. Did NOT touch the tracked `rom/*.sav`
files (audit advised against bulk-removal — some may be intentional
pinned checkpoints; needs user audit before `git rm --cached`).

---

## Prioritized findings

1. **(Info, no action needed for prod)** Production = `penta_dragon_dx_v301.gb`
   (base build). It has NO per-arena colors, NO scene_detect, NO arena tables — those
   are teleport-build-only. Confirmed by ROM bytes (BASE 0x7200 = original ROM data,
   0x6FB0 = zeros).
2. **(Cleanup, low priority, KEEP recommended)** Position-sweep system (possweep 159B
   @0x7100, expander 30B @0x6D80, posmap RLE 754B @0x7B00, ptr table 18B @0x7FE0 =
   961B; 772B uniquely-dead) is fully dead (0 callers). Keep as opt-in fallback; add a
   DEAD-code comment. Live arena colorizer is the inline hook + 0xDA00 + scene_detect.
3. **(Fragility, medium for teleport ROM only)** DF1D/DF1F/DF20/DF21 overlap bg_sweep's
   0xDF10-0xDF2F buffer. Currently safe via fire-frame RET + 60-frame DF1F skip-gate,
   but invariant is brittle on slower hardware / longer arena init. Relocate the 4
   bytes below 0xDF10 if the teleport build is ever shared/promoted. Not in prod.
4. **(Cosmetic — RESOLVED iter 178)** Stale comments: teleport docstring said DF1E
   but code uses DF0E. Fixed in iter 178 (3 stale references updated, ROM rebuilds
   byte-identical). "GDMA" filename misnomer noted but not renamed (would churn
   git history; not worth the disruption).
5. **(Git hygiene — RESOLVED iter 179)** `.gitignore` updated to ignore
   `/package-lock.json`, `rom/working/*.txt`, `rom/working/*.ram`, and global
   `*.ram`. Tracked `rom/*.sav` files left alone (audit advised against bulk
   removal — some may be intentional pinned checkpoints; needs user decision
   before `git rm --cached`).

No correctness regressions found in either build. Both ROMs assemble with all
internal asserts passing (overflow guards, inline-hook entry-point check, arena slot
spacing check, bg_sweep prefix check).
