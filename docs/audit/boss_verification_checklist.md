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
| 1 | Riff          | 0x0D | yes     | 0       | OK — mono purple (p2) by table design. Flat but clean. |
| 2 | Crystal Dragon| 0x0E | yes     | 0       | OK — mono cyan (p4). No red-flood, no flicker. Flat. |
| 3 | Cameo         | 0x0F | yes     | 0       | FLAT — mono red (p1, 387/432 cells). Looks heavy; candidate to enrich. |
| 4 | Ted           | 0x10 | yes     | 0       | OK — OBJ-drawn boss; BG table mostly unused (p0/white). |
| 5 | Troop         | 0x11 | yes     | 0       | GOOD — multi-pal (p0/p7). |
| 6 | Faze          | 0x12 | yes     | 0       | GOOD — multi-pal (p0/p1/p2/p6); drop-shadow present. |
| 7 | Angela        | 0x13 | yes     | 0       | GOOD — multi-pal (p0/p7/p1/p2). |
| 8 | Penta Dragon  | 0x14 | yes     | 0       | GOOD — multi-pal (p0/p1/p2/p3/p4/p5). |

TO VERIFY YOURSELF: boss-teleport to each (SELECT+START in a dungeon), look for
flicker (none expected) and overall color. Flat ones (Riff/Crystal/Cameo) are by
arena-table design — enriching them to multi-palette body parts (item 6 "more
colorful") is a low-risk follow-up that needs a per-boss tile-position re-probe
to know which tiles are which body part (scripts/arena_tables_data.py ARENA_TILE_PAL).
