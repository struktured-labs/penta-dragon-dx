#include "enemy.h"
#include "projectile.h"
#include "player.h"

#include "../assets/extracted/sprites/include/sprites_hornets.h"
#include "../assets/extracted/sprites/include/sprites_crows.h"
#include "../assets/extracted/sprites/include/sprites_orcs.h"

Enemy enemies[MAX_ENEMIES];
uint8_t enemy_count;

#define ENEMY_ANIM_SPEED 16
#define ENEMY_SHOOT_CD   90  // ~1.5 seconds

// Enemy config table
static const uint8_t enemy_hp[]      = { 0, 2, 2, 3, 3, 4 };
static const uint8_t enemy_palette[] = { 0, 4, 3, 5, 6, 7 };

void enemy_init(void) {
    uint8_t i;
    for (i = 0; i < MAX_ENEMIES; i++) {
        enemies[i].type = ENEMY_NONE;
    }
    enemy_count = 0;
}

void enemy_load_tiles(void) {
    set_sprite_data(TILE_HORNET, SPRITE_HORNETS_TILE_COUNT, SPRITE_HORNETS);
    set_sprite_data(TILE_CROW, SPRITE_CROWS_TILE_COUNT, SPRITE_CROWS);
    set_sprite_data(TILE_ORC, SPRITE_ORCS_TILE_COUNT, SPRITE_ORCS);
}

void enemy_spawn(uint8_t type, fixed_t x, fixed_t y) {
    uint8_t i;
    Enemy *e;

    for (i = 0; i < MAX_ENEMIES; i++) {
        e = &enemies[i];
        if (e->type == ENEMY_NONE) {
            e->type = type;
            e->x = x;
            e->y = y;
            e->hp = enemy_hp[type];
            e->palette = enemy_palette[type];
            e->frame = 0;
            e->anim_tick = 0;
            e->shoot_cd = ENEMY_SHOOT_CD / 2; // Stagger initial shot
            e->ai_state = 0;
            e->ai_timer = 0;

            // Set tile base and default velocity based on type
            switch (type) {
                case ENEMY_HORNET:
                    e->tile_base = TILE_HORNET;
                    e->dx = -1;
                    e->dy = 0;
                    break;
                case ENEMY_CROW:
                    e->tile_base = TILE_CROW;
                    e->dx = -2;
                    e->dy = 0;
                    break;
                case ENEMY_ORC:
                    e->tile_base = TILE_ORC;
                    e->dx = -1;
                    e->dy = 0;
                    break;
                default:
                    e->tile_base = TILE_HORNET;
                    e->dx = -1;
                    e->dy = 0;
                    break;
            }

            enemy_count++;
            return;
        }
    }
}

static void enemy_ai_hornet(Enemy *e) {
    // Hornets: sine-wave pattern (up/down while moving left)
    e->ai_timer++;
    if (e->ai_timer >= 30) {
        e->ai_timer = 0;
        e->dy = -e->dy;
        if (e->dy == 0) e->dy = 1;
    }
}

static void enemy_ai_crow(Enemy *e) {
    // Crows: fast diagonal swoop toward player
    if (e->ai_state == 0) {
        // Phase 1: fly left
        e->ai_timer++;
        if (e->ai_timer >= 40) {
            e->ai_state = 1;
            e->ai_timer = 0;
            // Dive toward player Y
            if (UNFIX(player.y) > UNFIX(e->y)) {
                e->dy = 2;
            } else {
                e->dy = -2;
            }
        }
    } else {
        // Phase 2: continue diagonal
        e->ai_timer++;
        if (e->ai_timer >= 30) {
            e->ai_state = 0;
            e->ai_timer = 0;
            e->dy = 0;
        }
    }
}

static void enemy_ai_orc(Enemy *e) {
    // Orcs: slow march, periodic shooting
    e->shoot_cd--;
    if (e->shoot_cd == 0) {
        e->shoot_cd = ENEMY_SHOOT_CD;
        projectile_spawn_enemy(e->x, e->y, -3, 0);
    }
}

