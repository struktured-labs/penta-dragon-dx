#include "projectile.h"
#include "player.h"

#include "../assets/extracted/sprites/include/sprites_effects_projectiles.h"

Projectile projectiles[MAX_PROJECTILES];

#define PROJ_SPEED     4
#define PROJ_TTL       60

// Tile 0x00 is EMPTY, 0x01 is star, 0x03 is diamond
#define PROJ_PLAYER_TILE  (TILE_PROJECTILE + 1)
#define PROJ_ENEMY_TILE   (TILE_PROJECTILE + 3)

void projectile_init(void) {
    uint8_t i;
    for (i = 0; i < MAX_PROJECTILES; i++) {
        projectiles[i].active = 0;
    }
}

void projectile_load_tiles(void) {
    set_sprite_data(TILE_PROJECTILE, 4, SPRITE_EFFECTS_PROJECTILES);
}

void projectile_spawn_player(void) {
    uint8_t i;
    Projectile *p;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        p = &projectiles[i];
        if (p->active == 0) {
            p->x = player.x + 8; // Spawn ahead of player
            p->y = player.y + 4; // Center vertically
            p->dx = (player.dir == DIR_RIGHT) ? PROJ_SPEED : -PROJ_SPEED;
            p->dy = 0;
            p->active = 1;
            p->tile = PROJ_PLAYER_TILE;
            if (player.powerup > 0) {
                p->palette = 0;
            } else if (player.form == 0) {
                p->palette = 3; // Sara W (red)
            } else {
                p->palette = 1; // Sara D (green)
            }
            p->ttl = PROJ_TTL;
            return;
        }
    }
}

void projectile_spawn_enemy(uint8_t x, uint8_t y, int8_t dx, int8_t dy) {
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
            p->palette = 0; // Blue
            p->ttl = PROJ_TTL;
            return;
        }
    }
}

void projectile_update(void) {
    uint8_t i;
    Projectile *p;
    uint8_t new_x;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        p = &projectiles[i];
        if (p->active == 0) continue;

        // Move
        new_x = (uint8_t)((int16_t)p->x + p->dx);
        p->y = (uint8_t)((int16_t)p->y + p->dy);

        // Off-screen check (unsigned wrapping means > 168 catches both edges)
        if (new_x > 168 || p->y > 160) {
            p->active = 0;
            continue;
        }
        p->x = new_x;

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
            move_sprite(oam_idx, 0, 0);
            continue;
        }

        set_sprite_tile(oam_idx, p->tile);
        set_sprite_prop(oam_idx, p->palette & 0x07);
        move_sprite(oam_idx, p->x + OAM_X_OFS, p->y + OAM_Y_OFS);
    }
}

uint8_t projectile_check_hit(uint8_t tx, uint8_t ty, uint8_t w, uint8_t h) {
    uint8_t i;
    Projectile *p;

    for (i = 0; i < MAX_PROJECTILES; i++) {
        p = &projectiles[i];
        if (p->active != 1) continue;

        if (p->x >= tx && p->x < tx + w &&
            p->y >= ty && p->y < ty + h) {
            p->active = 0;
            return 1;
        }
    }
    return 0;
}
