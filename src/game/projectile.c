#include <gb/gb.h>

#include "core/types.h"
#include "game/entity.h"
#include "game/projectile.h"
#include "game/player.h"
#include "game/room.h"
#include "render/tiles.h"

#define PROJECTILE_SPEED  3    // px/tick — slower = more visible, Penta-ish
#define PROJECTILE_TTL    75   // ~225px range = 1.4 room widths
#define PROJECTILE_DAMAGE 2

u8 projectile_spawn_player(i8 dx, i8 dy) {
    u8 idx;
    entity_t *e;
    if (dx == 0 && dy == 0) return 0xFF;
    idx = entity_spawn(ENT_PROJECTILE);
    if (idx == 0xFF) return 0xFF;
    e = &entities[idx];
    e->flags      |= EF_PLAYER_PROJ;
    e->x           = FIX8((i16)player.x + 2);
    e->y           = FIX8((i16)player.y + 2);
    e->vx          = (i8)((i16)dx * PROJECTILE_SPEED);
    e->vy          = (i8)((i16)dy * PROJECTILE_SPEED);
    e->sprite_tile = SPR_BULLET;
    e->palette     = 2;
    e->hp          = 1;
    e->state_timer = PROJECTILE_TTL;
    e->hitbox      = (7 << 4) | 7;       // 7×7 hitbox — nearly full sprite for reliable hits
    e->damage      = PROJECTILE_DAMAGE;
    // ai_data[0] = animation phase (for 2-frame flicker)
    e->ai_data[0]  = 0;
    // Muzzle flash — 6-frame FX behind bullet
    fx_spawn(SPR_FX_MUZZLE, 2, (i16)player.x + 2, (i16)player.y + 2, 6);
    return idx;
}

void projectile_update(entity_t *e, u8 idx) {
    if (e->state_timer == 0) { entity_kill(idx); return; }
    e->state_timer--;

    e->x = (fix8_t)(e->x + ((i32)e->vx << 8));   // integer px/tick, fix8 units
    e->y = (fix8_t)(e->y + ((i32)e->vy << 8));

    // Alternate sprite frames each tick for a shimmer effect
    e->ai_data[0] = (u8)(e->ai_data[0] + 1);
    e->sprite_tile = (u8)((e->ai_data[0] & 0x02) ? SPR_BULLET_B : SPR_BULLET);

    {
        i16 px = FIX8_TO_INT(e->x);
        i16 py = FIX8_TO_INT(e->y);
        if (px < 8 || px > (ROOM_W * 8 - 8)
            || py < 8 || py > (ROOM_H * 8 - 8)) {
            entity_kill(idx);
            return;
        }
        // Solid tiles (pillars, crystals, walls) stop bullets
        {
            u8 t = room_tile_at_px(px + 4, py + 4);
            if (t == BGT_WALL || t == BGT_PILLAR || t == BGT_CRYSTAL) {
                fx_spawn(SPR_FX_IMPACT, 2, px, py, 4);
                entity_kill(idx);
                return;
            }
        }
    }
}
