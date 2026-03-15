#ifndef __PLAYER_H__
#define __PLAYER_H__

#include "types.h"

// Player state
typedef struct {
    fixed_t x;         // Screen X (8.8 fixed point)
    fixed_t y;         // Screen Y (8.8 fixed point)
    uint8_t form;      // 0=Witch, 1=Dragon
    uint8_t dir;       // DIR_RIGHT or DIR_LEFT
    uint8_t frame;     // Animation frame (0-3)
    uint8_t anim_tick; // Animation counter
    uint8_t shoot_cd;  // Shoot cooldown (frames)
    uint8_t powerup;   // 0=none, 1=spiral, 2=shield, 3=turbo
    uint8_t hp;        // Health points
    uint8_t invuln;    // Invulnerability frames after hit
} Player;

extern Player player;

// Initialize player at starting position
void player_init(void);

// Load player sprite tiles into VRAM
void player_load_tiles(void);

// Process input and update player state
void player_update(uint8_t keys, uint8_t prev_keys);

// Draw player sprites to OAM
void player_draw(void);

// Get player's palette based on form
uint8_t player_get_palette(void);

#endif /* __PLAYER_H__ */
