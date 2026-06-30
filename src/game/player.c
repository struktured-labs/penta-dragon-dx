#include <string.h>

#include "core/types.h"
#include "game/player.h"
#include "content.h"

player_state_t player;

void player_clear(void) {
    u8 i;
    player.class_id = 0xFF;
    player.hp_max = player.hp = 0;
    player.mp_max = player.mp = 0;
    player.atk = player.def = player.spd = player.lck = 0;
    player.x = player.y = 0;
    player.facing = FACE_S;
    player.anim_frame = 0;
    player.iframes = 0;
    player.coins = 0;
    player.active_item   = 0xFF;
    player.active_charge = 0;
    player.starter_weapon = 0xFF;
    for (i = 0; i < INVENTORY_SLOTS; ++i) player.inventory[i] = 0xFF;
    player.score_lo = player.score_hi = 0;
}

void player_init_from_class(u8 class_id) {
    player_clear();
    if (class_id >= N_CLASSES) return;

    {
        const class_def_t *c = &classes[class_id];
        player.class_id = c->id;
        player.hp_max   = c->base_stats.hp_max;
        player.hp       = c->base_stats.hp_max;
        player.mp_max   = c->base_stats.mp_max;
        player.mp       = c->base_stats.mp_max;
        player.atk      = c->base_stats.atk;
        player.def      = c->base_stats.def;
        player.spd      = c->base_stats.spd;
        player.lck      = 0;
        player.starter_weapon = (u8)c->starter_weapon;
        player.active_item    = (u8)c->signature_active;
    }
}
