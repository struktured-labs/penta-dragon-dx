#include "level.h"
#include "enemy.h"
#include "palettes.h"

// Use the GAMEPLAY tiles (extracted from VRAM during actual gameplay)
// NOT the static ROM tiles (which are font/text characters)
#include "../assets/extracted/bg/include/bg_gameplay.h"

uint16_t scroll_x;
uint8_t  scroll_col;
uint8_t  scroll_speed;

// BG tile palette lookup — matches the DX colorizer categories
// But now using GAMEPLAY tile meanings:
//   0x00-0x06: Floor tiles (diamond checkerboard) → Palette 0
//   0x07-0x0E: Wall edge/transition → Palette 6
//   0x13-0x1E: Pillar/column components → Palette 6
//   0x20-0x39: Platform/ledge/staircase → Palette 6
//   0x3E-0x3F: Torch fixtures → Palette 5 (fire)
//   0x40-0x57: Wall structure → Palette 6
//   0x62-0x7E: Extended architecture → Palette 6
//   0xA0-0xBB: Items → Palette 1 (gold)
//   0xC0-0xFC: HUD elements → Palette 0
//   0xFE: Void → Palette 7 (dark)

static const uint8_t bg_tile_pal[256] = {
    // 0x00-0x0F: Floor (0x00-0x06) then wall edges (0x07-0x0E) then floor (0x0F)
    0,0,0,0,0,0,0, 6,6,6,6,6,6,6,6, 0,
    // 0x10-0x1F: Misc then pillars (0x13-0x1E)
    0,0,0, 6,6,6,6,6,6,6,6,6,6,6,6, 0,
    // 0x20-0x2F: Platform/staircase components → Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x30-0x3F: More platform/staircase, then torches
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6, 5,5,
    // 0x40-0x4F: Wall tops → Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x50-0x5F: Wall bottoms → Palette 6
    6,6,6,6,6,6,6,6, 6,6,6,6,6,6,6,6,
    // 0x60-0x6F: Extended arches → Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0x70-0x7F: More architecture → Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0x80-0x8F: (signed addr area) → Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0x90-0x9F: → Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0xA0-0xAF: Items → Palette 1 (gold)
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    // 0xB0-0xBF: Items → Palette 1
    1,1,1,1,1,1,1,1, 1,1,1,1,1,1,1,1,
    // 0xC0-0xCF: HUD / items
    0,0,0,0,0,0,0,0, 0,0,0,0,1,1,1,1,
    // 0xD0-0xDF: HUD / items
    0,0,0,0,0,0,0,0, 0,0,0,0,1,1,1,1,
    // 0xE0-0xEF: → Palette 0
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
    // 0xF0-0xFF: HUD, then void
    0,0,0,0,0,0,0,0, 0,0,0,0,0,0, 7,7,
};

// ============================================
// Gameplay tile definitions (actual VRAM tiles)
// ============================================

// Floor tiles (diamond checkerboard pattern)
#define T_EMPTY    0x00
#define T_FLOOR_A  0x01  // Light floor tile A
#define T_FLOOR_B  0x02  // Light floor tile B (alternates with A)
#define T_FLOOR_C  0x03  // Dark floor tile A
#define T_FLOOR_D  0x04  // Dark floor tile B
#define T_FLOOR_E  0x05  // Floor edge/transition
#define T_FLOOR_F  0x06  // Floor edge variant

// Wall structure tiles
#define T_WALL_TL  0x40  // Wall top-left corner
#define T_WALL_TC  0x41  // Wall top center
#define T_WALL_TR  0x42  // Wall top right
#define T_WALL_TX  0x43  // Wall top extension
#define T_WALL_MC  0x44  // Wall mid-left
#define T_WALL_ML  0x45  // Wall mid center
#define T_WALL_MR  0x46  // Wall mid right
#define T_WALL_MX  0x47  // Wall mid extension
#define T_WALL_BL  0x50  // Wall bottom-left
#define T_WALL_BC  0x51  // Wall bottom center
#define T_WALL_BR  0x52  // Wall bottom right
#define T_WALL_BX  0x53  // Wall bottom extension
#define T_WALL_EL  0x54  // Wall edge left
#define T_WALL_EC  0x55  // Wall edge center
#define T_WALL_ER  0x56  // Wall edge right
#define T_WALL_EX  0x57  // Wall edge extension

// Pillar tiles
#define T_PIL_TL   0x13  // Pillar top left
#define T_PIL_TC   0x14  // Pillar top center (solid)
#define T_PIL_TR   0x15  // Pillar top right
#define T_PIL_BL   0x16  // Pillar body left
#define T_PIL_BR   0x17  // Pillar body right
#define T_PIL_XL   0x1E  // Pillar inner corner

