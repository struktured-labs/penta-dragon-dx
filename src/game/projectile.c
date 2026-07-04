#include <gb/gb.h>

#include "audio/sfx.h"
#include "core/types.h"
#include "game/entity.h"
#include "game/projectile.h"
#include "game/player.h"
#include "game/room.h"
#include "render/tiles.h"
#include "content.h"

// Element bitmask stamped onto the next player shot (1=Fire 2=Ice 4=Lit
// 8=Shadow 16=Poison). Set by the fire code per class/weapon; combat
// doubles damage when it matches the target's weakness.
u8 g_shot_element;

u8 projectile_spawn_player(i8 dx, i8 dy, u8 damage, u8 kind) {
    u8 idx;
    entity_t *e;
    u8 speed, ttl, pierce;
    if (dx == 0 && dy == 0) return 0xFF;

    // Kind shapes the projectile's physics:
    switch (kind) {
        case PROJ_SPIKE:      // melee slash: fast, very short reach
            speed = 4; ttl = 12; pierce = 1; break;
        case PROJ_SHURIKEN:   // pierces 2 enemies
            speed = 3; ttl = 60; pierce = 2; break;
        case PROJ_BUBBLE:     // slow drifting, pierces, long-lived
            speed = 2; ttl = 120; pierce = 2; break;
        default:              // bullet/bolt baseline
            speed = 3; ttl = 75; pierce = 1; break;
    }

    idx = entity_spawn(ENT_PROJECTILE);
    if (idx == 0xFF) return 0xFF;
    e = &entities[idx];
    e->flags      |= EF_PLAYER_PROJ;
    e->x           = FIX8((i16)player.x + 2);
    e->y           = FIX8((i16)player.y + 2);
    e->vx          = (i8)((i16)dx * speed);
    e->vy          = (i8)((i16)dy * speed);
    e->sprite_tile = SPR_BULLET;
    e->palette     = 2;
    e->hp          = pierce;
    e->state_timer = ttl;
    e->hitbox      = (7 << 4) | 7;
    e->damage      = damage;
    e->ai_data[0]  = 0;              // anim phase
    e->ai_data[1]  = g_shot_element; // element for weakness bonus
    fx_spawn(SPR_FX_MUZZLE, 2, (i16)player.x + 2, (i16)player.y + 2, 6);
    sfx_play(SFX_FIRE);
    return idx;
}

u8 projectile_spawn_enemy(i16 px, i16 py, i8 dx, i8 dy, u8 damage) {
    u8 idx;
    entity_t *e;
    if (dx == 0 && dy == 0) return 0xFF;
    idx = entity_spawn(ENT_PROJECTILE);
    if (idx == 0xFF) return 0xFF;
    e = &entities[idx];
    // No EF_PLAYER_PROJ: combat treats it as hostile
    e->x           = FIX8(px);
    e->y           = FIX8(py);
    e->vx          = (i8)((i16)dx * 2);   // slower than player shots
    e->vy          = (i8)((i16)dy * 2);
    e->sprite_tile = SPR_BULLET_B;
    e->palette     = 3;                   // crawler blue — reads hostile
    e->hp          = 1;
    e->state_timer = 110;
    e->hitbox      = (6 << 4) | 6;
    e->damage      = damage;
    return idx;
}

void projectile_update(entity_t *e, u8 idx) {
    if (e->state_timer == 0) { entity_kill(idx); return; }
    e->state_timer--;

    e->x = (fix8_t)(e->x + ((i32)e->vx << 8));   // integer px/tick, fix8 units
    e->y = (fix8_t)(e->y + ((i32)e->vy << 8));

    // Player bullets shimmer between 2 frames; enemy bullets stay static
    if (e->flags & EF_PLAYER_PROJ) {
        e->ai_data[0] = (u8)(e->ai_data[0] + 1);
        e->sprite_tile = (u8)((e->ai_data[0] & 0x02) ? SPR_BULLET_B : SPR_BULLET);
    }

    {
        i16 px = FIX8_TO_INT(e->x);
        i16 py = FIX8_TO_INT(e->y);
        // Sample the tile FIRST (clamped into bounds) so a shot that reaches
        // a north/west border tile still triggers the crack — the old order
        // despawned on the OOB guard before ever testing the wall, making
        // ~half of all cracked walls unshootable.
        i16 sx = px + 4, sy = py + 4;
        u8 t;
        if (sx < 0) sx = 0; else if (sx > (ROOM_W * 8 - 1)) sx = ROOM_W * 8 - 1;
        if (sy < 0) sy = 0; else if (sy > (ROOM_H * 8 - 1)) sy = ROOM_H * 8 - 1;
        t = room_tile_at_px(sx, sy);

        if (t == BGT_WALL_CRACK && (e->flags & EF_PLAYER_PROJ)) {
            room_open_secret((u8)(sx >> 3), (u8)(sy >> 3));
            fx_spawn(SPR_FX_IMPACT, 2, px, py, 8);
            entity_kill(idx);
            return;
        }
        if (t == BGT_WALL || t == BGT_PILLAR || t == BGT_CRYSTAL
            || t == BGT_WALL_CRACK) {
            fx_spawn(SPR_FX_IMPACT, 2, px, py, 4);
            entity_kill(idx);
            return;
        }
        // Off-screen / past the room edge: despawn
        if (px < 8 || px > (ROOM_W * 8 - 8)
            || py < 8 || py > (ROOM_H * 8 - 8)) {
            entity_kill(idx);
            return;
        }
    }
}
