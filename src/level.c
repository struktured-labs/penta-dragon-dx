#include "level.h"
#include "enemy.h"
#include "palettes.h"

// Use the GAMEPLAY tiles (extracted from VRAM during actual gameplay)
// NOT the static ROM tiles (which are font/text characters)
#include "../assets/extracted/bg/include/bg_gameplay.h"

// Level 1 tilemap data extracted from the original Penta Dragon ROM
#include "level_data.h"

uint16_t scroll_x;
uint8_t  scroll_y;
uint8_t  scroll_col;
uint8_t  auto_scroll;

// BG tile palette lookup -- matches the DX colorizer categories
// Uses GAMEPLAY tile meanings from the original ROM:
//   0x00-0x06: Floor tiles (diamond checkerboard) -> Palette 0
//   0x07-0x0E: Wall edge/transition -> Palette 6
//   0x13-0x1E: Pillar/column components -> Palette 6
//   0x16:      Wall fill -> Palette 6
//   0x17:      Wall border -> Palette 6
//   0x18-0x1D: Staircase transition tiles -> Palette 6
//   0x20-0x39: Platform/ledge/staircase -> Palette 6
//   0x3E-0x3F: Torch fixtures -> Palette 5 (fire)
//   0x40-0x59: Wall structure -> Palette 6
//   0x88-0x9D: Items (original ROM item tiles) -> Palette 1 (gold)
//   0xA0-0xBB: Items (alternate range) -> Palette 1 (gold)
//   0xFE: Void -> Palette 7 (dark)

static const uint8_t bg_tile_pal[256] = {
    // 0x00-0x0F: Floor (0x00-0x06) then wall edges (0x07-0x0E) then floor (0x0F)
    0,0,0,0,0,0,0, 6,6,6,6,6,6,6,6, 0,
    // 0x10-0x1F: Misc (0x10-0x12), pillars/walls (0x13-0x1E), floor (0x1F)
    0,0,0, 6,6,6,6,6,6,6,6,6,6,6,6, 0,
    // 0x20-0x2F: Platform/staircase components -> Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x30-0x3F: More platform/staircase, then torches
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6, 5,5,
    // 0x40-0x4F: Wall tops -> Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x50-0x5F: Wall bottoms -> Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x60-0x6F: Extended arches -> Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0x70-0x7F: More architecture -> Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0x80-0x8F: Items (original ROM item tiles) -> Palette 1 (gold)
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    // 0x90-0x9F: Items (original ROM item tiles) -> Palette 1 (gold)
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    // 0xA0-0xAF: Items -> Palette 1 (gold)
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    // 0xB0-0xBF: Items -> Palette 1
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    // 0xC0-0xCF: HUD / items
    0,0,0,0,0,0,0,0, 0,0,0,0,1,1,1,1,
    // 0xD0-0xDF: HUD / items
    0,0,0,0,0,0,0,0, 0,0,0,0,1,1,1,1,
    // 0xE0-0xEF: -> Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0xF0-0xFF: HUD, then void
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0, 7,7,
};

// ============================================
// Level data lookup (replaces procedural gen)
// ============================================

// Get a column from the level data (wraps when past the end)
static void get_level_column(uint8_t *tiles, uint16_t col_idx) {
    uint8_t i;
    uint16_t data_col = col_idx % LEVEL1_NUM_COLUMNS;
    for (i = 0; i < LEVEL_HEIGHT; i++) {
        tiles[i] = level1_data[data_col][i];
    }
}

// Write a column of tiles + palette attributes to hardware tilemap
static void write_column(uint8_t map_col, uint8_t *tiles) {
    uint8_t row;
    uint8_t pal;

    for (row = 0; row < LEVEL_HEIGHT; row++) {
        set_bkg_tiles(map_col, row, 1, 1, &tiles[row]);
        VBK_REG = 1;
        pal = bg_tile_pal[tiles[row]];
        set_bkg_tiles(map_col, row, 1, 1, &pal);
        VBK_REG = 0;
    }
}

// ============================================
// Enemy spawning
// ============================================

// Enemy spawn: first at column 5, then every 10 columns
// Original: enemies appear as you enter a room area
#define SPAWN_INTERVAL 10
static uint16_t next_spawn_col;
static const uint8_t spawn_y[] = { 52, 36, 84, 68, 44, 76, 60 };
static uint8_t spawn_y_idx;
// Match original Level 1: mostly humanoids, some orcs, rare hornets/crows
static const uint8_t spawn_types[] = {
    ENEMY_HUMANOID, ENEMY_HUMANOID, ENEMY_ORC,
    ENEMY_HUMANOID, ENEMY_HUMANOID, ENEMY_HORNET,
    ENEMY_HUMANOID, ENEMY_ORC, ENEMY_HUMANOID,
    ENEMY_HUMANOID, ENEMY_CROW, ENEMY_HUMANOID
};
static uint8_t spawn_type_idx;

