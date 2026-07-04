#include <gb/gb.h>
#include <string.h>

#include "core/types.h"
#include "game/entity.h"
#include "game/player.h"
#include "game/projectile.h"
#include "game/enemy_ai.h"
#include "game/pickup.h"

entity_t entities[MAX_ENTITIES];

// 8-direction deltas: 0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW
const i8 dir8_dx[8] = {  0, +1, +1, +1,  0, -1, -1, -1 };
const i8 dir8_dy[8] = { -1, -1,  0, +1, +1, +1,  0, -1 };

static u8 hitbox_w(const entity_t *e) { return (e->hitbox >> 4) & 0x0F; }
static u8 hitbox_h(const entity_t *e) { return  e->hitbox       & 0x0F; }

void entity_init_all(void) {
    u8 i;
    memset(entities, 0, sizeof(entities));
    // Park entity sprites (slots 4..35) + boss metasprite overlay (36..39)
    for (i = 4; i < 40; ++i) {
        move_sprite(i, 0, 0);
    }
}

u8 entity_spawn(u8 type) {
    u8 i;
    for (i = 0; i < MAX_ENTITIES; ++i) {
        if (!(entities[i].flags & EF_ACTIVE)) {
            memset(&entities[i], 0, sizeof(entity_t));
            entities[i].type    = type;
            entities[i].flags   = EF_ACTIVE | EF_ALIVE;
            // OAM slots 0-3 reserved for player metasprite; entities use 4+
            entities[i].oam_slot = (u8)(4 + i);
            return i;
        }
    }
    return 0xFF;
}

void entity_kill(u8 idx) {
    if (idx >= MAX_ENTITIES) return;
    entities[idx].flags &= (u8)~(EF_ACTIVE | EF_ALIVE);
    entities[idx].type   = ENT_NONE;
    move_sprite(entities[idx].oam_slot, 0, 0);   // hide
}

u8 aabb_overlap_ee(const entity_t *a, const entity_t *b) {
    i16 ax = FIX8_TO_INT(a->x), ay = FIX8_TO_INT(a->y);
    i16 bx = FIX8_TO_INT(b->x), by = FIX8_TO_INT(b->y);
    u8  aw = hitbox_w(a),       ah = hitbox_h(a);
    u8  bw = hitbox_w(b),       bh = hitbox_h(b);
    if (ax + (i16)aw <= bx) return 0;
    if (bx + (i16)bw <= ax) return 0;
    if (ay + (i16)ah <= by) return 0;
    if (by + (i16)bh <= ay) return 0;
    return 1;
}

u8 aabb_overlap_player(const entity_t *e) {
    i16 ex = FIX8_TO_INT(e->x), ey = FIX8_TO_INT(e->y);
    i16 px = (i16)player.x, py = (i16)player.y;     // player is i16 pixels
    u8  ew = hitbox_w(e), eh = hitbox_h(e);
    px += 1; py += 1;
    if (px + 6 <= ex) return 0;
    if (ex + (i16)ew <= px) return 0;
    if (py + 6 <= ey) return 0;
    if (ey + (i16)eh <= py) return 0;
    return 1;
}

void entity_update_all(u8 keys, u8 pressed) {
    u8 i;
    for (i = 0; i < MAX_ENTITIES; ++i) {
        if (!(entities[i].flags & EF_ACTIVE)) continue;
        switch (entities[i].type) {
            case ENT_PROJECTILE: projectile_update(&entities[i], i); break;
            case ENT_ENEMY:      enemy_update(&entities[i], i);      break;
            case ENT_PICKUP:     pickup_update(&entities[i], i);     break;
            case ENT_FX:         fx_update(&entities[i], i);         break;
            default: break;
        }
        keys; pressed;
    }
}

u8 fx_spawn(u8 sprite_tile, u8 palette, i16 px, i16 py, u8 ttl) {
    u8 idx = entity_spawn(ENT_FX);
    if (idx == 0xFF) return 0xFF;
    {
        entity_t *e = &entities[idx];
        e->x = FIX8(px);
        e->y = FIX8(py);
        e->sprite_tile = sprite_tile;
        e->palette     = palette;
        e->state_timer = ttl;
        e->hitbox      = 0;
        e->damage      = 0;
    }
    return idx;
}

void fx_update(entity_t *e, u8 idx) {
    if (e->state_timer == 0) { entity_kill(idx); return; }
    e->state_timer--;
}

void entity_draw_all(void) {
    u8 i;
    u8 boss_drawn = 0;
    for (i = 0; i < MAX_ENTITIES; ++i) {
        if (!(entities[i].flags & EF_ACTIVE)) {
            continue;
        }
        // Boss (enemy content id 1) renders as a full 16x16 metasprite on
        // the reserved OAM slots 36-39; its own entity slot stays hidden.
        if (entities[i].type == ENT_ENEMY && entities[i].ai_data[0] == 1) {
            u8 sx = (u8)(FIX8_TO_INT(entities[i].x) + 8);
            u8 sy = (u8)(FIX8_TO_INT(entities[i].y) + 16);
            u8 pal = entities[i].palette;
            move_sprite(entities[i].oam_slot, 0, 0);
            set_sprite_tile(36, entities[i].sprite_tile);
            set_sprite_tile(37, (u8)(entities[i].sprite_tile + 1));
            set_sprite_tile(38, (u8)(entities[i].sprite_tile + 2));
            set_sprite_tile(39, (u8)(entities[i].sprite_tile + 3));
            set_sprite_prop(36, pal); set_sprite_prop(37, pal);
            set_sprite_prop(38, pal); set_sprite_prop(39, pal);
            move_sprite(36, sx,         sy);
            move_sprite(37, (u8)(sx+8), sy);
            move_sprite(38, sx,         (u8)(sy+8));
            move_sprite(39, (u8)(sx+8), (u8)(sy+8));
            boss_drawn = 1;
            continue;
        }
        set_sprite_tile(entities[i].oam_slot, entities[i].sprite_tile);
        set_sprite_prop(entities[i].oam_slot, entities[i].palette);
        move_sprite(entities[i].oam_slot,
            (u8)(FIX8_TO_INT(entities[i].x) + 8),
            (u8)(FIX8_TO_INT(entities[i].y) + 16));
    }
    if (!boss_drawn) {
        move_sprite(36, 0, 0); move_sprite(37, 0, 0);
        move_sprite(38, 0, 0); move_sprite(39, 0, 0);
    }
}
