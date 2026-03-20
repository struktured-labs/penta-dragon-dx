#include "level.h"
#include "enemy.h"
#include "player.h"
#include "gamestate.h"
#include "palettes.h"
#include "itemmenu.h"
#include "sound.h"

// BG tiles + level data in ROM bank 2
#include "data_bank2.h"

uint16_t scroll_x;
uint8_t  scroll_y;
uint8_t  scroll_col;
uint8_t  auto_scroll;
static uint8_t scroll_tick; // Counts frames for quantized 4px/4frame scroll

// ============================================
// Item collection tracking
// ============================================
// Track collected items by their level column + row.
// Uses a circular buffer of recently collected positions
// to prevent re-collecting the same item on level wrap.
#define MAX_COLLECTED_ITEMS 32
static uint16_t collected_cols[MAX_COLLECTED_ITEMS];
static uint8_t  collected_rows[MAX_COLLECTED_ITEMS];
static uint8_t  collected_count;

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

// Level data still in bank 1 (static const in header)
#include "level_data.h"

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

    scroll_x = 0;  // SCX starts at 0; gamestate sets room SCX after delay
    scroll_y = 0;
    scroll_col = 21;
    scroll_tick = 0;
    auto_scroll = 0;
    next_spawn_col = 5;
    spawn_y_idx = 0;
    spawn_type_idx = 0;
    collected_count = 0;

    // Don't set SCX here — gamestate handles room-based SCX with delay
    SCY_REG = scroll_y;

    // Fill initial visible area (21 columns from the level data)
    for (col = 0; col < 21; col++) {
        get_level_column(tiles, col);
        write_column(col & 31, tiles);
    }
}

// Banked tile loader in data_bank2.c — __banked handles bank switching
extern void load_bg_tiles_banked(void) __banked;

void level_load_tiles(void) {
    load_bg_tiles_banked();
}

