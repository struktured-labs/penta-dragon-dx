#include "boss.h"
#include "projectile.h"
#include "player.h"
#include "sound.h"
#include "music.h"

Boss boss;

// Gargoyle AI constants (from extraction data):
// Horizontal patrol: X range = 90px (from ~28 to ~118)
// Vertical oscillation: Y range = ~9px (minor bounce)
// Movement is rigid body (all 16 sprites move in sync)
#define GARGOYLE_X_MIN     28
#define GARGOYLE_X_MAX    118
#define GARGOYLE_Y_CENTER  56
#define GARGOYLE_Y_AMP      4   // Half-amplitude of Y oscillation
#define GARGOYLE_PATROL_SPEED  1   // Pixels per frame horizontal
#define GARGOYLE_Y_HALF_PERIOD 30  // Frames per half Y oscillation

void boss_init(void) {
    uint8_t i;

    boss.type = BOSS_NONE;
    boss.x = 0;
    boss.y = 0;
    boss.hp = 0;
    boss.dx = 0;
    boss.dy = 0;
    boss.ai_state = 0;
    boss.ai_timer = 0;
    boss.attack_cd = 0;
    boss.frame = 0;
    boss.anim_tick = 0;
    boss.palette = 6;
    boss.tile_base = TILE_HUMANOID;  // Reuse humanoid tiles for now

    // Clear boss OAM slots
    for (i = 0; i < BOSS_OAM_SLOTS; i++) {
        move_sprite(OAM_BOSS + i, 0, 0);
    }
}

void boss_spawn_gargoyle(uint8_t x, uint8_t y) {
    boss.type = BOSS_GARGOYLE;
    boss.x = x;
    boss.y = y;
    boss.hp = BOSS_GARGOYLE_HP;
    boss.dx = -GARGOYLE_PATROL_SPEED;  // Start moving left
    boss.dy = 1;                        // Start oscillating down
    boss.ai_state = 0;
    boss.ai_timer = 0;
    boss.attack_cd = BOSS_SHOOT_CD / 2;  // First attack comes sooner
    boss.frame = 0;
    boss.anim_tick = 0;
    boss.palette = 6;               // Uses boss palette slot 6 (gargoyle)
    boss.tile_base = TILE_HUMANOID; // Reuse humanoid tiles until boss tiles extracted
}

// Gargoyle AI: horizontal patrol with vertical oscillation.
// Fires projectiles aimed at the player periodically.
static void boss_ai_gargoyle(void) {
    int8_t aim_dx;
    int8_t aim_dy;

    boss.ai_timer++;

    // Horizontal patrol: bounce between X_MIN and X_MAX
    if (boss.x <= GARGOYLE_X_MIN) {
        boss.dx = GARGOYLE_PATROL_SPEED;
    } else if (boss.x >= GARGOYLE_X_MAX) {
        boss.dx = -GARGOYLE_PATROL_SPEED;
    }

    // Vertical oscillation: reverse direction every Y_HALF_PERIOD frames
    if (boss.ai_timer >= GARGOYLE_Y_HALF_PERIOD) {
        boss.ai_timer = 0;
        boss.dy = -boss.dy;
    }

    // Apply movement
    boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
    boss.y = (uint8_t)((int16_t)boss.y + boss.dy);

    // Clamp Y to valid range
    if (boss.y < 20) boss.y = 20;
    if (boss.y > 100) boss.y = 100;

    // Attack: fire projectile at player
    if (boss.attack_cd > 0) {
        boss.attack_cd--;
    }
    if (boss.attack_cd == 0) {
        boss.attack_cd = BOSS_SHOOT_CD;

        // Aim toward player
        aim_dx = -2;  // Default: shoot left
        aim_dy = 0;
        if (boss.x > player.x + 16) {
            aim_dx = -3;
        } else if (boss.x + 32 < player.x) {
            aim_dx = 3;
        }
        if (boss.y + 16 < player.y) {
            aim_dy = 1;
        } else if (boss.y > player.y + 8) {
            aim_dy = -1;
        }

        // Fire from center of boss sprite
        projectile_spawn_enemy(boss.x + 12, boss.y + 16, aim_dx, aim_dy);
    }

    // Animation
    boss.anim_tick++;
    if (boss.anim_tick >= BOSS_ANIM_SPEED) {
        boss.anim_tick = 0;
        boss.frame = (boss.frame + 1) & 0x01;
    }
}

void boss_update(void) {
    if (boss.type == BOSS_NONE) return;

    switch (boss.type) {
        case BOSS_GARGOYLE:
            boss_ai_gargoyle();
            break;
        default:
            break;
    }
}

// Draw the boss as a 4x4 grid of 8x8 sprites (16 OAM slots).
// Uses humanoid tiles as placeholder: two animation frames of 4 tiles each.
// The 4x4 grid repeats the 2x2 tile pattern across the 32x32 area.
void boss_draw(void) {
    uint8_t i, row, col;
    uint8_t sx, sy;
    uint8_t tile;
    uint8_t flags;
    uint8_t oam_idx;
    uint8_t sub_tile;

    if (boss.type == BOSS_NONE) {
        // Clear all boss OAM slots
        for (i = 0; i < BOSS_OAM_SLOTS; i++) {
            move_sprite(OAM_BOSS + i, 0, 0);
        }
        return;
    }

    flags = boss.palette & 0x07;

    // Base tile for current animation frame (humanoid has 4 tiles per frame)
    tile = boss.tile_base + boss.frame * 4;

    // Draw 4x4 grid of 8x8 sprites
    // Each 2x2 sub-block uses tiles: tile+0 (TL), tile+1 (TR), tile+2 (BL), tile+3 (BR)
    for (row = 0; row < 4; row++) {
        for (col = 0; col < 4; col++) {
            oam_idx = OAM_BOSS + row * 4 + col;
            sx = boss.x + col * 8 + OAM_X_OFS;
            sy = boss.y + row * 8 + OAM_Y_OFS;

            // Map to 2x2 sub-tile pattern (repeats within 4x4 grid)
            // row%2, col%2 determines which tile in the 2x2 block
            sub_tile = (row & 0x01) * 2 + (col & 0x01);

            set_sprite_tile(oam_idx, tile + sub_tile);
            set_sprite_prop(oam_idx, flags);
            move_sprite(oam_idx, sx, sy);
        }
    }
}

uint8_t boss_check_hit(uint8_t px, uint8_t py) {
    if (boss.type == BOSS_NONE) return 0;

    // AABB collision: boss is 32x32 pixels
    if (px >= boss.x && px < boss.x + 32 &&
        py >= boss.y && py < boss.y + 32) {

        boss.hp--;
        sound_enemy_hit();
        music_sfx_ch4(8);

        if (boss.hp == 0) {
            boss.type = BOSS_NONE;
            return 2;  // Boss killed
        }
        return 1;  // Boss hit but alive
    }
    return 0;
}

uint8_t boss_check_player_hit(uint8_t px, uint8_t py) {
    if (boss.type == BOSS_NONE) return 0;

    // Slightly smaller hitbox for fairness (inset by 4px)
    if (px + 12 > boss.x + 4 && px + 2 < boss.x + 28 &&
        py + 12 > boss.y + 4 && py + 2 < boss.y + 28) {
        return 1;
    }
    return 0;
}
