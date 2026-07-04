#ifndef QUINTRA_GAME_ROOM_H
#define QUINTRA_GAME_ROOM_H

#include "core/types.h"
#include "game/screen.h"

// Visible BG grid: 20 cols × 17 rows (136 px). The bottom 8 px of the
// screen belong to the HUD WINDOW strip — GB windows extend to the bottom
// of the frame, so the HUD must be the LAST rows, and the room must end
// above it. No scrolling yet.
#define ROOM_W 20
#define ROOM_H 17

extern u8 room_tilemap[ROOM_H][ROOM_W];

// Tile id at world pixel position (BGT_WALL for out-of-bounds).
u8 room_tile_at_px(i16 px, i16 py);
// 1 if the tile id is walkable / passable for entities+bullets.
u8 room_tile_walkable(u8 t);

void        room_enter(void);
void        room_exit(void);
screen_id_t room_tick(u8 keys, u8 pressed);
void        room_draw(void);

#endif