void enemy_update(void) {
    uint8_t i;
    Enemy *e;
    int16_t sx;

    for (i = 0; i < MAX_ENEMIES; i++) {
        e = &enemies[i];
        if (e->type == ENEMY_NONE) continue;

        // AI
        switch (e->type) {
            case ENEMY_HORNET: enemy_ai_hornet(e); break;
            case ENEMY_CROW:   enemy_ai_crow(e);   break;
            case ENEMY_ORC:    enemy_ai_orc(e);    break;
        }

        // Movement
        e->x += FIX(e->dx);
        e->y += FIX(e->dy);

        // Clamp Y to screen
        if (e->y < FIX(16))  e->y = FIX(16);
        if (e->y > FIX(136)) e->y = FIX(136);

        // Remove if off-screen left
        sx = UNFIX(e->x);
        if (sx < -16) {
            e->type = ENEMY_NONE;
            enemy_count--;
            continue;
        }

        // Check hit by player projectile
        if (projectile_check_hit(
                (uint8_t)sx, (uint8_t)UNFIX(e->y), 16, 16)) {
            e->hp--;
            if (e->hp == 0) {
                e->type = ENEMY_NONE;
                enemy_count--;
                // TODO: spawn explosion effect, score
            }
        }

        // Animation
        e->anim_tick++;
        if (e->anim_tick >= ENEMY_ANIM_SPEED) {
            e->anim_tick = 0;
            e->frame = (e->frame + 1) & 0x01;
        }
    }
}

void enemy_draw(void) {
    uint8_t i, j;
    uint8_t oam_base;
    Enemy *e;
    uint8_t sx, sy;
    uint8_t tile;
    uint8_t flags;

    for (i = 0; i < MAX_ENEMIES; i++) {
        oam_base = OAM_ENEMIES + i * 4;
        e = &enemies[i];

        if (e->type == ENEMY_NONE) {
            // Hide all 4 sprites for this slot
            for (j = 0; j < 4; j++) {
                move_sprite(oam_base + j, 0, 0);
            }
            continue;
        }

        sx = (uint8_t)(UNFIX(e->x) + OAM_X_OFS);
        sy = (uint8_t)(UNFIX(e->y) + OAM_Y_OFS);
        tile = e->tile_base + e->frame * 4;
        flags = e->palette & 0x07;

        // 16x16 as 4 8x8 tiles
        set_sprite_tile(oam_base,     tile);
        set_sprite_prop(oam_base,     flags);
        move_sprite(oam_base,         sx, sy);

        set_sprite_tile(oam_base + 1, tile + 1);
        set_sprite_prop(oam_base + 1, flags);
        move_sprite(oam_base + 1,     sx + 8, sy);

        set_sprite_tile(oam_base + 2, tile + 2);
        set_sprite_prop(oam_base + 2, flags);
        move_sprite(oam_base + 2,     sx, sy + 8);

        set_sprite_tile(oam_base + 3, tile + 3);
        set_sprite_prop(oam_base + 3, flags);
        move_sprite(oam_base + 3,     sx + 8, sy + 8);
    }
}

uint8_t enemy_check_player_hit(uint8_t px, uint8_t py) {
    uint8_t i;
    Enemy *e;
    uint8_t ex, ey;

    for (i = 0; i < MAX_ENEMIES; i++) {
        e = &enemies[i];
        if (e->type == ENEMY_NONE) continue;

        ex = (uint8_t)UNFIX(e->x);
        ey = (uint8_t)UNFIX(e->y);

        // AABB collision (12x12 hitbox centered in 16x16)
        if (px + 12 > ex + 2 && px + 2 < ex + 14 &&
            py + 12 > ey + 2 && py + 2 < ey + 14) {
            return 1; // Hit!
        }
    }
    return 0;
}
