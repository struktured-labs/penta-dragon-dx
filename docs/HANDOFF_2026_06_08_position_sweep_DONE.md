# Handoff — boss-arena colorization HOLY GRAIL delivered (2026-06-08)

Supersedes `HANDOFF_2026_06_08_arena_colorization.md` (which ended at "GDMA
dead, position-sweep next"). The position sweep is built, working, and verified
in mGBA for **all 9 boss arenas**.

## What was achieved

The goal — color each boss arena with **no color alternation** and **no shared
boss/background tile bleed** — is met in mGBA for all 9 bosses, using plain CPU
VBlank writes (no HDMA, so it coexists with the arena's scroll-shake that killed
the GDMA approach).

Branch `wip-arena-position-sweep` (pushed), tag `milestone-arena-position-all9`.
Commits `83bdddd` (Phase-0 table fix) → `d74b47d` (all 9 posmaps) + long-run probe.

## How it works (see [[project_arena_position_sweep]] in memory for full detail)

1. **Neutralize** the inline hook's attr writes in arenas (0x42A7 D880 entry-
   branch → tile-only copy) so the position sweep is the sole attr writer.
2. **Position sweep** (bank13:0x7100, VBlank): per-cell FIXED posmap → no
   alternation by construction. Posmaps RLE-compressed in bank 13 (930 B),
   expanded per-arena to WRAM 0xD000.
3. **Posmaps** = the modal palette the good Phase-0 hook gives each cell
   (`probe_arena_posmap_gen.lua`), >=25% coverage for swept limbs.

Also fixed a standalone bug (Phase-0): the bg_sweep read the dungeon table in
arenas while the hook read the per-scene table → they disagreed and flipped
every sweep pass. Unified to WRAM 0xDA00 (Shalamar 606→210 flips).

## Verification done (mGBA, headless)

- **No steady alternation**, all 9: flip_stable == distinct_flip_cells (each
  cell changes once = settle, then stable). shalamar 139, riff 284, crystal 296,
  cameo 130, ted 127, troop 129, faze 78, angela 254, penta 158.
- **Visuals** (montage): all 9 colored, no white/uncolored boss. riff / angela /
  penta / faze / cameo / ted vibrant & thematic; shalamar banded shell + natural
  gray legs; crystal / troop full-screen banded (matches their footprints).
- **No regressions**: dungeon pixel-diff vs Phase-0 = 0.24% (sprite timing
  only); Sara OBJ palettes intact in arenas (BG-hook neutralize doesn't touch
  sprites); mini-bosses unaffected (gated out — they're D880=0x0A, not 0x0C-14).

## NEXT — needs you / follow-up

1. **MiSTer hardware verification** (the real gate; mGBA-clean != hardware-clean
   historically, and FF70 bank-switching in the sweep is new on hardware).
   - MiSTer was offline this session (couldn't auto-deploy).
   - When up: deploy `rom/working/penta_dragon_dx_teleport.gb` (the all-9 build)
     as a TEST file (don't overwrite production v3.01). Start the game on the
     gamepad (DOWN→A→A→A→START→A), then **SELECT+START** cycles bosses
     0→8 (Shalamar→…→Penta) so you can check all 9 fast. Or just play to a boss.
   - Watch for: freeze on arena entry (FF70/expander), or flicker (would mean
     a hardware timing difference vs mGBA).
   - Say "deploy it" and I'll SCP it once the MiSTer is reachable.
2. **Production promotion**: the teleport build already colors arenas in normal
   play, so it's effectively production-capable (the combo is just a bonus). For
   a clean ship, optionally strip the SELECT+START combo. Decide after hardware
   verify.
3. **Optional polish** (taste calls — better done with you or via the live
   editor): crystal/troop band the whole background (their bosses are small) —
   could tighten to color only the boss if you prefer default backgrounds;
   per-arena CRAM for richer stable colors.

## Tooling added this session (scripts/diagnostics/)

- `probe_arena_posmap_gen.lua` — generate a posmap from the hook-active ROM.
- `probe_arena_alt_fullscan.lua` — alternation A/B harness (flip_stable count).
- `probe_arena_longrun.lua` — windowed stability + Sara OBJ check.
- `probe_arena_dump.lua`, `probe_shal_multishot.lua`, `probe_dungeon_shot.lua`.
- `montage.py` — combine per-boss screenshots into a review grid.
- Build: `python scripts/build_v301_teleport.py`. Posmap source:
  `scripts/diagnostics/posmap_maps.log` (regenerate with the gen probe).