void level_init(void) {
    uint8_t col;
    uint8_t tiles[LEVEL_HEIGHT];

    scroll_x = 0;
    scroll_y = 0;
    scroll_col = 21;
    auto_scroll = 0; // Player-driven scrolling (bonus stages override this)
    next_spawn_col = 5; // First enemy after a bit of scrolling
    spawn_y_idx = 0;
    spawn_type_idx = 0;

    // Fill initial visible area (21 columns from the level data)
    for (col = 0; col < 21; col++) {
        get_level_column(tiles, col);
        write_column(col & 31, tiles);
    }
}

void level_load_tiles(void) {
    // Load the GAMEPLAY BG tiles (extracted from VRAM during actual gameplay)
    set_bkg_data(0, 255, BG_GAMEPLAY_TILES);
}

int8_t level_update(uint8_t keys) {
    uint8_t tiles[LEVEL_HEIGHT];
    uint8_t old_pixel;
    uint8_t new_pixel;
    int8_t scroll_amount = 0;

    old_pixel = (uint8_t)(scroll_x & 0x07);

    if (auto_scroll > 0) {
        // Auto-scroll mode (bonus stages)
        scroll_amount = (int8_t)auto_scroll;
    } else {
        // Original behavior: BG scrolls when player presses LEFT/RIGHT
        // Sara stays fixed on screen
        if (keys & J_RIGHT) {
            scroll_amount = 1; // ~1px/frame average (original does 4px/4frames)
        }
        // LEFT scrolling (back-track) -- slower
        if (keys & J_LEFT) {
            if (scroll_x > 0) {
                scroll_amount = -1;
            }
        }
    }

    if (scroll_amount > 0) {
        scroll_x += (uint8_t)scroll_amount;
        new_pixel = (uint8_t)(scroll_x & 0x07);
        SCX_REG = (uint8_t)(scroll_x & 0xFF);

        // Load next column when crossing tile boundary
        if (new_pixel < old_pixel) {
            uint8_t map_col = (uint8_t)((scroll_x >> 3) + 20) & 31;
            get_level_column(tiles, scroll_col);
            write_column(map_col, tiles);
            scroll_col++;
        }
    } else if (scroll_amount < 0 && scroll_x > 0) {
        scroll_x--;
        SCX_REG = (uint8_t)(scroll_x & 0xFF);
    }

    // Vertical scrolling: BG scrolls when UP/DOWN pressed (Sara stays fixed)
    if (keys & J_UP) {
        if (scroll_y > 0) {
            scroll_y--;
        }
    }
    if (keys & J_DOWN) {
        if (scroll_y < SCROLL_Y_MAX) {
            scroll_y++;
        }
    }
    SCY_REG = scroll_y;

    return scroll_amount;
}

uint8_t level_get_tile(uint16_t col, uint8_t row) {
    uint16_t data_col = col % LEVEL1_NUM_COLUMNS;
    if (row >= LEVEL_HEIGHT) return 0x00;
    return level1_data[data_col][row];
}

uint8_t level_is_solid(uint16_t world_x, uint8_t world_y) {
    uint16_t col = world_x >> 3;
    uint8_t row = world_y >> 3;
    uint8_t tile = level_get_tile(col, row);
    // Wall/pillar/platform tiles are solid
    // 0x13-0x1E: Pillar components
    // 0x20-0x39: Platform/staircase
    // 0x40-0x59: Wall structure
    // 0xFE: Void (not walkable)
    return (tile >= 0x13 && tile <= 0x1E) ||
           (tile >= 0x20 && tile <= 0x39) ||
           (tile >= 0x40 && tile <= 0x59) ||
           (tile == 0xFE);
}

void level_check_spawns(void) {
    uint16_t current_col = scroll_x >> 3;

    if (current_col >= next_spawn_col && enemy_count < MAX_ENEMIES) {
        uint8_t type = spawn_types[spawn_type_idx];
        uint8_t y = spawn_y[spawn_y_idx];

        enemy_spawn(type, 168, y);

        spawn_y_idx = (spawn_y_idx + 1) % sizeof(spawn_y);
        spawn_type_idx = (spawn_type_idx + 1) % sizeof(spawn_types);
        next_spawn_col += SPAWN_INTERVAL;
    }
}
