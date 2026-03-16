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
    boss.type = BOSS_MINIBOSS_1;
    boss.x = x;
    boss.y = y;
    boss.hp = BOSS_MINIBOSS_HP;
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
    boss.type = BOSS_MINIBOSS_2;
    boss.x = x;
    boss.y = y;
    boss.hp = BOSS_MINIBOSS_HP;
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

// Stage boss AI constants
#define STAGEBOSS_X_MIN    20
#define STAGEBOSS_X_MAX    128
#define STAGEBOSS_Y_MIN    16
#define STAGEBOSS_Y_MAX    96

void boss_spawn_crimson(uint8_t x, uint8_t y) {
    // Generic stage boss spawn — type and HP are set by gamestate before/after
    boss.x = x;
    boss.y = y;
    boss.dx = -2;
    boss.dy = 1;
    boss.ai_state = 0;
    boss.ai_timer = 0;
    boss.attack_cd = 50;
    boss.frame = 0;
    boss.anim_tick = 0;
    boss.tile_base = TILE_HUMANOID;
}

// Helper: clamp boss position to arena bounds
static void boss_clamp(void) {
    if (boss.x < STAGEBOSS_X_MIN) boss.x = STAGEBOSS_X_MIN;
    if (boss.x > STAGEBOSS_X_MAX) boss.x = STAGEBOSS_X_MAX;
    if (boss.y < STAGEBOSS_Y_MIN) boss.y = STAGEBOSS_Y_MIN;
    if (boss.y > STAGEBOSS_Y_MAX) boss.y = STAGEBOSS_Y_MAX;
}

// Helper: common animation tick
static void boss_animate(uint8_t speed) {
    boss.anim_tick++;
    if (boss.anim_tick >= speed) {
        boss.anim_tick = 0;
        boss.frame = (boss.frame + 1) & 0x01;
    }
}

// ---- Shalamar (Stage 1): Scorpion — patrol + charge + tail burst ----
static void boss_ai_shalamar(void) {
    int8_t aim_dx;
    boss.ai_timer++;

    switch (boss.ai_state) {
        case 0: // Patrol: horizontal bounce, vertical oscillation
            if (boss.x <= STAGEBOSS_X_MIN) boss.dx = 2;
            else if (boss.x >= STAGEBOSS_X_MAX) boss.dx = -2;
            if (boss.ai_timer >= 25) {
                boss.ai_timer = 0;
                boss.dy = -boss.dy;
            }
            boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
            boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
            boss_clamp();

            boss.attack_cd--;
            if (boss.attack_cd == 0) {
                boss.attack_cd = 50;
                aim_dx = (boss.x > player.x) ? -3 : 3;
                projectile_spawn_enemy(boss.x + 12, boss.y + 16, aim_dx, 0);
                if (boss.hp < (BOSS_SHALAMAR_HP / 2)) {
                    boss.ai_state = 1;
                    boss.ai_timer = 0;
                }
            }
            break;
        case 1: // Charge: rush toward player Y
            if (boss.ai_timer < 30) {
                boss.dx = 0; boss.dy = 0;
            } else if (boss.ai_timer < 60) {
                boss.dx = -3;
                boss.dy = (player.y > boss.y + 16) ? 2 : -2;
                boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
                boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
                boss_clamp();
            } else {
                boss.ai_state = 2;
                boss.ai_timer = 0;
                boss.attack_cd = 10;
            }
            break;
        case 2: // Burst: rapid 3-shot spread (tail attack)
            boss.dx = 0; boss.dy = 0;
            boss.attack_cd--;
            if (boss.attack_cd == 0) {
                boss.attack_cd = 10;
                projectile_spawn_enemy(boss.x, boss.y + 8, -3, -1);
                projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                projectile_spawn_enemy(boss.x, boss.y + 24, -3, 1);
            }
            if (boss.ai_timer >= 40) {
                boss.ai_state = 0;
                boss.ai_timer = 0;
                boss.dx = -2; boss.dy = 1;
                boss.attack_cd = 50;
            }
            break;
    }
    boss_animate(BOSS_ANIM_SPEED);
}

