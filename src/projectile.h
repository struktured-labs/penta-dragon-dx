#ifndef __PROJECTILE_H__
#define __PROJECTILE_H__

#include "types.h"

typedef struct {
    uint8_t x;
    uint8_t y;
    int8_t  dx;       // X velocity (pixels/frame, signed)
    int8_t  dy;       // Y velocity
    uint8_t active;   // 0=inactive, 1=player shot, 2=enemy shot
    uint8_t tile;     // VRAM tile index
    uint8_t palette;  // CGB palette
    uint8_t ttl;      // Time to live (frames)
} Projectile;

extern Projectile projectiles[MAX_PROJECTILES];

#define PROJ_SPEED  4

void projectile_init(void);
void projectile_load_tiles(void);
void projectile_spawn_player(void);
void projectile_spawn_player_dir(int8_t dx, int8_t dy);
void projectile_spawn_enemy(uint8_t x, uint8_t y, int8_t dx, int8_t dy);
void projectile_update(void);
void projectile_draw(void);
uint8_t projectile_check_hit(uint8_t tx, uint8_t ty, uint8_t w, uint8_t h);

#endif /* __PROJECTILE_H__ */
