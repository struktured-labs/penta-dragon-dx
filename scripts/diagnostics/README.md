# Arena colorization diagnostics

Probes used to diagnose the boss-arena color alternation + shared-tile issues
(2026-06-07). Run headed: `mgba-qt rom/working/penta_dragon_dx_teleport.gb
--script scripts/diagnostics/<probe>.lua` (teleports to Shalamar, writes a log
to /tmp/).

- `probe_arena_alternation_cause.lua` — tracks specific boss cells' (tile,attr)
  + D880 over time. Finding: D880 stable (no scene thrash); cells show
  ATTR-FLIP with the tile STABLE → palette gets cleared to 0 between the
  1-row/frame sweep passes while the boss animates faster. Root cause of the
  "alternating colors."
- `probe_boss_coord.lua` — correlates WRAM coords with the boss's visual top
  row. Finding: boss tilemap footprint is STABLE (top=0 always); the visual
  "bob" is a SCX/SCY scroll shake (FF42/FF43 oscillate), NOT the boss moving
  in tilemap space. => position-based coloring in TILEMAP space is stable
  through the bob (scroll moves tiles + attrs together).
- `probe_arena_timeseries.lua` — captures 4 time-spaced screenshots + counts
  tiles that show >1 palette over time (134 for Shalamar = the alternation).

Conclusion: the fix is a static, position-banded attribute buffer blitted to
VRAM every frame (atomic, via the GDMA path) — kills alternation (fresh every
frame, not tile-dependent) and shared-tile bleed (color by cell, not tile ID).