// ---- Riff (Stage 2): Black ball barrage — stays high, rains projectiles ----
static void boss_ai_riff(void) {
    boss.ai_timer++;

    // Stays in upper half, drifts horizontally
    if (boss.x <= STAGEBOSS_X_MIN) boss.dx = 1;
    else if (boss.x >= STAGEBOSS_X_MAX) boss.dx = -1;
    // Slow vertical bob in upper area
    if (boss.y < 20) boss.dy = 1;
    else if (boss.y > 50) boss.dy = -1;

    boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
    boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
    if (boss.y < 16) boss.y = 16;
    if (boss.y > 55) boss.y = 55;

    // Rain black balls downward + aimed shots
    boss.attack_cd--;
    if (boss.attack_cd == 0) {
        uint8_t pattern = boss.ai_timer & 0x03;
        boss.attack_cd = 35;
        // Downward rain
        projectile_spawn_enemy(boss.x + 8, boss.y + 30, 0, 3);
        projectile_spawn_enemy(boss.x + 24, boss.y + 30, 0, 3);
        // Aimed shot every other attack
        if (pattern & 0x01) {
            int8_t adx = (boss.x > player.x) ? -2 : 2;
            int8_t ady = 2;
            projectile_spawn_enemy(boss.x + 16, boss.y + 30, adx, ady);
        }
        // When hurt: faster, extra shots
        if (boss.hp < (BOSS_RIFF_HP / 2)) {
            boss.attack_cd = 22;
            projectile_spawn_enemy(boss.x + 16, boss.y + 30, -1, 3);
        }
    }
    boss_animate(BOSS_ANIM_SPEED);
}

// ---- Crystal Dragon (Stage 3): Teleport — warps to random positions ----
static void boss_ai_crystal(void) {
    boss.ai_timer++;

    switch (boss.ai_state) {
        case 0: // Visible: slow movement + aimed shots
            boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
            boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
            boss_clamp();

            if (boss.x <= STAGEBOSS_X_MIN || boss.x >= STAGEBOSS_X_MAX) boss.dx = -boss.dx;
            if (boss.y <= STAGEBOSS_Y_MIN || boss.y >= STAGEBOSS_Y_MAX) boss.dy = -boss.dy;

            boss.attack_cd--;
            if (boss.attack_cd == 0) {
                boss.attack_cd = 45;
                projectile_spawn_enemy(boss.x, boss.y + 16,
                    (boss.x > player.x) ? -3 : 3, 0);
            }
            // Warp every 90 frames
            if (boss.ai_timer >= 90) {
                boss.ai_state = 1;
                boss.ai_timer = 0;
            }
            break;
        case 1: // Warping out (invisible for ~20 frames)
            // Move off screen briefly (visually "disappears")
            if (boss.ai_timer == 1) {
                boss.x = 200; // Off-screen
            }
            if (boss.ai_timer >= 20) {
                // Reappear at semi-random position near player
                uint8_t new_x = 80 + (boss.ai_timer * 17) % 60;
                uint8_t new_y = 30 + (boss.ai_timer * 13) % 50;
                if (new_x > STAGEBOSS_X_MAX) new_x = STAGEBOSS_X_MAX;
                boss.x = new_x;
                boss.y = new_y;
                boss.dx = (boss.x > player.x) ? -2 : 2;
                boss.dy = (boss.y > 60) ? -1 : 1;
                // Fire spread on reappear
                projectile_spawn_enemy(boss.x, boss.y + 8, -3, -1);
                projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                projectile_spawn_enemy(boss.x, boss.y + 24, -3, 1);
                boss.ai_state = 0;
                boss.ai_timer = 0;
                boss.attack_cd = 30;
            }
            break;
    }
    boss_animate(BOSS_ANIM_SPEED);
}

