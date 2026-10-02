# RC11 — low-health, game-over, and Sara-form state bugs (2026-08-30)

**Build under test:** `Penta Dragon DX v3.01-924173f3cd82.gbc`
md5 `58e5357354cd2dde8568ab18e4082661`, 524288 bytes (`0dd75f9` rc11).

**Status: USER-REPORTED, NOT YET REPRODUCED OR INSTRUMENTED.**
Everything below the symptom list is hypothesis. No probe was run, no save
state captured, no tile/attr dump taken. Treat the causes as leads to test,
not findings. Recorded now so the reports aren't lost.

## Symptoms (as reported by the operator, playing on moonshot)

1. **Low-health "emergency mode" visual breakdown.** When HP drops into the
   emergency/warning state, the screen "falls apart visually."
2. **Post-game-over corruption.** After the game-over sequence, "everything
   was corrupted, colors missing."
3. **Sara form not reset.** On starting a new game after that game over, Sara
   appeared as **Sara D (dragon form)** rather than the normal starting form.

(2) and (3) were observed in the same run, immediately after (1) → death.

## Captures

No capture is confirmed to show any of these three. There is one screenshot
at the right wall-clock time —
`rom/working/penta_dragon_dx_rc11_official-5.png` (11:07) — but **its
provenance is unconfirmed**; it may simply be a hazard room. Its colour
histogram shows pal0 (`#a5a5ff`/`#52527b`), pal5 hazard yellow/red
(`#ffff00`/`#ff0000`), and pal6 (`#dec6ff`/`#42427b`). Do not treat it as
evidence for these bugs without the operator confirming what it depicts.

## Hypotheses to test

### H1 — death / game-over scenes fall through to the dungeon table

This is the **same bug class** already fixed twice in this codebase. Commit
`fdf41ad` ("bg-flood: fix title-banner red bands + post-boss-reload red
flood") generalised `scene_detect`'s splash branch to cover
`D880 ∈ {0x18, 0x1B, 0x16}` precisely because scenes not special-cased fall
through to the dungeon table, whose `0x80-0xDF → pal1` rule floods them.

Relevant D880 values (per `CLAUDE.md`):

| D880 | Scene |
|------|-------|
| `0x17` | **death** |
| `0x16` | post-boss reload (already covered by `fdf41ad`) |
| `0x18` | boss splash (covered) |
| `0x1B` | title banner (covered) |

**`0x17` (death) does not appear in the covered set.** If the game-over /
continue / name-entry screens also run at their own D880 values outside that
set, they would inherit dungeon palettes → "corrupted, colors missing."

*Test:* probe `D880` across the death → game-over → new-game transition and
log which values appear; check each against `scene_detect`'s branch table.

### H2 — low-health emergency mode drives a palette/flash effect that the colorizer fights

The HUD is known to have a `MEDICAL / H.P. / MEGA_FLASH` strip
(`docs/v301_resolved_issues.md:66`). "MEGA_FLASH" suggests the game drives a
flash effect at low HP, likely by rewriting palettes or attributes each
frame. If the DX colorizer also writes those cells every VBlank, the two
writers alternate → visual breakdown.

Note a closely-related issue was already fixed once: **item-menu HUD attr
bleed**, resolved in rc3 by keeping the visible window attr rows on palette 0
and pausing `bg_sweep` while the menu is open
(`docs/agent_memory_update.md:59`). The low-health path may need the same
treatment.

*Test:* watch HP (`DCDC`/`DCDD`) into the emergency threshold while logging
BG palette RAM + attr writes per frame; check whether game and colorizer are
both writing the HUD region.

### H3 — Sara form byte not reset on new game

`FFBE` holds Sara's form (`1` = Dragon). If the death / game-over path does
not reset `FFBE`, a new game starts with the stale dragon value → Sara D at
onset.

Worth determining whether this reproduces on **vanilla** `Penta Dragon (J).gb`.
If it does, it is an original-game bug and not a DX regression — that changes
whether it should be fixed at all.

*Test:* read `FFBE` immediately before death, during game over, and on the
first gameplay frame of the new game. Repeat on vanilla for comparison.

## Priority note

H1 is the strongest lead: it is a known, twice-recurring bug class in this
codebase with a known fix shape (add the scene's D880 to the splash-table
branch in `scene_detect`), and it would explain symptom (2) directly.

---
Recorded on moonshot from operator play-testing of the official RC11
artifact. No instrumentation performed.
