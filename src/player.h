#ifndef __PLAYER_H__
#define __PLAYER_H__

#include "types.h"

typedef struct {
    uint8_t x;         // Screen X (pixels)
    uint8_t y;         // Screen Y (pixels)
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

void player_init(void);
void player_load_tiles(void);
void player_update(uint8_t keys, uint8_t prev_keys);
void player_draw(void);

#endif /* __PLAYER_H__ */
