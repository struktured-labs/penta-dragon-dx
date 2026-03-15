#include "enemy.h"
#include "projectile.h"
#include "player.h"

#include "../assets/extracted/sprites/include/sprites_hornets.h"
#include "../assets/extracted/sprites/include/sprites_crows.h"
#include "../assets/extracted/sprites/include/sprites_orcs.h"

Enemy enemies[MAX_ENEMIES];
uint8_t enemy_count;

#define ENEMY_ANIM_SPEED 16
#define ENEMY_SHOOT_CD   90

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

void enemy_spawn(uint8_t type, uint8_t x, uint8_t y) {
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
            e->shoot_cd = ENEMY_SHOOT_CD / 2;
            e->ai_state = 0;
            e->ai_timer = 0;

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
    e->ai_timer++;
    if (e->ai_timer >= 30) {
        e->ai_timer = 0;
        e->dy = -e->dy;
        if (e->dy == 0) e->dy = 1;
    }
}

static void enemy_ai_crow(Enemy *e) {
    if (e->ai_state == 0) {
        e->ai_timer++;
        if (e->ai_timer >= 40) {
            e->ai_state = 1;
            e->ai_timer = 0;
            e->dy = (player.y > e->y) ? 2 : -2;
        }
    } else {
        e->ai_timer++;
        if (e->ai_timer >= 30) {
            e->ai_state = 0;
            e->ai_timer = 0;
            e->dy = 0;
        }
    }
}

static void enemy_ai_orc(Enemy *e) {
    e->shoot_cd--;
    if (e->shoot_cd == 0) {
        e->shoot_cd = ENEMY_SHOOT_CD;
        projectile_spawn_enemy(e->x, e->y + 4, -3, 0);
    }
}

void enemy_update(void) {
    uint8_t i;
    Enemy *e;
    uint8_t new_x;
    int16_t new_y;

    for (i = 0; i < MAX_ENEMIES; i++) {
        e = &enemies[i];
        if (e->type == ENEMY_NONE) continue;

        // AI
        switch (e->type) {
            case ENEMY_HORNET: enemy_ai_hornet(e); break;
            case ENEMY_CROW:   enemy_ai_crow(e);   break;
            case ENEMY_ORC:    enemy_ai_orc(e);    break;
        }

        // Movement with signed arithmetic
        new_x = (uint8_t)((int16_t)e->x + e->dx);
        new_y = (int16_t)e->y + e->dy;

        // Clamp Y
        if (new_y < 16)  new_y = 16;
        if (new_y > 128) new_y = 128;
        e->y = (uint8_t)new_y;

        // Remove if off-screen left (unsigned wrap: x > 200 after subtracting)
        if (new_x > 200) {
            e->type = ENEMY_NONE;
            enemy_count--;
            continue;
        }
        e->x = new_x;

        // Check hit by player projectile
        if (projectile_check_hit(e->x, e->y, 16, 16)) {
            e->hp--;
            if (e->hp == 0) {
                e->type = ENEMY_NONE;
                enemy_count--;
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
            for (j = 0; j < 4; j++) {
                move_sprite(oam_base + j, 0, 0);
            }
            continue;
        }

        sx = e->x + OAM_X_OFS;
        sy = e->y + OAM_Y_OFS;
        tile = e->tile_base + e->frame * 4;
        flags = e->palette & 0x07;

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

    for (i = 0; i < MAX_ENEMIES; i++) {
        e = &enemies[i];
        if (e->type == ENEMY_NONE) continue;

        if (px + 12 > e->x + 2 && px + 2 < e->x + 14 &&
            py + 12 > e->y + 2 && py + 2 < e->y + 14) {
            return 1;
        }
    }
    return 0;
}
