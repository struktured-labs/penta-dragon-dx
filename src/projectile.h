#ifndef __PROJECTILE_H__
#define __PROJECTILE_H__

#include "types.h"

typedef struct {
    fixed_t x;
    fixed_t y;
    int8_t  dx;       // X velocity (pixels/frame, signed)
    int8_t  dy;       // Y velocity
    uint8_t active;   // 0=inactive, 1=player shot, 2=enemy shot
    uint8_t tile;     // VRAM tile index
    uint8_t palette;  // CGB palette
    uint8_t ttl;      // Time to live (frames)
} Projectile;

extern Projectile projectiles[MAX_PROJECTILES];

// Initialize projectile system
void projectile_init(void);

// Load projectile tiles into VRAM
void projectile_load_tiles(void);

// Spawn a projectile from player
void projectile_spawn_player(void);

// Spawn an enemy projectile
void projectile_spawn_enemy(fixed_t x, fixed_t y, int8_t dx, int8_t dy);

// Update all active projectiles
void projectile_update(void);

// Draw all active projectiles to OAM
void projectile_draw(void);

// Check if any player projectile hits a point (returns 1 and deactivates)
uint8_t projectile_check_hit(uint8_t tx, uint8_t ty, uint8_t w, uint8_t h);

#endif /* __PROJECTILE_H__ */
