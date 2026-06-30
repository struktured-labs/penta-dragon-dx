// Tile / sprite primitives — Phase 4 placeholder graphics.
// Phase 7+ will replace these with real biome-themed assets via quintra-assets.
#ifndef QUINTRA_RENDER_TILES_H
#define QUINTRA_RENDER_TILES_H

#include "core/types.h"

// BG tile slots
#define BGT_FLOOR  1
#define BGT_WALL   2
#define BGT_DOOR   3
#define BGT_VOID   0

// OBJ tile slots (sprite VRAM lives at 0x8000)
#define SPR_PLAYER 0

// Tile blobs
extern const u8 bg_tile_floor[16];
extern const u8 bg_tile_wall[16];
extern const u8 bg_tile_door[16];
extern const u8 bg_tile_void[16];
extern const u8 sprite_tile_player[16];

void tiles_load_room_bg(void);
void tiles_load_player_sprite(void);

#endif