// Platform/staircase tiles
#define T_PLAT_TL  0x20  // Platform top-left
#define T_PLAT_TC  0x21  // Platform top center
#define T_PLAT_TR  0x22  // Platform top right
#define T_PLAT_TX  0x23  // Platform top ext
#define T_PLAT_ML  0x24  // Platform mid-left (brick)
#define T_PLAT_MC  0x25  // Platform mid-center (brick)
#define T_PLAT_BL  0x26  // Platform bottom-left
#define T_PLAT_BC  0x27  // Platform bottom center
#define T_PLAT_RL  0x28  // Platform right-left corner
#define T_PLAT_RC  0x29  // Platform right center
#define T_PLAT_EL  0x30  // Platform edge left
#define T_PLAT_EC  0x31  // Platform edge center
#define T_PLAT_FL  0x34  // Platform fill left
#define T_PLAT_FR  0x37  // Platform fill right
#define T_PLAT_XL  0x38  // Platform extra left

// Items (2x2 tile blocks)
#define T_ITEM_TL  0xA0  // Item top-left
#define T_ITEM_TR  0xA1  // Item top-right
#define T_ITEM_BL  0xB0  // Item bottom-left
#define T_ITEM_BR  0xB1  // Item bottom-right

// Void
#define T_VOID     0xFE  // Solid dark void

// ============================================
// Level data: column-based dungeon generation
// ============================================

// Each column is 18 tiles (LEVEL_HEIGHT). We define column templates
// that recreate the original dungeon patterns.

// Column type enum
#define COL_FLOOR      0  // Open floor with checkerboard
#define COL_WALL_L     1  // Wall column (left side pattern)
#define COL_WALL_R     2  // Wall column (right side)
#define COL_STAIR_TOP  3  // Staircase start (top of step)
#define COL_STAIR_MID  4  // Staircase middle
#define COL_STAIR_BOT  5  // Staircase bottom
#define COL_PILLAR     6  // Pillar column
#define COL_ITEM       7  // Floor with item
#define COL_VOID       8  // Mostly void (edge of map)

