#ifndef __LEVEL_H__
#define __LEVEL_H__

#include "types.h"

// Level map dimensions (wider than screen for scrolling)
// 256 tiles wide x 18 tiles tall = 4608 bytes
// But that's too much RAM. Use column-based streaming instead.
// Store level as a compressed column map.

// For now: procedural dungeon generation with repeating patterns
// Level 1 has 7 "rooms" each ~40 tiles wide = 280 tiles total

#define LEVEL_HEIGHT    18  // Visible tile rows
#define LEVEL_MAP_W     32  // Hardware tilemap width (wrapping)
#define LEVEL_MAP_H     32  // Hardware tilemap height

// Scroll state
extern uint16_t scroll_x;       // World scroll position (pixels)
extern uint8_t  scroll_y;       // Vertical scroll position (pixels, written to SCY)
extern uint8_t  scroll_col;     // Next column to load (world units)
extern uint8_t  auto_scroll;    // 0=player-driven, non-zero=auto-scroll speed

// Vertical scroll limits
#define SCROLL_Y_MAX    24      // Maximum downward scroll

// Initialize level (load initial screen)
void level_init(void);

// Load BG tiles into VRAM
void level_load_tiles(void);

// Update scrolling — pass D-pad state directly
// Original scrolls BG when player presses LEFT/RIGHT (Sara stays fixed)
// Returns pixels scrolled this frame (positive = right)
int8_t level_update(uint8_t keys);

// Get a tile from the level map at world column, row
uint8_t level_get_tile(uint16_t col, uint8_t row);

// Check if a world position is solid (for collision)
uint8_t level_is_solid(uint16_t world_x, uint8_t world_y);

// Spawn enemies based on scroll position
void level_check_spawns(void);

#endif /* __LEVEL_H__ */