int8_t level_update(uint8_t keys) {
    // OG: SCX set by room system (not D-pad). SCY controlled by UP/DOWN.
    // Verified: OG SCY cycles through {0, 4, 8, 12} with D-pad (60-sec comparison)
    static uint8_t scy_tick = 0;

    if (keys & J_DOWN) {
        scy_tick++;
        if (scy_tick >= 10) {
            scy_tick = 0;
            if (scroll_y < 12) scroll_y += 4;
        }
    } else if (keys & J_UP) {
        scy_tick++;
        if (scy_tick >= 10) {
            scy_tick = 0;
            if (scroll_y >= 4) scroll_y -= 4;
        }
    } else {
        scy_tick = 0;
    }
    SCY_REG = scroll_y;
    return 0;
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

// ============================================
// Item pickup
// ============================================

// Check if an item at (data_col, row) was already collected
static uint8_t is_item_collected(uint16_t data_col, uint8_t row) {
    uint8_t i;
    for (i = 0; i < collected_count; i++) {
        if (collected_cols[i] == data_col && collected_rows[i] == row) {
            return 1;
        }
    }
    return 0;
}

// Mark an item at (data_col, row) as collected
static void mark_item_collected(uint16_t data_col, uint8_t row) {
    if (collected_count < MAX_COLLECTED_ITEMS) {
        collected_cols[collected_count] = data_col;
        collected_rows[collected_count] = row;
        collected_count++;
    } else {
        // Circular: overwrite oldest entry
        uint8_t idx = collected_count % MAX_COLLECTED_ITEMS;
        collected_cols[idx] = data_col;
        collected_rows[idx] = row;
        collected_count++;
    }
}

// Powerup types (direct application, not inventory items)
#define POWERUP_SPIRAL   0x81   // Returned as pseudo-item for special handling
#define POWERUP_TURBO    0x82

// Map item tile ID to inventory item type (or powerup pseudo-type)
static uint8_t tile_to_item_type(uint8_t tile) {
    // Item tiles come in 2x2 groups:
    //   0x88/0x89 + 0x98/0x99: Flash bomb (first item pair)
    //   0x8A/0x8B + 0x9A/0x9B: Potion
    //   0x8C/0x8D + 0x9C/0x9D: Shield
    //   0x8E/0x8F: Spiral powerup
    //   0x90/0x91: Turbo powerup
    //   0x92-0x97: Extra flash bombs / potions
    if (tile >= 0x88 && tile <= 0x89) return ITEM_FLASH_BOMB;
    if (tile >= 0x98 && tile <= 0x99) return ITEM_FLASH_BOMB;
    if (tile >= 0x8A && tile <= 0x8B) return ITEM_POTION;
    if (tile >= 0x9A && tile <= 0x9B) return ITEM_POTION;
    if (tile >= 0x8C && tile <= 0x8D) return ITEM_SHIELD;
    if (tile >= 0x9C && tile <= 0x9D) return ITEM_SHIELD;
    if (tile >= 0x8E && tile <= 0x8F) return POWERUP_SPIRAL;
    if (tile >= 0x90 && tile <= 0x91) return POWERUP_TURBO;
    if (tile >= 0x92 && tile <= 0x97) return ITEM_FLASH_BOMB;
    return ITEM_FLASH_BOMB; // Default
}

// Replace an item tile with floor in the hardware tilemap
static void clear_item_hw(uint16_t world_col, uint8_t row) {
    uint8_t map_col;
    uint8_t floor_tile;
    uint8_t floor_pal;

    map_col = (uint8_t)(world_col & 31);
    // Checkerboard floor: alternate based on row + col parity
    floor_tile = ((world_col + row) & 1) ? 0x02 : 0x01;
    floor_pal = bg_tile_pal[floor_tile];

    // Write floor tile to hardware tilemap
    set_bkg_tiles(map_col, row, 1, 1, &floor_tile);
    // Write palette attribute
    VBK_REG = 1;
    set_bkg_tiles(map_col, row, 1, 1, &floor_pal);
    VBK_REG = 0;
}

void level_check_item_pickup(void) {
    uint16_t world_x;
    uint8_t  world_y;
    uint16_t tile_col;
    uint8_t  tile_row;
    uint8_t  tile;
    uint16_t data_col;
    uint8_t  item_type;
    uint8_t  dx, dy;

    // Sara's world position (she's fixed on screen, world scrolls)
    // Sara screen: (72, 64), size 16x16
    // Check the 2x2 tile area under Sara's center
    world_x = scroll_x + player.x;
    world_y = scroll_y + player.y;

    // Check a 2x2 tile area (Sara is 16x16 = 2x2 tiles)
    for (dy = 0; dy < 2; dy++) {
        for (dx = 0; dx < 2; dx++) {
            tile_col = (world_x + dx * 8) >> 3;
            tile_row = (world_y + dy * 8) >> 3;

            if (tile_row >= LEVEL_HEIGHT) continue;

            tile = level_get_tile(tile_col, tile_row);

            // Check if it's an item tile (0x88-0x9D)
            if (tile >= 0x88 && tile <= 0x9D) {
                data_col = tile_col % LEVEL1_NUM_COLUMNS;

                // Skip if already collected
                if (is_item_collected(data_col, tile_row)) continue;

                // Determine item type from tile
                item_type = tile_to_item_type(tile);

                // Apply powerups directly or add to inventory
                if (item_type == POWERUP_SPIRAL) {
                    player.powerup = 1;
                    sound_pickup();
                } else if (item_type == POWERUP_TURBO) {
                    player.powerup = 3;
                    sound_pickup();
                } else {
                    itemmenu_add_item(item_type);
                }

                // Mark as collected
                mark_item_collected(data_col, tile_row);

                // Clear all tiles in the 2x2 item group from hardware tilemap
                // Items are placed in 2x2 groups (top-left=0x88, top-right=0x89,
                // bottom-left=0x98, bottom-right=0x99, etc.)
                // Clear this tile and try to clear neighboring item tiles
                clear_item_hw(tile_col, tile_row);

                // Check and clear adjacent item tiles in the 2x2 group
                if (tile_row > 0) {
                    uint8_t above = level_get_tile(tile_col, tile_row - 1);
                    if (above >= 0x88 && above <= 0x9D) {
                        if (!is_item_collected(tile_col % LEVEL1_NUM_COLUMNS, tile_row - 1)) {
                            mark_item_collected(tile_col % LEVEL1_NUM_COLUMNS, tile_row - 1);
                            clear_item_hw(tile_col, tile_row - 1);
                        }
                    }
                }
                if (tile_row + 1 < LEVEL_HEIGHT) {
                    uint8_t below = level_get_tile(tile_col, tile_row + 1);
                    if (below >= 0x88 && below <= 0x9D) {
                        if (!is_item_collected(tile_col % LEVEL1_NUM_COLUMNS, tile_row + 1)) {
                            mark_item_collected(tile_col % LEVEL1_NUM_COLUMNS, tile_row + 1);
                            clear_item_hw(tile_col, tile_row + 1);
                        }
                    }
                }
                {
                    uint16_t adj_col = tile_col + 1;
                    uint8_t adj_tile = level_get_tile(adj_col, tile_row);
                    if (adj_tile >= 0x88 && adj_tile <= 0x9D) {
                        if (!is_item_collected(adj_col % LEVEL1_NUM_COLUMNS, tile_row)) {
                            mark_item_collected(adj_col % LEVEL1_NUM_COLUMNS, tile_row);
                            clear_item_hw(adj_col, tile_row);
                        }
                    }
                }
                if (tile_col > 0) {
                    uint16_t adj_col = tile_col - 1;
                    uint8_t adj_tile = level_get_tile(adj_col, tile_row);
                    if (adj_tile >= 0x88 && adj_tile <= 0x9D) {
                        if (!is_item_collected(adj_col % LEVEL1_NUM_COLUMNS, tile_row)) {
                            mark_item_collected(adj_col % LEVEL1_NUM_COLUMNS, tile_row);
                            clear_item_hw(adj_col, tile_row);
                        }
                    }
                }

                // Sound is played by itemmenu_add_item
                return; // One pickup per frame
            }
        }
    }
}
