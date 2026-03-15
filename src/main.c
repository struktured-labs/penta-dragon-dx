// Penta Dragon DX Remake - GBC Native
// Full color from the ground up

#include <gb/gb.h>
#include <gb/cgb.h>
#include <gb/metasprites.h>
#include <string.h>

#include "palettes.h"

// Include extracted tile data
#include "../assets/extracted/bg/include/bg_all.h"
#include "../assets/extracted/sprites/include/sprites_sara_witch.h"
#include "../assets/extracted/sprites/include/sprites_sara_dragon.h"
#include "../assets/extracted/sprites/include/sprites_hornets.h"
#include "../assets/extracted/sprites/include/sprites_crows.h"
#include "../assets/extracted/sprites/include/sprites_orcs.h"
#include "../assets/extracted/sprites/include/sprites_effects_projectiles.h"

// BG tile palette assignment table (same logic as original colorizer)
// Maps tile_id -> CGB palette number (0-7)
// Stored in a 256-byte lookup table
static const uint8_t bg_tile_palette[256] = {
    // 0x00-0x3F: Floor/edges/platforms -> Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0x40-0x5F: Wall fill blocks -> Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x60-0x87: Arches/doorways -> Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    // 0x88-0xDF: Items -> Palette 1 (gold)
    1,1,1,1,1,1,1,1,
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    1,1,1,1,1,1,1,1,
    // 0xE0-0xFD: Decorative -> Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,
    // 0xFE-0xFF: Void -> Palette 0
    0, 0
};

// Demo tilemap: fill screen with a mix of dungeon tiles
// 20x18 visible area from the 32x32 hardware tilemap
static void setup_demo_bg(void) {
    uint8_t tilemap[32];
    uint8_t attrmap[32];
    uint8_t y, x;

    // Fill background with a simple dungeon pattern
    for (y = 0; y < 18; y++) {
        for (x = 0; x < 20; x++) {
            uint8_t tile;

            // Create a dungeon-like layout
            if (y == 0 || y == 17) {
                // Top/bottom walls
                tile = 0x48; // Wall fill tile
            } else if (x == 0 || x == 19) {
                // Side walls
                tile = 0x4A; // Wall edge tile
            } else if (y == 3 && x >= 4 && x <= 7) {
                // Arch/doorway
                tile = 0x62 + (x - 4);
            } else if (y == 8 && x == 10) {
                // Item (potion)
                tile = 0x90;
            } else if (y == 8 && x == 12) {
                // Item (heart)
                tile = 0x92;
            } else if (y == 8 && x == 14) {
                // Item (extra life)
                tile = 0x94;
            } else if (y >= 14 && y <= 16) {
                // Floor platform
                tile = 0x02 + ((x + y) & 0x03);
            } else {
                // Empty floor
                tile = 0x00;
            }

            tilemap[x] = tile;
            attrmap[x] = bg_tile_palette[tile]; // CGB palette from lookup
        }
        // Write tile row
        set_bkg_tiles(0, y, 20, 1, tilemap);
        // Write attribute row (CGB palette per tile)
        VBK_REG = 1;
        set_bkg_tiles(0, y, 20, 1, attrmap);
        VBK_REG = 0;
    }
}

// Player state
static uint8_t player_x = 80;
static uint8_t player_y = 120;
static uint8_t player_form = 0; // 0=Witch, 1=Dragon
static uint8_t player_frame = 0;
static uint8_t player_dir = 0; // 0=right, 1=left

#define SARA_W_SPRITE_START 0
#define SARA_D_SPRITE_START 8
#define PLAYER_SPEED 2

static void init_sprites(void) {
    // Load Sara Witch tiles at VRAM tile 0
    set_sprite_data(SARA_W_SPRITE_START, SPRITE_SARA_WITCH_TILE_COUNT,
                    SPRITE_SARA_WITCH);

    // Load Sara Dragon tiles at tile 8
    set_sprite_data(SARA_D_SPRITE_START, SPRITE_SARA_DRAGON_TILE_COUNT,
                    SPRITE_SARA_DRAGON);
}

static void update_player_sprite(void) {
    uint8_t tile_base;
    uint8_t palette;
    uint8_t flags = 0;

    if (player_form == 0) {
        // Witch: 4 frames, 2 tiles each (16x16)
        tile_base = SARA_W_SPRITE_START + (player_frame & 0x01) * 2;
        palette = 2; // Sara Witch palette
    } else {
        // Dragon: 4 frames, 2 tiles each (16x16)
        tile_base = SARA_D_SPRITE_START + (player_frame & 0x01) * 2;
        palette = 1; // Sara Dragon palette
    }

    // Flip horizontally when facing left
    if (player_dir) {
        flags |= S_FLIPX;
    }

    // Set CGB palette in flags
    flags |= (palette & 0x07);

    // 16x16 sprite = 2 tiles (top + bottom in 8x16 mode)
    // Or 4 tiles in 8x8 mode arranged as 2x2
    // Using 8x8 mode with 4 sprite slots for a 16x16 character
    set_sprite_tile(0, tile_base);
    set_sprite_prop(0, flags);
    move_sprite(0, player_x, player_y);

    set_sprite_tile(1, tile_base + 1);
    set_sprite_prop(1, flags ^ (player_dir ? S_FLIPX : 0));
    move_sprite(1, player_x + (player_dir ? -8 : 8), player_y);

    set_sprite_tile(2, tile_base + 2);
    set_sprite_prop(2, flags);
    move_sprite(2, player_x, player_y + 8);

    set_sprite_tile(3, tile_base + 3);
    set_sprite_prop(3, flags ^ (player_dir ? S_FLIPX : 0));
    move_sprite(3, player_x + (player_dir ? -8 : 8), player_y + 8);
}

static uint8_t anim_counter = 0;

static void handle_input(void) {
    uint8_t keys = joypad();

    if (keys & J_LEFT) {
        player_x -= PLAYER_SPEED;
        player_dir = 1;
    }
    if (keys & J_RIGHT) {
        player_x += PLAYER_SPEED;
        player_dir = 0;
    }
    if (keys & J_UP) {
        player_y -= PLAYER_SPEED;
    }
    if (keys & J_DOWN) {
        player_y += PLAYER_SPEED;
    }

    // SELECT to toggle Sara form
    if (keys & J_SELECT) {
        player_form ^= 1;
        // Small delay to prevent rapid toggling
        delay(200);
    }

    // Animation
    anim_counter++;
    if (anim_counter >= 15) {
        anim_counter = 0;
        player_frame = (player_frame + 1) & 0x03;
    }
}

void main(void) {
    // Detect CGB hardware
    if (_cpu == CGB_TYPE) {
        // Enable CGB features
        cpu_fast(); // Double-speed mode
    }

    // Turn off display during setup
    DISPLAY_OFF;

    // Load palettes (CGB color)
    init_palettes();

    // Load BG tiles into VRAM (array is BG_TILES from bg_all.h)
    set_bkg_data(0, 255, BG_TILES);

    // Set up demo background with per-tile palette attributes
    setup_demo_bg();

    // Load sprite tiles
    init_sprites();

    // Show background and sprites
    SHOW_BKG;
    SHOW_SPRITES;
    DISPLAY_ON;

    // Main game loop
    while (1) {
        wait_vbl_done(); // Sync to VBlank

        handle_input();
        update_player_sprite();
    }
}
