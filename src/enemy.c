#include "enemy.h"
#include "projectile.h"
#include "player.h"
#include "gamestate.h"
#include "itemmenu.h"
#include "sound.h"
#include "music.h"

#include "../assets/extracted/sprites/include/sprites_hornets.h"
#include "../assets/extracted/sprites/include/sprites_crows.h"
#include "../assets/extracted/sprites/include/sprites_orcs.h"
#include "../assets/extracted/sprites/include/sprites_humanoids.h"
#include "../assets/extracted/sprites/include/sprites_special_catfish.h"

Enemy enemies[MAX_ENEMIES];
uint8_t enemy_count;

#define ENEMY_ANIM_SPEED 16

/* --- Extracted from original ROM frame-by-frame analysis ---
 *
 * The original game runs a main loop every 4 frames (15 Hz).
 * Some enemies (orc, humanoid) update every 8 frames (7.5 Hz).
 * The remake runs at 60 fps, so we throttle via ai_timer.
 *
 * Hornet:  moves every 4 frames, DX~-4/tick, DY oscillates +-1/tick
 *          Net: ~-1 px/frame left, ~0.3 px/frame vertical oscillation
 *          Y oscillation period: ~60 frames (30 down, 30 up)
 *          Amplitude: ~15 px. Does NOT shoot.
 *
 * Crow:    moves every 4 frames, DX~-3/tick, DY~-2/tick
 *          Net: ~-1 px/frame left, ~-0.5 px/frame up (diagonal)
 *          Short lifetime (~28 frames). Does NOT shoot.
 *
 * Orc:     moves every 8 frames, DX~-1/tick, DY oscillates +-1/tick
 *          Net: ~-0.13 px/frame left (very slow patrol)
 *          Y oscillation period: ~300 frames (150 down, 150 up)
 *          Amplitude: ~20 px. SHOOTS aimed at player every ~90-100 frames.
 *
 * Humanoid: moves every 8 frames, DX~-1/tick, DY drifts +-1/tick
 *          Net: ~-0.18 px/frame left (slow approach)
 *          Y drift: goes one direction for ~100 frames, then reverses
 *          Amplitude: ~20 px. SHOOTS aimed at player every ~90-100 frames.
 */

/* Shoot cooldown: ~90-100 frames in original (avg gap between shots) */
#define ENEMY_SHOOT_CD   90

/* Throttle ticks for slow enemies (orc/humanoid).
 * Original moves DX=-1 every 8 frames = -0.125 px/frame.
 * Using 8 to match original exactly. */
#define TICK_SLOW   8

/* Y oscillation half-periods (frames) */
#define HORNET_Y_HALF_PERIOD  30
#define ORC_Y_HALF_PERIOD     75
#define HUMANOID_Y_HALF_PERIOD 100

