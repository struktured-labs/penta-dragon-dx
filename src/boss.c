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

// Spider AI constants (from extraction data):
// Horizontal: dx=22 (much less than gargoyle, slow lateral drift)
// Vertical: dy=42 (large bounce, primarily vertical movement)
// Shoots faster than gargoyle (every 70 frames)
#define SPIDER_X_MIN       40
#define SPIDER_X_MAX      130
#define SPIDER_Y_MIN       20
#define SPIDER_Y_MAX      100
#define SPIDER_X_HALF_PERIOD  60   // Frames per half X drift
#define SPIDER_Y_HALF_PERIOD  20   // Frames per half Y bounce (fast)
#define SPIDER_SHOOT_CD       70   // Faster shooting than gargoyle

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

void boss_spawn_spider(uint8_t x, uint8_t y) {
    boss.type = BOSS_SPIDER;
    boss.x = x;
    boss.y = y;
    boss.hp = BOSS_SPIDER_HP;
    boss.dx = 1;                         // Start drifting right (slow)
    boss.dy = -2;                        // Start bouncing up (fast)
    boss.ai_state = 0;
    boss.ai_timer = 0;
    boss.attack_cd = SPIDER_SHOOT_CD / 2;  // First attack comes sooner
    boss.frame = 0;
    boss.anim_tick = 0;
    boss.palette = 7;               // Uses boss palette slot 7 (spider)
    boss.tile_base = TILE_HUMANOID; // Reuse humanoid tiles until boss tiles extracted
}