// ---- Cameo (Stage 4): Chameleon — turns invisible, surprise attacks ----
static void boss_ai_cameo(void) {
    boss.ai_timer++;

    switch (boss.ai_state) {
        case 0: // Visible: circle around arena
            {
                // Circular-ish motion using alternating axes
                uint8_t phase = (boss.ai_timer >> 4) & 0x03;
                switch (phase) {
                    case 0: boss.dx = 2; boss.dy = 1; break;
                    case 1: boss.dx = -1; boss.dy = 2; break;
                    case 2: boss.dx = -2; boss.dy = -1; break;
                    case 3: boss.dx = 1; boss.dy = -2; break;
                }
            }
            boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
            boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
            boss_clamp();

            boss.attack_cd--;
            if (boss.attack_cd == 0) {
                boss.attack_cd = 40;
                projectile_spawn_enemy(boss.x, boss.y + 16,
                    (boss.x > player.x) ? -3 : 3, 0);
            }
            // Go invisible every 80 frames
            if (boss.ai_timer >= 80) {
                boss.ai_state = 1;
                boss.ai_timer = 0;
            }
            break;
        case 1: // Invisible: move toward player, then surprise attack
            // Boss is "invisible" — palette trick: move off-screen
            if (boss.ai_timer == 1) {
                boss.x = 200;
            }
            if (boss.ai_timer >= 40) {
                // Reappear right next to player and fire
                boss.x = player.x + 40;
                if (boss.x > STAGEBOSS_X_MAX) boss.x = STAGEBOSS_X_MAX;
                boss.y = player.y;
                boss_clamp();
                // Burst fire on reappear
                projectile_spawn_enemy(boss.x, boss.y, -4, -2);
                projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                projectile_spawn_enemy(boss.x, boss.y + 30, -4, 2);
                boss.ai_state = 0;
                boss.ai_timer = 0;
                boss.attack_cd = 25;
            }
            break;
    }
    boss_animate(12); // Slightly faster animation
}

// ---- Ted (Stage 5): Stationary — fires vine tendrils in patterns ----
static void boss_ai_ted(void) {
    boss.ai_timer++;

    // Ted stays mostly still (Mother Brain-like), slight vertical bob
    boss.x = 120; // Fixed right side
    if (boss.ai_timer & 0x20) {
        boss.y = (uint8_t)((int16_t)boss.y + 1);
        if (boss.y > 70) boss.y = 70;
    } else {
        if (boss.y > STAGEBOSS_Y_MIN)
            boss.y = (uint8_t)((int16_t)boss.y - 1);
    }

    // Fire vines (multi-directional tendril patterns)
    boss.attack_cd--;
    if (boss.attack_cd == 0) {
        uint8_t pattern = (boss.ai_timer >> 3) & 0x03;
        boss.attack_cd = 30;

        switch (pattern) {
            case 0: // Horizontal sweep
                projectile_spawn_enemy(boss.x, boss.y + 8, -3, 0);
                projectile_spawn_enemy(boss.x, boss.y + 24, -3, 0);
                break;
            case 1: // Fan spread
                projectile_spawn_enemy(boss.x, boss.y, -2, -2);
                projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                projectile_spawn_enemy(boss.x, boss.y + 30, -2, 2);
                break;
            case 2: // Diagonal cross
                projectile_spawn_enemy(boss.x, boss.y + 4, -3, -1);
                projectile_spawn_enemy(boss.x, boss.y + 28, -3, 1);
                break;
            case 3: // Dense barrage when hurt
                projectile_spawn_enemy(boss.x, boss.y, -3, -2);
                projectile_spawn_enemy(boss.x, boss.y + 10, -4, -1);
                projectile_spawn_enemy(boss.x, boss.y + 20, -4, 1);
                projectile_spawn_enemy(boss.x, boss.y + 30, -3, 2);
                break;
        }
        if (boss.hp < (BOSS_TED_HP / 2)) {
            boss.attack_cd = 18; // Much faster when hurt
        }
    }
    boss_animate(BOSS_ANIM_SPEED);
}

