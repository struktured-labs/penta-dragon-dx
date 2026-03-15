#ifndef __ENEMY_H__
#define __ENEMY_H__

#include "types.h"

// Enemy types (matching original tile ranges)
#define ENEMY_NONE      0
#define ENEMY_HORNET    1  // Tiles 0x40-0x4F, palette 4
#define ENEMY_CROW      2  // Tiles 0x30-0x3F, palette 3
#define ENEMY_ORC       3  // Tiles 0x50-0x5F, palette 5
#define ENEMY_HUMANOID  4  // Tiles 0x60-0x6F, palette 6
#define ENEMY_CATFISH   5  // Tiles 0x70-0x7F, palette 7

typedef struct {
    fixed_t x;
    fixed_t y;
    int8_t  dx;         // X velocity
    int8_t  dy;         // Y velocity
    uint8_t type;       // ENEMY_* constant
    uint8_t hp;         // Hit points
    uint8_t frame;      // Animation frame
    uint8_t anim_tick;  // Animation counter
    uint8_t shoot_cd;   // Shoot cooldown
    uint8_t tile_base;  // VRAM tile start for this enemy
    uint8_t palette;    // CGB palette number
    uint8_t ai_state;   // Simple AI state machine
    int16_t ai_timer;   // AI timer
} Enemy;

extern Enemy enemies[MAX_ENEMIES];
extern uint8_t enemy_count;

// Initialize enemy system
void enemy_init(void);

// Load enemy sprite tiles into VRAM
void enemy_load_tiles(void);

// Spawn an enemy at position
void enemy_spawn(uint8_t type, fixed_t x, fixed_t y);

// Update all enemies (AI, movement, shooting)
void enemy_update(void);

// Draw all enemies to OAM
void enemy_draw(void);

// Check player-enemy collision (returns damage or 0)
uint8_t enemy_check_player_hit(uint8_t px, uint8_t py);

#endif /* __ENEMY_H__ */