// Generate a column of tiles based on type
static void gen_column(uint8_t col_type, uint8_t *tiles, uint8_t col_idx) {
    uint8_t i;
    uint8_t parity = col_idx & 1; // For checkerboard alternation

    // Default: fill with checkerboard floor
    for (i = 0; i < LEVEL_HEIGHT; i++) {
        if ((i & 1) == parity) {
            tiles[i] = T_FLOOR_A;
        } else {
            tiles[i] = T_FLOOR_B;
        }
    }

    switch (col_type) {
        case COL_FLOOR:
            // Pure checkerboard floor — already done
            break;

        case COL_WALL_L:
            // Left wall column (from tilemap: 45 46 / 55 56 / 42 41 / 52 51)
            tiles[0]  = T_WALL_ML;
            tiles[1]  = T_WALL_EC;
            tiles[2]  = T_WALL_TR;
            tiles[3]  = T_WALL_BR;
            // Lower wall
            tiles[14] = T_PLAT_TR;
            tiles[15] = T_PLAT_EL;
            tiles[16] = T_PLAT_BL;
            tiles[17] = T_PLAT_EL;
            break;

        case COL_WALL_R:
            // Right wall column
            tiles[0]  = T_WALL_MR;
            tiles[1]  = T_WALL_ER;
            tiles[2]  = T_WALL_TR;
            tiles[3]  = T_WALL_BR;
            tiles[14] = T_PLAT_TR;
            tiles[15] = T_PLAT_EC;
            tiles[16] = T_PLAT_BL;
            tiles[17] = T_PLAT_EC;
            break;

        case COL_STAIR_TOP:
            // Staircase top: floor transitions to step
            // Upper portion stays floor
            // Lower: step with platform tiles
            tiles[10] = T_FLOOR_E;
            tiles[11] = T_FLOOR_E;
            tiles[12] = T_PLAT_TL;
            tiles[13] = T_PLAT_EL;
            tiles[14] = T_PLAT_ML;
            tiles[15] = T_PLAT_EL;
            tiles[16] = T_PLAT_BL;
            tiles[17] = T_PLAT_EL;
            break;

        case COL_STAIR_MID:
            // Staircase middle: pillar + void below
            tiles[10] = T_PLAT_TC;
            tiles[11] = T_PLAT_EC;
            tiles[12] = T_PIL_TC;
            tiles[13] = T_PIL_BL;
            tiles[14] = T_PIL_BL;
            tiles[15] = T_VOID;
            tiles[16] = T_VOID;
            tiles[17] = T_VOID;
            break;

        case COL_STAIR_BOT:
            // Staircase: deep void
            tiles[8]  = T_FLOOR_E;
            tiles[9]  = T_FLOOR_C;
            tiles[10] = T_PLAT_TC;
            tiles[11] = T_PLAT_EC;
            tiles[12] = T_PIL_TC;
            tiles[13] = T_PIL_BL;
            tiles[14] = T_PIL_BL;
            tiles[15] = T_VOID;
            tiles[16] = T_VOID;
            tiles[17] = T_VOID;
            break;

        case COL_PILLAR:
            // Freestanding pillar in middle of room
            tiles[5]  = T_PIL_TL;
            tiles[6]  = T_PIL_TC;
            tiles[7]  = T_PIL_TR;
            tiles[12] = T_PIL_TL;
            tiles[13] = T_PIL_TC;
            tiles[14] = T_PIL_TR;
            break;

        case COL_ITEM:
            // Floor with item in middle (2x2 item block)
            tiles[7]  = T_ITEM_TL;
            tiles[8]  = T_ITEM_BL;
            break;

        case COL_VOID:
            // Edge of dungeon, mostly void
            for (i = 8; i < LEVEL_HEIGHT; i++) {
                tiles[i] = T_VOID;
            }
            break;
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

// Room pattern: 24-column repeating dungeon section
// Recreates the descending staircase dungeon from the original game
static const uint8_t room_pattern[] = {
    COL_WALL_L,     // 0: Wall
    COL_FLOOR,      // 1: Open floor
    COL_FLOOR,      // 2: Open floor
    COL_FLOOR,      // 3: Open floor
    COL_FLOOR,      // 4: Open floor
    COL_PILLAR,     // 5: Pillar
    COL_FLOOR,      // 6: Open floor
    COL_ITEM,       // 7: Item pickup
    COL_FLOOR,      // 8: Open floor
    COL_FLOOR,      // 9: Open floor
    COL_FLOOR,      // 10: Open floor
    COL_FLOOR,      // 11: Open floor
    COL_FLOOR,      // 12: Open floor
    COL_FLOOR,      // 13: Open floor
    COL_STAIR_TOP,  // 14: Staircase begins
    COL_STAIR_MID,  // 15: Staircase middle
    COL_STAIR_BOT,  // 16: Staircase deep
    COL_VOID,       // 17: Void edge
    COL_FLOOR,      // 18: New floor level
    COL_FLOOR,      // 19: Open floor
    COL_FLOOR,      // 20: Open floor
    COL_PILLAR,     // 21: Pillar
    COL_FLOOR,      // 22: Open floor
    COL_WALL_R,     // 23: Wall
};
#define ROOM_PATTERN_LEN 24

// Enemy spawn schedule — first enemy at column 8 (~64 frames), then every 12
#define SPAWN_INTERVAL 12
static uint16_t next_spawn_col;
static const uint8_t spawn_y[] = { 56, 40, 88, 72, 48, 80, 64 };
static uint8_t spawn_y_idx;
static const uint8_t spawn_types[] = {
    ENEMY_HORNET, ENEMY_CROW, ENEMY_HORNET,
    ENEMY_ORC, ENEMY_HORNET, ENEMY_CROW
};
static uint8_t spawn_type_idx;

void level_init(void) {
    uint8_t col;
    uint8_t tiles[LEVEL_HEIGHT];

    scroll_x = 0;
    scroll_col = 21;
    scroll_speed = 1;
    next_spawn_col = 8; // First enemy spawns early
    spawn_y_idx = 0;
    spawn_type_idx = 0;

    // Fill initial visible area (21 columns for safety)
    for (col = 0; col < 21; col++) {
        uint8_t pattern_idx = col % ROOM_PATTERN_LEN;
        gen_column(room_pattern[pattern_idx], tiles, col);
        write_column(col & 31, tiles);
    }
}

void level_load_tiles(void) {
    // Load the GAMEPLAY BG tiles (extracted from VRAM during actual gameplay)
    set_bkg_data(0, 255, BG_GAMEPLAY_TILES);
}

void level_update(void) {
    uint8_t tiles[LEVEL_HEIGHT];
    uint8_t old_pixel;
    uint8_t new_pixel;

    old_pixel = (uint8_t)(scroll_x & 0x07);
    scroll_x += scroll_speed;
    new_pixel = (uint8_t)(scroll_x & 0x07);

    SCX_REG = (uint8_t)(scroll_x & 0xFF);

    // Load next column when crossing tile boundary
    if (new_pixel < old_pixel) {
        uint8_t map_col = (uint8_t)((scroll_x >> 3) + 20) & 31;
        uint8_t pattern_idx = (uint8_t)(scroll_col % ROOM_PATTERN_LEN);
        gen_column(room_pattern[pattern_idx], tiles, scroll_col);
        write_column(map_col, tiles);
        scroll_col++;
    }
}

uint8_t level_get_tile(uint16_t col, uint8_t row) {
    uint8_t pattern_idx = (uint8_t)(col % ROOM_PATTERN_LEN);
    uint8_t tiles[LEVEL_HEIGHT];
    gen_column(room_pattern[pattern_idx], tiles, (uint8_t)col);
    return tiles[row];
}

uint8_t level_is_solid(uint16_t world_x, uint8_t world_y) {
    uint16_t col = world_x >> 3;
    uint8_t row = world_y >> 3;
    uint8_t tile = level_get_tile(col, row);
    // Wall/pillar/platform tiles are solid, void is passthrough
    return (tile >= T_WALL_TL && tile <= T_WALL_EX) ||
           (tile >= T_PIL_TL && tile <= T_PIL_XL) ||
           (tile >= T_PLAT_TL && tile <= T_PLAT_XL);
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
