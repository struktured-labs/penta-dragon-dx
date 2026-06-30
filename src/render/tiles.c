#include <gb/gb.h>

#include "core/types.h"
#include "render/tiles.h"

// All tiles are 2bpp 8x8 (16 bytes). For each row: byte_low, byte_high.
// color = (high_bit, low_bit) per pixel.

// Floor — uniform color 1 (mid)
const u8 bg_tile_floor[16] = {
    0xFF, 0x00,  0xFF, 0x00,  0xFF, 0x00,  0xFF, 0x00,
    0xFF, 0x00,  0xFF, 0x00,  0xFF, 0x00,  0xFF, 0x00,
};

// Wall — color 3 (bright) with darker speckles on left edge
const u8 bg_tile_wall[16] = {
    0xFF, 0xFF,  0x7F, 0xFF,  0xFF, 0xFF,  0xBF, 0xFF,
    0xFF, 0xFF,  0xDF, 0xFF,  0xFF, 0xFF,  0xEF, 0xFF,
};

// Door — color 2 (accent) frame
const u8 bg_tile_door[16] = {
    0xFF, 0xFF,  0x81, 0x7E,  0xBD, 0x7E,  0xBD, 0x7E,
    0xBD, 0x7E,  0xBD, 0x7E,  0x81, 0x7E,  0xFF, 0xFF,
};

// Void — color 0 (black)
const u8 bg_tile_void[16] = {
    0,0, 0,0, 0,0, 0,0, 0,0, 0,0, 0,0, 0,0,
};

// Player — 6x6 square in color 1 with color 2 corners
const u8 sprite_tile_player[16] = {
    0x00, 0x00,
    0x3C, 0x00,
    0x7E, 0x00,
    0x7E, 0x00,
    0x7E, 0x00,
    0x7E, 0x00,
    0x3C, 0x00,
    0x00, 0x00,
};

void tiles_load_room_bg(void) {
    set_bkg_data(BGT_VOID,  1, bg_tile_void);
    set_bkg_data(BGT_FLOOR, 1, bg_tile_floor);
    set_bkg_data(BGT_WALL,  1, bg_tile_wall);
    set_bkg_data(BGT_DOOR,  1, bg_tile_door);
}

void tiles_load_player_sprite(void) {
    set_sprite_data(SPR_PLAYER, 1, sprite_tile_player);
}
