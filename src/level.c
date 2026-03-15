#include "level.h"
#include "enemy.h"
#include "palettes.h"

#include "../assets/extracted/bg/include/bg_all.h"

uint16_t scroll_x;
uint8_t  scroll_col;
uint8_t  scroll_speed;

// BG tile palette lookup (same as original colorizer's 256-byte table)
static const uint8_t bg_tile_pal[256] = {
    // 0x00-0x3F: Floor/edges -> Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0x40-0x5F: Walls -> Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x60-0x87: Arches -> Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,
    // 0x88-0xDF: Items -> Palette 1
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

// ============================================
// Procedural level generation
// ============================================
// The original has 7 rooms, each ~200 scroll pixels wide.
// For now, generate a repeating dungeon pattern.

// Room templates (column patterns, 18 rows each)
// Each byte = tile ID. Uses the actual extracted tile IDs.
//
// Looking at the BG tileset:
//   0xE0-0xEF region has architectural tiles (walls, pillars)
//   0xF0-0xFD region has more dungeon decorations
//   0x40-0x5F has wall fill patterns
//   0x00 = empty/blank

// Simple dungeon column patterns
#define T_EMPTY   0x00
#define T_WALL    0x48  // Solid wall fill
#define T_WALL2   0x4A  // Wall variant
#define T_BRICK   0x4C  // Brick pattern
#define T_FLOOR   0xE0  // Floor tile
#define T_CEIL    0xE2  // Ceiling tile
#define T_PILLAR  0xE4  // Pillar tile
#define T_ARCH_T  0x62  // Arch top
#define T_ARCH_B  0x64  // Arch bottom
#define T_ITEM_HP 0x90  // Health item
#define T_ITEM_PW 0x92  // Powerup item

// Column types for procedural generation
#define COL_OPEN     0  // Open passage
#define COL_WALL     1  // Solid wall column
#define COL_PLATFORM 2  // Floor + ceiling, open middle
#define COL_NARROW   3  // Narrow passage
#define COL_ITEM     4  // Open with item

// Room template: repeating 20-column pattern
static const uint8_t room_pattern[] = {
    COL_WALL,     // 0
    COL_PLATFORM, // 1
    COL_OPEN,     // 2
    COL_OPEN,     // 3
    COL_PLATFORM, // 4
    COL_OPEN,     // 5
    COL_OPEN,     // 6
    COL_OPEN,     // 7
    COL_NARROW,   // 8
    COL_OPEN,     // 9
    COL_OPEN,     // 10
    COL_ITEM,     // 11
    COL_OPEN,     // 12
    COL_OPEN,     // 13
    COL_PLATFORM, // 14
    COL_OPEN,     // 15
    COL_OPEN,     // 16
    COL_NARROW,   // 17
    COL_OPEN,     // 18
    COL_WALL,     // 19
};
#define ROOM_PATTERN_LEN 20

// Generate a column of tiles based on column type
static void gen_column(uint8_t col_type, uint8_t *tiles) {
    uint8_t i;

    // Default: empty
    for (i = 0; i < LEVEL_HEIGHT; i++) {
        tiles[i] = T_EMPTY;
    }

    // Top and bottom walls always present
    tiles[0] = T_WALL;
    tiles[1] = T_CEIL;
    tiles[LEVEL_HEIGHT - 2] = T_FLOOR;
    tiles[LEVEL_HEIGHT - 1] = T_WALL;

    switch (col_type) {
        case COL_WALL:
            for (i = 0; i < LEVEL_HEIGHT; i++) {
                tiles[i] = T_WALL;
            }
            break;

        case COL_PLATFORM:
            // Add middle platform
            tiles[6] = T_FLOOR;
            tiles[11] = T_FLOOR;
            break;

        case COL_NARROW:
            // Narrow gap in middle
            tiles[2] = T_WALL;
            tiles[3] = T_WALL;
            tiles[13] = T_WALL;
            tiles[14] = T_WALL;
            tiles[15] = T_WALL;
            break;

        case COL_ITEM:
            // Item in middle of open area
            tiles[8] = T_ITEM_HP;
            break;

        case COL_OPEN:
        default:
            // Already set up with floor/ceiling
            break;
    }
}

// Write a column of tiles + attributes to the hardware tilemap
static void write_column(uint8_t map_col, uint8_t *tiles) {
    uint8_t row;

    for (row = 0; row < LEVEL_HEIGHT; row++) {
        // Write tile
        set_bkg_tiles(map_col, row, 1, 1, &tiles[row]);
        // Write CGB palette attribute
        VBK_REG = 1;
        uint8_t pal = bg_tile_pal[tiles[row]];
        set_bkg_tiles(map_col, row, 1, 1, &pal);
        VBK_REG = 0;
    }
}

// Enemy spawn schedule: spawn based on world column
// Every 30 columns, spawn an enemy
#define SPAWN_INTERVAL 30
static uint16_t next_spawn_col;

// Spawn point Y positions (cycling)
static const uint8_t spawn_y[] = { 60, 40, 100, 80, 50, 90, 70 };
static uint8_t spawn_y_idx;
// Enemy types cycle
static const uint8_t spawn_types[] = {
    ENEMY_HORNET, ENEMY_HORNET, ENEMY_CROW,
    ENEMY_ORC, ENEMY_HORNET, ENEMY_CROW
};
static uint8_t spawn_type_idx;

void level_init(void) {
    uint8_t col;
    uint8_t tiles[LEVEL_HEIGHT];

    scroll_x = 0;
    scroll_col = 20; // Next column to load (after initial screen)
    scroll_speed = 1; // Auto-scroll at 1 px/frame
    next_spawn_col = SPAWN_INTERVAL;
    spawn_y_idx = 0;
    spawn_type_idx = 0;

    // Fill initial screen (20 visible columns)
    for (col = 0; col < 21; col++) {
        uint8_t pattern_idx = col % ROOM_PATTERN_LEN;
        gen_column(room_pattern[pattern_idx], tiles);
        write_column(col & 31, tiles);
    }
}

void level_load_tiles(void) {
    // Load BG tiles into VRAM bank 0
    set_bkg_data(0, 255, BG_TILES);
}

void level_update(void) {
    uint8_t tiles[LEVEL_HEIGHT];
    uint8_t old_pixel;
    uint8_t new_pixel;

    // Auto-scroll
    old_pixel = (uint8_t)(scroll_x & 0x07);
    scroll_x += scroll_speed;
    new_pixel = (uint8_t)(scroll_x & 0x07);

    // Update hardware scroll register
    SCX_REG = (uint8_t)(scroll_x & 0xFF);

    // When we cross a tile boundary, load the next column
    if (new_pixel < old_pixel) {
        // Crossed tile boundary — load new column
        uint8_t map_col = (uint8_t)((scroll_x >> 3) + 20) & 31;
        uint8_t pattern_idx = (uint8_t)(scroll_col % ROOM_PATTERN_LEN);
        gen_column(room_pattern[pattern_idx], tiles);
        write_column(map_col, tiles);
        scroll_col++;
    }
}

uint8_t level_get_tile(uint16_t col, uint8_t row) {
    uint8_t pattern_idx = (uint8_t)(col % ROOM_PATTERN_LEN);
    uint8_t tiles[LEVEL_HEIGHT];
    gen_column(room_pattern[pattern_idx], tiles);
    return tiles[row];
}

uint8_t level_is_solid(uint16_t world_x, uint8_t world_y) {
    uint16_t col = world_x >> 3;
    uint8_t row = world_y >> 3;
    uint8_t tile = level_get_tile(col, row);
    // Wall tiles are solid
    return (tile == T_WALL || tile == T_WALL2 || tile == T_BRICK);
}

void level_check_spawns(void) {
    uint16_t current_col = scroll_x >> 3;

    if (current_col >= next_spawn_col && enemy_count < MAX_ENEMIES) {
        uint8_t type = spawn_types[spawn_type_idx];
        uint8_t y = spawn_y[spawn_y_idx];

        enemy_spawn(type, FIX(168), FIX(y));

        spawn_y_idx = (spawn_y_idx + 1) % sizeof(spawn_y);
        spawn_type_idx = (spawn_type_idx + 1) % sizeof(spawn_types);
        next_spawn_col += SPAWN_INTERVAL;
    }
}
