# Boss arena verification checklist (item 12) — 2026-06-14

Method: reach each arena via boss-teleport (load level1_sara_d_alone.ss0 -> D880=0x02
FFC1=1; set FFBA=idx-1; pulse SELECT+START; wait D880=0x0C+idx). Sample active
tilemap 200-300 frames; count steady-state palette flips (a cell's BG palette
changing frame-to-frame while its tile ID is stable = flicker).

RESULT: ZERO flicker on all 9 arenas. The colorizer is stable (inline hook +
bg_sweep read the same per-arena 0xDA00 table, so no competing-writer flip — the
old position-sweep work is not needed in this build). Crystal Dragon's red-flood
history is RESOLVED (now cyan). Only remaining items are palette QUALITY (flat
vs multi-color), not bugs.

| # | Boss          | D880 | reached | flicker | status |
|---|---------------|------|---------|---------|--------|
| 0 | Shalamar      | 0x0C | yes     | 0       | GOOD — multi-pal body (p1/p4/p0). Best-colorized. |
| 1 | Riff          | 0x0D | yes     | 0       | OK — multi-pal (p2 purple body 195 tiles + p1 red accents 42 tiles per ARENA_TILE_PAL). |
| 2 | Crystal Dragon| 0x0E | yes     | 0       | OK — multi-pal (p4 cyan 23 + p7 spider 38 + p2 purple 10 tiles). No flicker. |
| 3 | Cameo         | 0x0F | yes     | 0       | OK — multi-pal (p1 gold 175 + p5 green 33 + p2 purple 32 tiles). |
| 4 | Ted           | 0x10 | yes     | 0       | OK — OBJ-drawn boss; BG table mostly unused (p0/white). |
| 5 | Troop         | 0x11 | yes     | 0       | GOOD — multi-pal (p0/p7). |
| 6 | Faze          | 0x12 | yes     | 0       | GOOD — multi-pal (p0/p1/p2/p6); drop-shadow present. |
| 7 | Angela        | 0x13 | yes     | 0       | GOOD — multi-pal (p0/p7/p1/p2). |
| 8 | Penta Dragon  | 0x14 | yes     | 0       | GOOD — multi-pal (p0/p1/p2/p3/p4/p5). |

2026-06-21 UPDATE (iter 161): Riff/Crystal/Cameo were previously labeled
"FLAT mono" but inspection of `scripts/arena_tables_data.py` ARENA_TILE_PAL
shows they're actually multi-palette by table design. The "FLAT" perception
may have come from an earlier table revision; current tables (verified
post-iter-12+) all use 2-3 palettes per arena. No additional enrichment
work needed unless the user reports a visible color complaint.

TO VERIFY YOURSELF: boss-teleport to each (SELECT+START in a dungeon), look
for flicker (none expected) and overall color.
