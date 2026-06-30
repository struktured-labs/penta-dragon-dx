#ifndef QUINTRA_GAME_ROOM_H
#define QUINTRA_GAME_ROOM_H

#include "core/types.h"
#include "game/screen.h"

// Visible BG grid: 20 cols × 18 rows. Phase 4 rooms are exactly that —
// no scrolling. Phase 7 adds larger room sizes + camera scroll.
#define ROOM_W 20
#define ROOM_H 18

extern u8 room_tilemap[ROOM_H][ROOM_W];

void        room_enter(void);
void        room_exit(void);
screen_id_t room_tick(u8 keys, u8 pressed);
void        room_draw(void);

#endif
