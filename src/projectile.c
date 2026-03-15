#include "projectile.h"
#include "player.h"

#include "../assets/extracted/sprites/include/sprites_effects_projectiles.h"

Projectile projectiles[MAX_PROJECTILES];

#define PROJ_SPEED     4
#define PROJ_TTL       60  // ~1 second

// Projectile tiles: use tile 0x01 area from extracted data
// The original uses tiles 0x00-0x0F for projectiles/effects
#define PROJ_PLAYER_TILE  TILE_PROJECTILE
#define PROJ_ENEMY_TILE   (TILE_PROJECTILE + 2)

void projectile_init(void) {
    uint8_t i;
    for (i = 0; i < MAX_PROJECTILES; i++) {
        projectiles[i].active = 0;
    }
}

void projectile_load_tiles(void) {
    // Load first 4 tiles from effects/projectiles for projectile graphics
    // These map to original tiles 0x00-0x03
    set_sprite_data(TILE_PROJECTILE, 4, SPRITE_EFFECTS_PROJECTILES);
}

void projectile_spawn_player(void) {
    uint8_t i;
    Projectile *p;
    int8_t dx;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        p = &projectiles[i];
        if (p->active == 0) {
            p->x = player.x;
            p->y = player.y;
            dx = (player.dir == DIR_RIGHT) ? PROJ_SPEED : -PROJ_SPEED;
            p->dx = dx;
            p->dy = 0;
            p->active = 1;
            p->tile = PROJ_PLAYER_TILE;
            // Palette based on form and powerup
            if (player.powerup > 0) {
                p->palette = 0; // Powerup palette (dynamically loaded)
            } else if (player.form == 0) {
                p->palette = 3; // Sara W projectile (red)
            } else {
                p->palette = 1; // Sara D projectile (green)
            }
            p->ttl = PROJ_TTL;
            return;
        }
    }
}

void projectile_spawn_enemy(fixed_t x, fixed_t y, int8_t dx, int8_t dy) {
    uint8_t i;
    Projectile *p;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        p = &projectiles[i];
        if (p->active == 0) {
            p->x = x;
            p->y = y;
            p->dx = dx;
            p->dy = dy;
            p->active = 2;
            p->tile = PROJ_ENEMY_TILE;
            p->palette = 0; // Enemy projectile palette (blue)
            p->ttl = PROJ_TTL;
            return;
        }
    }
}

void projectile_update(void) {
    uint8_t i;
    Projectile *p;
    int16_t sx, sy;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        p = &projectiles[i];
        if (p->active == 0) continue;

        p->x += FIX(p->dx);
        p->y += FIX(p->dy);

        // Remove if off-screen or expired
        sx = (int16_t)(p->x >> 8);
        sy = (int16_t)(p->y >> 8);
        if (sx < -8 || sx > 168 || sy < -8 || sy > 160) {
            p->active = 0;
            continue;
        }
        p->ttl--;
        if (p->ttl == 0) {
            p->active = 0;
        }
    }
}

void projectile_draw(void) {
    uint8_t i;
    uint8_t oam_idx;
    Projectile *p;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        oam_idx = OAM_PROJECTILES + i;
        p = &projectiles[i];

        if (p->active == 0) {
            // Hide sprite
            move_sprite(oam_idx, 0, 0);
            continue;
        }

        set_sprite_tile(oam_idx, p->tile);
        set_sprite_prop(oam_idx, p->palette & 0x07);
        move_sprite(oam_idx,
                    (uint8_t)(UNFIX(p->x) + OAM_X_OFS),
                    (uint8_t)(UNFIX(p->y) + OAM_Y_OFS));
    }
}

uint8_t projectile_check_hit(uint8_t tx, uint8_t ty, uint8_t w, uint8_t h) {
    uint8_t i;
    Projectile *p;
    int16_t px, py;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        p = &projectiles[i];
        if (p->active != 1) continue; // Only player shots

        px = (int16_t)(p->x >> 8);
        py = (int16_t)(p->y >> 8);

        // Simple AABB collision
        if (px >= (int16_t)tx && px < (int16_t)(tx + w) &&
            py >= (int16_t)ty && py < (int16_t)(ty + h)) {
            p->active = 0; // Consume projectile
            return 1;
        }
    }
    return 0;
}