// Spider AI: slow horizontal drift with large vertical bounce.
// The spider primarily bounces up and down with minimal lateral movement.
// Shoots aimed at player every 70 frames (faster than gargoyle).
static void boss_ai_spider(void) {
    int8_t aim_dx;
    int8_t aim_dy;

    boss.ai_timer++;

    // Slow horizontal drift: reverse direction every SPIDER_X_HALF_PERIOD frames
    if (boss.ai_timer >= SPIDER_X_HALF_PERIOD) {
        boss.ai_timer = 0;
        boss.dx = -boss.dx;
    }

    // Large vertical bounce: reverse direction at Y boundaries
    // Spider bounces fast with +/-2 pixels per frame
    if (boss.y <= SPIDER_Y_MIN) {
        boss.dy = 2;
    } else if (boss.y >= SPIDER_Y_MAX) {
        boss.dy = -2;
    }

    // Apply movement
    boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
    boss.y = (uint8_t)((int16_t)boss.y + boss.dy);

    // Clamp X to valid range
    if (boss.x < SPIDER_X_MIN) boss.x = SPIDER_X_MIN;
    if (boss.x > SPIDER_X_MAX) boss.x = SPIDER_X_MAX;

    // Attack: fire projectile at player
    if (boss.attack_cd > 0) {
        boss.attack_cd--;
    }
    if (boss.attack_cd == 0) {
        boss.attack_cd = SPIDER_SHOOT_CD;

        // Aim toward player
        aim_dx = -2;
        aim_dy = 0;
        if (boss.x > player.x + 16) {
            aim_dx = -3;
        } else if (boss.x + 32 < player.x) {
            aim_dx = 3;
        }
        if (boss.y + 16 < player.y) {
            aim_dy = 2;
        } else if (boss.y > player.y + 8) {
            aim_dy = -2;
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

// Crimson boss AI constants
// Stage 1 final boss: faster, more aggressive, multi-shot attacks
#define CRIMSON_X_MIN      20
#define CRIMSON_X_MAX      128
#define CRIMSON_SPEED      2    // Faster than minibosses
#define CRIMSON_Y_HALF_P   25   // Fast vertical oscillation
#define CRIMSON_SHOOT_CD   50   // Shoots more often
#define CRIMSON_BURST_CD   10   // Burst fire interval

void boss_spawn_crimson(uint8_t x, uint8_t y) {
    boss.type = BOSS_CRIMSON;
    boss.x = x;
    boss.y = y;
    boss.hp = BOSS_CRIMSON_HP;
    boss.dx = -CRIMSON_SPEED;
    boss.dy = 1;
    boss.ai_state = 0;    // 0=patrol, 1=charge, 2=burst fire
    boss.ai_timer = 0;
    boss.attack_cd = CRIMSON_SHOOT_CD;
    boss.frame = 0;
    boss.anim_tick = 0;
    boss.palette = 6;             // Crimson palette slot
    boss.tile_base = TILE_HUMANOID; // Placeholder tiles
}

// Crimson AI: aggressive patrol with charge attacks and burst fire
static void boss_ai_crimson(void) {
    int8_t aim_dx;
    int8_t aim_dy;

    boss.ai_timer++;

    switch (boss.ai_state) {
        case 0: // Patrol phase
            // Horizontal patrol (faster than minibosses)
            if (boss.x <= CRIMSON_X_MIN) {
                boss.dx = CRIMSON_SPEED;
            } else if (boss.x >= CRIMSON_X_MAX) {
                boss.dx = -CRIMSON_SPEED;
            }

            // Vertical oscillation
            if (boss.ai_timer >= CRIMSON_Y_HALF_P) {
                boss.ai_timer = 0;
                boss.dy = -boss.dy;
            }

            // Apply movement
            boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
            boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
            if (boss.y < 16) boss.y = 16;
            if (boss.y > 96) boss.y = 96;

            // Single aimed shot
            boss.attack_cd--;
            if (boss.attack_cd == 0) {
                boss.attack_cd = CRIMSON_SHOOT_CD;

                aim_dx = (boss.x > player.x) ? -3 : 3;
                aim_dy = 0;
                if (boss.y + 16 < player.y) aim_dy = 1;
                else if (boss.y > player.y + 8) aim_dy = -1;

                projectile_spawn_enemy(boss.x + 12, boss.y + 16, aim_dx, aim_dy);

                // Every 3rd attack, switch to charge
                if ((boss.ai_timer & 0x03) == 0 && boss.hp < 25) {
                    boss.ai_state = 1;
                    boss.ai_timer = 0;
                }
            }
            break;

        case 1: // Charge phase — rush toward player's Y position
            if (boss.ai_timer < 30) {
                // Pause briefly
                boss.dx = 0;
                boss.dy = 0;
            } else if (boss.ai_timer < 60) {
                // Rush toward player
                boss.dx = -3;
                boss.dy = (player.y > boss.y + 16) ? 2 : -2;
                boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
                boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
                if (boss.x < CRIMSON_X_MIN) boss.x = CRIMSON_X_MIN;
                if (boss.y < 16) boss.y = 16;
                if (boss.y > 96) boss.y = 96;
            } else {
                // Switch to burst fire
                boss.ai_state = 2;
                boss.ai_timer = 0;
                boss.attack_cd = CRIMSON_BURST_CD;
            }
            break;

        case 2: // Burst fire — rapid 3-shot spread
            boss.dx = 0;
            boss.dy = 0;

            boss.attack_cd--;
            if (boss.attack_cd == 0) {
                boss.attack_cd = CRIMSON_BURST_CD;
                // Spread shot: left, straight, right
                projectile_spawn_enemy(boss.x, boss.y + 8, -3, -1);
                projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                projectile_spawn_enemy(boss.x, boss.y + 24, -3, 1);
            }

            if (boss.ai_timer >= 40) {
                // Return to patrol
                boss.ai_state = 0;
                boss.ai_timer = 0;
                boss.dx = -CRIMSON_SPEED;
                boss.dy = 1;
                boss.attack_cd = CRIMSON_SHOOT_CD;
            }
            break;
    }

    // Animation
    boss.anim_tick++;
    if (boss.anim_tick >= BOSS_ANIM_SPEED) {
        boss.anim_tick = 0;
        boss.frame = (boss.frame + 1) & 0x01;
    }
}

// Penta Dragon — true final boss. The five-headed dragon.
// 4 phases based on HP thresholds (5 "heads" = 5 attack patterns):
//   Phase 0 (HP>90): Slow patrol, single aimed shots
//   Phase 1 (HP>60): Faster patrol, 3-shot spread
//   Phase 2 (HP>30): Charge attacks + 5-shot fan
//   Phase 3 (HP<=30): Enraged — fast erratic movement, rapid fire
#define PENTA_X_MIN      16
#define PENTA_X_MAX      132
#define PENTA_SHOOT_CD_0 60
#define PENTA_SHOOT_CD_1 40
#define PENTA_SHOOT_CD_2 25
#define PENTA_SHOOT_CD_3 12

void boss_spawn_penta(uint8_t x, uint8_t y) {
    boss.type = BOSS_PENTA;
    boss.x = x;
    boss.y = y;
    boss.hp = BOSS_PENTA_HP;
    boss.dx = -1;
    boss.dy = 1;
    boss.ai_state = 0;
    boss.ai_timer = 0;
    boss.attack_cd = PENTA_SHOOT_CD_0;
    boss.frame = 0;
    boss.anim_tick = 0;
    boss.palette = 7;             // Use special palette slot
    boss.tile_base = TILE_HUMANOID;
}

static void boss_ai_penta(void) {
    uint8_t phase;
    int8_t aim_dx;

    boss.ai_timer++;

    // Determine phase from HP
    if (boss.hp > 90) phase = 0;
    else if (boss.hp > 60) phase = 1;
    else if (boss.hp > 30) phase = 2;
    else phase = 3;

    // Movement — gets faster and more erratic each phase
    {
        uint8_t speed = 1 + phase;
        uint8_t y_period = 30 - phase * 5;

        if (boss.x <= PENTA_X_MIN) boss.dx = speed;
        else if (boss.x >= PENTA_X_MAX) boss.dx = -(int8_t)speed;

        if (boss.ai_timer >= y_period) {
            boss.ai_timer = 0;
            boss.dy = -boss.dy;
            if (boss.dy == 0) boss.dy = 1;
        }

        boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
        boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
        if (boss.y < 12) boss.y = 12;
        if (boss.y > 100) boss.y = 100;
    }

    // Attacks — escalate per phase
    boss.attack_cd--;
    if (boss.attack_cd == 0) {
        aim_dx = (boss.x > player.x) ? -3 : 3;

        switch (phase) {
            case 0: // Single aimed shot
                boss.attack_cd = PENTA_SHOOT_CD_0;
                projectile_spawn_enemy(boss.x, boss.y + 16, aim_dx, 0);
                break;

            case 1: // 3-shot spread
                boss.attack_cd = PENTA_SHOOT_CD_1;
                projectile_spawn_enemy(boss.x, boss.y + 8, aim_dx, -1);
                projectile_spawn_enemy(boss.x, boss.y + 16, aim_dx, 0);
                projectile_spawn_enemy(boss.x, boss.y + 24, aim_dx, 1);
                break;

            case 2: // 5-shot fan (the five heads)
                boss.attack_cd = PENTA_SHOOT_CD_2;
                projectile_spawn_enemy(boss.x, boss.y,      aim_dx, -2);
                projectile_spawn_enemy(boss.x, boss.y + 8,  aim_dx, -1);
                projectile_spawn_enemy(boss.x, boss.y + 16, aim_dx, 0);
                projectile_spawn_enemy(boss.x, boss.y + 24, aim_dx, 1);
                projectile_spawn_enemy(boss.x, boss.y + 30, aim_dx, 2);
                break;

            case 3: // Enraged — rapid alternating spread
                boss.attack_cd = PENTA_SHOOT_CD_3;
                if (boss.ai_timer & 0x01) {
                    projectile_spawn_enemy(boss.x, boss.y + 8, -4, -1);
                    projectile_spawn_enemy(boss.x, boss.y + 24, -4, 1);
                } else {
                    projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                    projectile_spawn_enemy(boss.x, boss.y, 4, -2);
                    projectile_spawn_enemy(boss.x, boss.y + 30, 4, 2);
                }
                break;
        }
    }

    // Animation (faster when enraged)
    boss.anim_tick++;
    if (boss.anim_tick >= (phase >= 3 ? 8 : BOSS_ANIM_SPEED)) {
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
        case BOSS_SPIDER:
            boss_ai_spider();
            break;
        case BOSS_CRIMSON:
            boss_ai_crimson();
            break;
        case BOSS_PENTA:
            boss_ai_penta();
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
