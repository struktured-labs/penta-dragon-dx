#include "audio/sfx.h"
#include "core/rng.h"
#include "core/types.h"
#include "game/combat.h"
#include "game/enemy_ai.h"
#include "game/entity.h"
#include "game/pickup.h"
#include "game/player.h"
#include "game/run_state.h"
#include "render/tiles.h"
#include "content.h"

// Global hit-stop: freezes the room loop for a few frames on impact for weight.
u8 g_hitstop;

// Knock an enemy 3px along a bullet's travel direction, unless it's too poised
// (bosses, heavy enemies). Blocked by walls via enemy_try_step.
static void knockback_enemy(entity_t *e, i8 bvx, i8 bvy, u8 poise) {
    u8 n;
    if (poise >= 3) return;                 // heavy: immovable
    {
        i8 kx = (bvx > 0) ? 1 : (bvx < 0) ? -1 : 0;
        i8 ky = (bvy > 0) ? 1 : (bvy < 0) ? -1 : 0;
        for (n = 0; n < 3; ++n) enemy_try_step(e, kx, ky);
    }
}

u8 combat_resolve(void) {
    u8 i, j;
    u8 player_died = 0;

    // Tick down per-frame timers
    if (player.iframes > 0) player.iframes--;

    // 1) Player-projectile -> enemy collisions
    for (i = 0; i < MAX_ENTITIES; ++i) {
        if (!(entities[i].flags & EF_ACTIVE)) continue;
        if (entities[i].type   != ENT_PROJECTILE) continue;
        if (!(entities[i].flags & EF_PLAYER_PROJ)) continue;
        for (j = 0; j < MAX_ENTITIES; ++j) {
            u8 eid, weakness, poise, dmg;
            if (j == i) continue;
            if (!(entities[j].flags & EF_ACTIVE)) continue;
            if (entities[j].type != ENT_ENEMY) continue;
            if (!aabb_overlap_ee(&entities[i], &entities[j])) continue;

            eid      = entities[j].ai_data[0];
            weakness = (eid < N_ENEMIES) ? enemies[eid].stats.weakness : 0;
            poise    = (eid < N_ENEMIES) ? enemies[eid].stats.poise    : 0;

            // Per-hit damage: base + elemental x2 (weapon element in
            // projectile ai_data[1]) + crit x2 (LCK * 5% chance).
            dmg = entities[i].damage;
            if (entities[i].ai_data[1] & weakness) dmg = (u8)(dmg << 1);
            if (rng_range(100) < (u8)(player.lck * 5)) dmg = (u8)(dmg << 1);
            if (dmg == 0) dmg = 1;

            {
                // Apply damage
                if (entities[j].hp > dmg) {
                    entities[j].hp = (u8)(entities[j].hp - dmg);
                    entities[j].ai_data[7] = 4;    // hit-flash frames
                    knockback_enemy(&entities[j], entities[i].vx, entities[i].vy, poise);
                    if (g_hitstop < 1) g_hitstop = 1;
                    sfx_play(SFX_HIT);
                } else {
                    sfx_play(SFX_DEATH);
                    if (g_hitstop < 2) g_hitstop = 2;
                    {
                        if (eid < N_ENEMIES) {
                            u16 s = run_state.score + (u16)enemies[eid].stats.score;
                            run_state.score = s;
                        }
                        run_state.enemies_killed++;
                        if (eid == 1) {
                            g_hitstop = 8;   // boss kill: big freeze
                            // Boss down: reward burst + unseal, or final victory
                            run_state.bosses_beaten++;
                            if (run_state.bosses_beaten >= BOSSES_TO_WIN) {
                                run_state.victory = 1;
                            } else {
                                run_state.pending_unseal = 1;
                            }
                            pickup_spawn(PICKUP_HEART_HALF, entities[j].x - FIX8(8), entities[j].y);
                            pickup_spawn(PICKUP_HEART_HALF, entities[j].x + FIX8(16), entities[j].y);
                            pickup_spawn(PICKUP_COIN_5, entities[j].x, entities[j].y - FIX8(8));
                            pickup_spawn(PICKUP_COIN_5, entities[j].x, entities[j].y + FIX8(16));
                        }
                    }
                    // Impact FX at enemy position
                    fx_spawn(SPR_FX_IMPACT, 2,
                        (i16)FIX8_TO_INT(entities[j].x),
                        (i16)FIX8_TO_INT(entities[j].y), 8);
                    pickup_roll_drop(entities[j].x, entities[j].y);
                    entity_kill(j);
                }
                // Impact FX at bullet position (spawn on every hit, even non-kill)
                fx_spawn(SPR_FX_IMPACT, 2,
                    (i16)FIX8_TO_INT(entities[i].x),
                    (i16)FIX8_TO_INT(entities[i].y), 4);
                // Projectile pierce
                if (entities[i].hp <= 1) {
                    entity_kill(i);
                    break;     // this projectile is dead, move on
                } else {
                    entities[i].hp--;
                }
            }
        }
    }

    // 2) Pickup collisions (always processed; doesn't require iframes)
    pickup_check_player_collision();

    // 3) Enemy bodies AND enemy projectiles -> player (respects iframes)
    if (player.iframes == 0) {
        for (i = 0; i < MAX_ENTITIES; ++i) {
            u8 hostile;
            if (!(entities[i].flags & EF_ACTIVE)) continue;
            hostile = (entities[i].type == ENT_ENEMY)
                || (entities[i].type == ENT_PROJECTILE
                    && !(entities[i].flags & EF_PLAYER_PROJ));
            if (!hostile) continue;
            if (aabb_overlap_player(&entities[i])) {
                u8 was_projectile = (entities[i].type == ENT_PROJECTILE);
                // DEF soaks incoming damage (min 1 half-heart gets through)
                u8 taken = (entities[i].damage > player.def)
                    ? (u8)(entities[i].damage - player.def) : 1;
                if (player.hp > taken) {
                    player.hp = (u8)(player.hp - taken);
                    player.iframes = 30;
                    g_hitstop = 3;
                    sfx_play(SFX_HURT);
                } else {
                    player.hp = 0;
                    player_died = 1;
                }
                if (was_projectile) entity_kill(i);   // bullet spent
                break;   // one hit per frame
            }
        }
    }

    return player_died;
}