static const uint8_t enemy_hp[]      = { 0, 2, 2, 3, 3, 4, 3, 4 };
static const uint8_t enemy_palette[] = { 0, 4, 3, 5, 6, 7, 4, 6 };

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
    set_sprite_data(TILE_HUMANOID, SPRITE_HUMANOIDS_TILE_COUNT, SPRITE_HUMANOIDS);
    set_sprite_data(TILE_CATFISH, SPRITE_SPECIAL_CATFISH_TILE_COUNT, SPRITE_SPECIAL_CATFISH);
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
            // HP scales with stage: +1 HP per 2 stages
            e->hp = enemy_hp[type] + (game_stage - 1) / 2;
            e->palette = enemy_palette[type];
            e->frame = 0;
            e->anim_tick = 0;
            /* Shoot cooldown scales with stage: faster in later stages */
            {
                uint8_t cd = ENEMY_SHOOT_CD - (game_stage - 1) * 8;
                if (cd < 40) cd = 40;
                e->shoot_cd = cd / 2;
            }
            e->ai_state = 0;
            e->ai_timer = 0;
            e->hit_flash = 0;

            switch (type) {
                case ENEMY_HORNET:
                    e->tile_base = TILE_HORNET;
                    e->dx = -1;     /* Constant leftward, applied each frame */
                    e->dy = 1;      /* Start moving down; will oscillate */
                    break;
                case ENEMY_CROW:
                    e->tile_base = TILE_CROW;
                    e->dx = -2;     /* Fast leftward */
                    e->dy = -1;     /* Diagonal upward flight */
                    break;
                case ENEMY_ORC:
                    e->tile_base = TILE_ORC;
                    e->dx = 0;      /* Slow patrol: movement applied by AI */
                    e->dy = 0;
                    e->ai_state = 1; /* Start moving down */
                    break;
                case ENEMY_HUMANOID:
                    e->tile_base = TILE_HUMANOID;
                    e->dx = 0;      /* Slow approach: movement applied by AI */
                    e->dy = 0;
                    e->ai_state = 1; /* Start drifting down */
                    break;
                case ENEMY_CATFISH:
                    e->tile_base = TILE_CATFISH;
                    e->dx = -1;
                    e->dy = 0;
                    e->ai_state = 1;
                    break;
                case ENEMY_DRAGONFLY:
                    e->tile_base = TILE_HORNET; /* Reuse hornet tiles */
                    e->dx = -2;     /* Faster than hornet */
                    e->dy = 2;      /* Wider oscillation */
                    break;
                case ENEMY_SOLDIER:
                    e->tile_base = TILE_HUMANOID; /* Reuse humanoid tiles */
                    e->dx = 0;
                    e->dy = 0;
                    e->ai_state = 1;
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

/* Hornet AI: constant leftward flight with vertical oscillation.
 * Original: DX~-1/frame, DY oscillates +-1 with period ~60 frames.
 * The hornet flies in a gentle sine-wave pattern. */
static void enemy_ai_hornet(Enemy *e) {
    e->ai_timer++;
    if (e->ai_timer >= HORNET_Y_HALF_PERIOD) {
        e->ai_timer = 0;
        e->dy = -e->dy; /* Reverse vertical direction */
    }
    /* dx stays at -1 (set at spawn), applied every frame */
}

/* Crow AI: fast diagonal flight, always moving left and upward.
 * Original: DX~-2/frame, DY~-1/frame (diagonal). Short lifetime.
 * No state machine needed -- constant velocity. */
static void enemy_ai_crow(Enemy *e) {
    (void)e; /* No AI changes needed -- constant velocity */
}

/* Orc AI: slow left patrol with Y oscillation, shoots aimed at player.
 * Original: updates every 8 frames, DX=-1/tick, DY oscillates +-1/tick.
 * Slow patrol with long Y oscillation period (~300 frames full cycle).
 * Shoots projectile aimed toward player every ~90 frames. */
static void enemy_ai_orc(Enemy *e) {
    int8_t aim_dx;
    int8_t aim_dy;

    e->ai_timer++;

    /* Slow X drift: move left by 1 every TICK_SLOW frames */
    if ((e->ai_timer & (TICK_SLOW - 1)) == 0) {
        e->dx = -1;
    } else {
        e->dx = 0;
    }

    /* Y oscillation: reverse direction every ORC_Y_HALF_PERIOD frames.
     * ai_state: 0 = moving up (dy=-1), 1 = moving down (dy=+1) */
    if (e->ai_timer >= ORC_Y_HALF_PERIOD) {
        e->ai_timer = 0;
        e->ai_state ^= 1; /* Toggle direction */
    }

    /* Apply Y movement every TICK_SLOW frames (slow patrol) */
    if ((e->ai_timer & (TICK_SLOW - 1)) == 0) {
        e->dy = (e->ai_state == 1) ? 1 : -1;
    } else {
        e->dy = 0;
    }

    /* Shooting: aimed at player position */
    e->shoot_cd--;
    if (e->shoot_cd == 0) {
        {
                uint8_t cd = ENEMY_SHOOT_CD - (game_stage - 1) * 8;
                e->shoot_cd = (cd < 40) ? 40 : cd;
            }

        /* Compute aimed direction toward player (simplified) */
        aim_dx = -1; /* Default: shoot left */
        aim_dy = 0;
        if (e->x > player.x + 16) {
            aim_dx = -2;
        } else if (e->x + 16 < player.x) {
            aim_dx = 2;
        }
        if (e->y + 8 < player.y) {
            aim_dy = 1;
        } else if (e->y > player.y + 8) {
            aim_dy = -1;
        }

        projectile_spawn_enemy(e->x, e->y + 4, aim_dx, aim_dy);
    }
}

/* Humanoid AI: slow approach with long Y drift periods, shoots at player.
 * Original: similar to orc but drifts in one Y direction for longer
 * before reversing (half-period ~100 frames vs orc's ~75).
 * Also shoots aimed at player every ~90 frames. */
static void enemy_ai_humanoid(Enemy *e) {
    int8_t aim_dx;
    int8_t aim_dy;

    e->ai_timer++;

    /* Slow X drift: move left by 1 every TICK_SLOW frames */
    if ((e->ai_timer & (TICK_SLOW - 1)) == 0) {
        e->dx = -1;
    } else {
        e->dx = 0;
    }

    /* Y drift: longer period than orc, stays in one direction longer.
     * ai_state: 0 = moving up, 1 = moving down */
    if (e->ai_timer >= HUMANOID_Y_HALF_PERIOD) {
        e->ai_timer = 0;
        e->ai_state ^= 1;
    }

    /* Apply Y movement every TICK_SLOW frames */
    if ((e->ai_timer & (TICK_SLOW - 1)) == 0) {
        e->dy = (e->ai_state == 1) ? 1 : -1;
    } else {
        e->dy = 0;
    }

    /* Shooting: aimed at player */
    e->shoot_cd--;
    if (e->shoot_cd == 0) {
        {
                uint8_t cd = ENEMY_SHOOT_CD - (game_stage - 1) * 8;
                e->shoot_cd = (cd < 40) ? 40 : cd;
            }

        aim_dx = -1;
        aim_dy = 0;
        if (e->x > player.x + 16) {
            aim_dx = -2;
        } else if (e->x + 16 < player.x) {
            aim_dx = 2;
        }
        if (e->y + 8 < player.y) {
            aim_dy = 1;
        } else if (e->y > player.y + 8) {
            aim_dy = -1;
        }

        projectile_spawn_enemy(e->x, e->y + 4, aim_dx, aim_dy);
    }
}

/* Catfish AI: slow, tanky, shoots frequently.
 * Drifts left slowly with gentle vertical oscillation.
 * Fires aimed shots more often than other enemies. */
#define CATFISH_SHOOT_CD   60
#define CATFISH_Y_HALF_P   40
static void enemy_ai_catfish(Enemy *e) {
    int8_t aim_dx;
    int8_t aim_dy;

    e->ai_timer++;

    /* Slow leftward drift */
    e->dx = -1;

    /* Gentle Y oscillation */
    if (e->ai_timer >= CATFISH_Y_HALF_P) {
        e->ai_timer = 0;
        e->ai_state ^= 1;
    }
    e->dy = (e->ai_state == 1) ? 1 : -1;

    /* Frequent aimed shooting */
    e->shoot_cd--;
    if (e->shoot_cd == 0) {
        e->shoot_cd = CATFISH_SHOOT_CD;

        aim_dx = (e->x > player.x + 8) ? -3 : 3;
        aim_dy = 0;
        if (e->y + 8 < player.y) aim_dy = 1;
        else if (e->y > player.y + 8) aim_dy = -1;

        projectile_spawn_enemy(e->x, e->y + 4, aim_dx, aim_dy);
        /* Sometimes fire a second shot diagonally */
        if (e->ai_timer & 0x04) {
            projectile_spawn_enemy(e->x, e->y + 12, aim_dx, aim_dy ? -aim_dy : 1);
        }
    }
}

/* Dragonfly AI: fast dive toward player Y, pull up, repeat */
static void enemy_ai_dragonfly(Enemy *e) {
    e->ai_timer++;
    e->dx = -2; /* Fast leftward */

    /* Dive toward player Y, then pull away */
    if (e->ai_state == 0) {
        /* Dive phase */
        if (e->y < player.y) e->dy = 2;
        else e->dy = -2;
        if (e->ai_timer >= 30) {
            e->ai_state = 1;
            e->ai_timer = 0;
        }
    } else {
        /* Pull-up phase — move away from player */
        if (e->y < 60) e->dy = -1;
        else e->dy = 1;
        if (e->ai_timer >= 20) {
            e->ai_state = 0;
            e->ai_timer = 0;
        }
    }
}

/* Soldier AI: strafe left, fire aimed bursts */
#define SOLDIER_SHOOT_CD 50
static void enemy_ai_soldier(Enemy *e) {
    e->ai_timer++;

    /* Strafe: move left steadily */
    if ((e->ai_timer & (TICK_SLOW - 1)) == 0) {
        e->dx = -2; /* Faster than humanoid */
    } else {
        e->dx = 0;
    }

    /* Vertical: track player Y loosely */
    if (e->y + 8 < player.y) e->dy = 1;
    else if (e->y > player.y + 8) e->dy = -1;
    else e->dy = 0;

    /* Burst fire: 2 rapid shots */
    e->shoot_cd--;
    if (e->shoot_cd == 0 || e->shoot_cd == 5) {
        int8_t aim_dx = (e->x > player.x + 8) ? -3 : 3;
        int8_t aim_dy = 0;
        if (e->y + 8 < player.y) aim_dy = 1;
        else if (e->y > player.y + 8) aim_dy = -1;
        projectile_spawn_enemy(e->x, e->y + 4, aim_dx, aim_dy);
    }
    if (e->shoot_cd == 0) {
        uint8_t cd = SOLDIER_SHOOT_CD - (game_stage - 1) * 6;
        e->shoot_cd = (cd < 25) ? 25 : cd;
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

        /* Death animation: flash for 12 frames then remove */
        if (e->hp == 0 && e->hit_flash > 0) {
            e->hit_flash--;
            if (e->hit_flash == 0) {
                e->type = ENEMY_NONE;
                if (enemy_count > 0) enemy_count--;
            }
            continue; /* Skip AI/movement during death */
        }

        /* AI -- each type has its own function */
        switch (e->type) {
            case ENEMY_HORNET:   enemy_ai_hornet(e);   break;
            case ENEMY_CROW:     enemy_ai_crow(e);     break;
            case ENEMY_ORC:      enemy_ai_orc(e);      break;
            case ENEMY_HUMANOID: enemy_ai_humanoid(e);  break;
            case ENEMY_CATFISH:  enemy_ai_catfish(e);   break;
            case ENEMY_DRAGONFLY: enemy_ai_dragonfly(e); break;
            case ENEMY_SOLDIER:  enemy_ai_soldier(e);  break;
        }

        /* Movement (dx/dy set by AI each frame) */
        new_x = (uint8_t)((int16_t)e->x + e->dx);
        new_y = (int16_t)e->y + e->dy;

        /* Clamp Y to playable area */
        if (new_y < 16)  new_y = 16;
        if (new_y > 128) new_y = 128;
        e->y = (uint8_t)new_y;

        /* Remove if off-screen left (unsigned wrap: x > 200) */
        if (new_x > 200) {
            e->type = ENEMY_NONE;
            if (enemy_count > 0) enemy_count--;
            continue;
        }
        e->x = new_x;

        /* Check hit by player projectile */
        if (projectile_check_hit(e->x, e->y, 16, 16)) {
            e->hp--;
            e->hit_flash = 6;
            sound_enemy_hit();
            music_sfx_ch4(8);  // yield Ch4 drums during enemy hit SFX
            if (e->hp == 0) {
                // Score: varies by enemy type
                game.score += (e->type >= ENEMY_ORC) ? 20 : 10;
                // Item drop: ~25% chance
                {
                    uint8_t drop_roll = (game.progress * 7 + e->x) & 0x0F;
                    if (drop_roll < 4) {
                        uint8_t item = (drop_roll < 2) ? ITEM_FLASH_BOMB : ITEM_POTION;
                        itemmenu_add_item(item);
                    }
                }
                // Start death animation (12 frames of flash)
                e->hit_flash = 12;
                e->dx = 0;
                e->dy = 0;
            }
        }

        /* Animation */
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
        // Hit flash: use palette 0 (decrement handled in enemy_update)
        if (e->hit_flash > 0) {
            flags = 0;
        } else {
            flags = e->palette & 0x07;
        }

        // Face toward Sara (flip ground enemies when Sara is left)
        {
            uint8_t tl, tr, bl, br;
            if (e->x > player.x + 8 &&
                e->type >= ENEMY_ORC && e->type != ENEMY_DRAGONFLY) {
                flags |= S_FLIPX;
                tl = tile + 1; tr = tile;
                bl = tile + 3; br = tile + 2;
            } else {
                tl = tile; tr = tile + 1;
                bl = tile + 2; br = tile + 3;
            }
            set_sprite_tile(oam_base, tl);
            set_sprite_prop(oam_base, flags);
            move_sprite(oam_base, sx, sy);
            set_sprite_tile(oam_base + 1, tr);
            set_sprite_prop(oam_base + 1, flags);
            move_sprite(oam_base + 1, sx + 8, sy);
            set_sprite_tile(oam_base + 2, bl);
            set_sprite_prop(oam_base + 2, flags);
            move_sprite(oam_base + 2, sx, sy + 8);
            set_sprite_tile(oam_base + 3, br);
            set_sprite_prop(oam_base + 3, flags);
            move_sprite(oam_base + 3, sx + 8, sy + 8);
        }
    }
}

uint8_t enemy_check_player_hit(uint8_t px, uint8_t py) {
    uint8_t i;
    Enemy *e;

    for (i = 0; i < MAX_ENEMIES; i++) {
        e = &enemies[i];
        if (e->type == ENEMY_NONE) continue;
        if (e->hp == 0) continue;  // Skip dying enemies

        if (px + 12 > e->x + 2 && px + 2 < e->x + 14 &&
            py + 12 > e->y + 2 && py + 2 < e->y + 14) {
            return 1;
        }
    }
    return 0;
}