// ---- Troop (Stage 6): Fireballs + homing missiles ----
static void boss_ai_troop(void) {
    boss.ai_timer++;

    // Fast diagonal patrol
    if (boss.x <= STAGEBOSS_X_MIN) boss.dx = 3;
    else if (boss.x >= STAGEBOSS_X_MAX) boss.dx = -3;
    if (boss.y <= STAGEBOSS_Y_MIN) boss.dy = 2;
    else if (boss.y >= STAGEBOSS_Y_MAX) boss.dy = -2;

    boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
    boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
    boss_clamp();

    boss.attack_cd--;
    if (boss.attack_cd == 0) {
        boss.attack_cd = 28;
        // Fireball: fast aimed shot
        {
            int8_t adx = (boss.x > player.x) ? -4 : 4;
            int8_t ady = 0;
            if (boss.y + 16 < player.y) ady = 2;
            else if (boss.y > player.y + 8) ady = -2;
            projectile_spawn_enemy(boss.x, boss.y + 16, adx, ady);
        }
        // Homing-ish missile (slow, aimed at player center)
        if (boss.ai_timer & 0x02) {
            int8_t hx = (player.x > boss.x + 16) ? 1 : -1;
            int8_t hy = (player.y > boss.y + 16) ? 1 : -1;
            projectile_spawn_enemy(boss.x + 16, boss.y, hx, hy);
        }
        if (boss.hp < (BOSS_TROOP_HP / 3)) {
            boss.attack_cd = 16;
        }
    }
    boss_animate(10); // Fast animation
}

// ---- Faze (Stage 7): Screen-filler — aggressive, fills screen with shots ----
static void boss_ai_faze(void) {
    boss.ai_timer++;

    // Erratic high-speed movement
    {
        uint8_t sp = 3;
        if (boss.hp < (BOSS_FAZE_HP / 2)) sp = 4;

        if (boss.x <= STAGEBOSS_X_MIN) boss.dx = sp;
        else if (boss.x >= STAGEBOSS_X_MAX) boss.dx = -(int8_t)sp;

        // Rapid Y oscillation
        if (boss.ai_timer % 15 == 0) {
            boss.dy = -boss.dy;
            if (boss.dy == 0) boss.dy = 2;
        }
    }

    boss.x = (uint8_t)((int16_t)boss.x + boss.dx);
    boss.y = (uint8_t)((int16_t)boss.y + boss.dy);
    boss_clamp();

    // Screen-filling attack patterns
    boss.attack_cd--;
    if (boss.attack_cd == 0) {
        uint8_t pattern = (boss.ai_timer >> 2) & 0x03;
        boss.attack_cd = 20;

        switch (pattern) {
            case 0: // 5-direction fan
                projectile_spawn_enemy(boss.x, boss.y,      -3, -2);
                projectile_spawn_enemy(boss.x, boss.y + 8,  -4, -1);
                projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                projectile_spawn_enemy(boss.x, boss.y + 24, -4, 1);
                projectile_spawn_enemy(boss.x, boss.y + 30, -3, 2);
                break;
            case 1: // Cross pattern
                projectile_spawn_enemy(boss.x, boss.y + 16, -4, 0);
                projectile_spawn_enemy(boss.x + 16, boss.y, 0, -3);
                projectile_spawn_enemy(boss.x + 16, boss.y + 30, 0, 3);
                break;
            case 2: // Rapid aimed double
                {
                    int8_t adx = (boss.x > player.x) ? -4 : 4;
                    projectile_spawn_enemy(boss.x, boss.y + 12, adx, -1);
                    projectile_spawn_enemy(boss.x, boss.y + 20, adx, 1);
                }
                break;
            case 3: // Spiral scatter
                projectile_spawn_enemy(boss.x, boss.y, -2, -3);
                projectile_spawn_enemy(boss.x, boss.y + 30, -2, 3);
                projectile_spawn_enemy(boss.x + 30, boss.y + 16, 2, 0);
                break;
        }
        if (boss.hp < (BOSS_FAZE_HP / 3)) {
            boss.attack_cd = 12; // Extremely aggressive when low HP
        }
    }
    boss_animate(8); // Very fast animation
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
        case BOSS_MINIBOSS_1:
            boss_ai_gargoyle();
            break;
        case BOSS_MINIBOSS_2:
            boss_ai_spider();
            break;
        case BOSS_SHALAMAR:
            boss_ai_shalamar();
            break;
        case BOSS_RIFF:
            boss_ai_riff();
            break;
        case BOSS_CRYSTAL:
            boss_ai_crystal();
            break;
        case BOSS_CAMEO:
            boss_ai_cameo();
            break;
        case BOSS_TED:
            boss_ai_ted();
            break;
        case BOSS_TROOP:
            boss_ai_troop();
            break;
        case BOSS_FAZE:
            boss_ai_faze();
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
