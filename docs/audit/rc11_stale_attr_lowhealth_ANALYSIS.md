# RC11 wall/HUD corruption — corrected root cause: stale BG attrs, low-HP correlated (2026-08-30)

**Build:** `Penta Dragon DX v3.01-924173f3cd82.gbc` md5 `58e5357354cd2dde8568ab18e4082661` (`0dd75f9` rc11).

**Save states analysed** (operator-captured on moonshot, mgba PNG states):
- `save_states_for_claude/rc11_corrupted-walls.ss0`
- `save_states_for_claude/rc11_low-health-degradation.ss0`

> ## ⚠️ THIS SUPERSEDES `rc11_wall_edge_pal6_speckle.md`
> That earlier doc blamed the speckled `0x13-0x23` band in `BG_TABLE_BYTES`
> (pitfall #4). **That diagnosis was wrong as a primary cause.** It was
> inferred from pixel colours before save states existed. The table *is*
> speckled and that finding still stands on its own, but it **cannot** produce
> the corruption actually observed — see "Why the table is not the cause"
> below. Treat the speckle as a separate, lower-priority cosmetic issue.

## Method

mgba `.ss0` files are PNG-wrapped; state lives in the `gbAs` chunk
(zlib, 71680 bytes uncompressed). Anchors located by searching the state for
the known 256-byte `BG_TABLE_BYTES` (found at state offset `0x4A00`), giving:

- **WRAM base** = state `0x4400` (so `0xC000` → `0x4400`; table is at WRAM `0xC600`, matching `WRAM_BG_TABLE` in `build_v302_title_fix.py:116`)
- **VRAM base** = state `0x0400` (tilemap `0x9800` → `0x1C00`; attr plane → `0x3C00`)

WRAM anchor sanity-checked against `D880`/`DCDC`/`DCDD`/`DCB8` producing
in-range values.

## Hard findings

### 1. Both states are at zero main HP

| | corrupted-walls | low-health-degradation |
|---|---|---|
| `D880` (scene) | `0x0B` | `0x0B` |
| `DCDC` (HP sub) | `0x0C` | `0x0C` |
| **`DCDD` (HP main)** | **`0x00`** | **`0x00`** |
| `DCB8` | `0x02` | `0x01` |
| `DCBB` | `0x0F` | `0x1C` |

**The operator's hunch is confirmed: low health is a factor in _both_ captures,
including the one labelled "corrupted walls."** Both sit at `DCDD == 0x00`.
Both also report the same, otherwise-undocumented scene value `D880 = 0x0B`
(`CLAUDE.md` documents `0x02` dungeon, `0x0A` mini-boss, `0x0C-0x14` arenas —
`0x0B` is not listed).

### 2. The same tile ID renders with two different palettes at once

BG attr plane histograms:

- corrupted-walls: `{pal0: 974, pal6: 50}`
- low-health-degradation: `{pal0: 834, pal5: 78, pal6: 66, pal7: 46}`

Tile IDs appearing with **more than one palette simultaneously**:

- corrupted-walls — **12**: `0x03 0x04 0x10 0x14 0x17 0x21 0x24 0x25 0x34 0x37 0x39 0xFE`
- low-health-degradation — **25**: `0x01 0x02 0x03 0x04 0x05 0x16 0x24 0x25 0x30 0x35 0x3F 0x64 0x68 0x69 0x6C 0x6D 0x6E 0x71 0x74 0x76 0x78 0x7C 0x7D 0x7E 0xFE`

### 3. The palette is position-dependent, not tile-dependent

Tile `0x04` (table says pal 0), by screen cell:

```
(row 0, col 17) -> pal 6      (row 1, col 16) -> pal 0
(row 2, col 17) -> pal 6      (row 3, col 16) -> pal 0
(row 4, col 17) -> pal 6      (row 5, col 16) -> pal 0
(row 8, col 13) -> pal 6      (row 9, col 12) -> pal 0
```

Column 17 → pal6, column 16 → pal0, **same tile ID**.

## Why the table is not the cause

The BG table is a pure tile-ID → palette lookup. It is a **function of tile ID
alone**. It is therefore incapable of producing:

- the same tile ID with two palettes on one screen, or
- a palette that varies by screen column.

27 of 48 distinct on-screen tile IDs disagree with what the table prescribes.
Whatever wrote these attrs was not driven by the table.

## Actual root cause (high confidence)

This is **pitfall #5**, the stale-attr class:

> **The "stale pal7 attrs" bug** (v297-v299 sweep race): the CGB boot ROM init
> writes pal7 to all BG attrs. Our bg_sweep visits one row per frame, so when
> the game writes new tiles between sweep visits, those attrs stay at pal7.

Same mechanism, pal6/pal7 residue instead. Some tile-writing path is
**bypassing the DX inline attr hook at bank1:0x42A7** — writing tile IDs
without writing the matching attribute byte — so those cells keep whatever
palette was previously there. Hence position-dependence: the attr is a
function of *what used to be in that cell*, not of the tile now in it.

There is direct precedent for exactly this in the codebase:

- `docs/audit/levelselect_score_bleed.md` — the level-select screen "draws the
  letters with the **direct tilemap writer (tile IDs only, no CGB attribute)**"
  and runs its own DI'd loop, so the colorizer never reaches it.
- `docs/agent_memory_update.md:59` — item-menu HUD attr bleed, fixed in rc3 by
  pinning visible window attr rows to pal0 and pausing `bg_sweep` while the
  menu is open.

The low-health capture shows the `MEDICAL / H.P. / MEGA_FLASH` HUD strip open
(pal5 and pal7 appear only in that state), which is the same HUD family as the
rc3 fix. **The rc3 mitigation may not cover the low-HP/emergency variant of
that overlay.**

## What to do next

1. **Identify the tile writer used at `D880 = 0x0B` / low HP.** If it is the
   direct tilemap writer, it needs the same treatment as level-select: either
   route it through the inline hook, or clear/stamp the attr plane on entry.
2. **Establish what `D880 = 0x0B` actually is.** Both captures report it and it
   is undocumented. If it is the emergency/low-HP state, it needs an explicit
   branch in `scene_detect` — this would be the *fourth* scene in this bug
   family after `0x18`, `0x1B`, `0x16` (`fdf41ad`).
3. Only then revisit the table speckle, which is cosmetic by comparison.

## Explicitly NOT established

- **`D880 = 0x0B` is correlated with low HP across 2 samples — that is not
  proof it means "emergency mode."** Both samples came from one play session.
  Needs a third sample at full HP to test.
- Which of `0x9800` / `0x9C00` is the active BG map was not determined (LCDC
  bit 3 not read). **The finding holds either way** — both maps exhibit the
  multi-palette anomaly (`0x9800`: 12 tiles, `0x9C00`: 17 tiles).
- The reported **post-game-over corruption** and **Sara-D-on-new-game** are
  not covered by these states; they remain unreproduced. See
  `rc11_death_and_lowhealth_state_bugs.md`.

---
Static analysis of operator save states on moonshot. No emulation run.
