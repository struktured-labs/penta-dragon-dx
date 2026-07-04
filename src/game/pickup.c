#include <gb/gb.h>

#include "audio/sfx.h"
#include "core/types.h"
#include "core/rng.h"
#include "game/entity.h"
#include "game/pickup.h"
#include "game/player.h"
#include "render/hud.h"
#include "render/tiles.h"
#include "content.h"

u8 pickup_spawn(u8 kind, fix8_t x, fix8_t y) {
    u8 idx = entity_spawn(ENT_PICKUP);
    if (idx == 0xFF) return 0xFF;
    {
        entity_t *e = &entities[idx];
        e->x = x;
        e->y = y;
        e->vx = e->vy = 0;
        e->ai_data[0] = kind;
        e->hitbox     = (6 << 4) | 6;
        e->damage     = 0;
        e->hp         = 1;
        e->state_timer = 240;    // despawn after 4 seconds
        switch (kind) {
            case PICKUP_HEART_HALF:
                e->sprite_tile = SPR_HEART;
                e->palette     = 0x04;   // OBJ palette 4 (heart red)
                break;
            case PICKUP_COIN_1:
            case PICKUP_COIN_5:
            default:
                e->sprite_tile = SPR_COIN;
                e->palette     = 0x05;   // OBJ palette 5 (coin gold)
                break;
        }
    }
    return idx;
}

u8 pickup_spawn_item(u8 item_index, fix8_t x, fix8_t y) {
    u8 idx = pickup_spawn(PICKUP_ITEM, x, y);
    if (idx != 0xFF) {
        entities[idx].ai_data[1]  = item_index;
        entities[idx].sprite_tile = SPR_ITEM_ORB;
        entities[idx].palette     = 0x05;      // gold
        entities[idx].state_timer = 255;       // items linger longest
    }
    return idx;
}

void pickup_roll_drop(fix8_t x, fix8_t y) {
    u8 r = rng_next_u8();
    if      (r < 0x40) pickup_spawn(PICKUP_HEART_HALF, x, y);   // 25%
    else if (r < 0xB3) pickup_spawn(PICKUP_COIN_1,     x, y);   // 45%
    else if (r < 0xCC) {                                        // 10%: item
        // Passive stat-boosters live at items[] indices 10..14
        pickup_spawn_item((u8)(10 + rng_range(5)), x, y);
    }
    // else: no drop (20%)
}

void pickup_update(entity_t *e, u8 idx) {
    // Shop wares are permanent until bought; state counts a retry delay.
    if (e->ai_data[0] == PICKUP_SHOP) {
        if (e->state > 0) e->state--;
        return;
    }
    if (e->state_timer == 0) { entity_kill(idx); return; }
    e->state_timer--;
}

// Apply a generated item's StatBoost effects to the live player.
static void apply_item_effects(u8 item_idx) {
    const item_def_t *it;
    u8 k;
    if (item_idx >= N_ITEMS) return;
    it = &items[item_idx];
    for (k = 0; k < it->n_effects; ++k) {
        const effect_t *ef = &it->effects[k];
        if (ef->kind != EFFECT_STAT_BOOST) continue;
        switch (ef->d0) {
            case STAT_HP:
                player.hp_max = (u8)(player.hp_max + ef->d1);
                if (player.hp_max > 24) player.hp_max = 24;
                player.hp = (u8)(player.hp + ef->d1);
                if (player.hp > player.hp_max) player.hp = player.hp_max;
                break;
            case STAT_MP:
                player.mp_max = (u8)(player.mp_max + ef->d1);
                if (player.mp_max > 20) player.mp_max = 20;
                break;
            case STAT_ATK:
                if (player.atk < 15) player.atk = (u8)(player.atk + ef->d1);
                break;
            case STAT_DEF:
                if (player.def < 10) player.def = (u8)(player.def + ef->d1);
                break;
            case STAT_SPD:
                if (player.spd < 9) player.spd = (u8)(player.spd + ef->d1);
                break;
            case STAT_LCK:
                if (player.lck < 10) player.lck = (u8)(player.lck + ef->d1);
                break;
        }
    }
    hud_redraw_all();
}

u8 pickup_check_player_collision(void) {
    u8 i;
    u8 any = 0;
    for (i = 0; i < MAX_ENTITIES; ++i) {
        if (!(entities[i].flags & EF_ACTIVE)) continue;
        if (entities[i].type != ENT_PICKUP)   continue;
        if (aabb_overlap_player(&entities[i])) {
            switch (entities[i].ai_data[0]) {
                case PICKUP_HEART_HALF:
                    if (player.hp < player.hp_max) {
                        player.hp = (u8)(player.hp + 1);
                        if (player.hp > player.hp_max) player.hp = player.hp_max;
                        hud_redraw_hp();
                    }
                    sfx_play(SFX_HEART);
                    break;
                case PICKUP_COIN_1:
                    if (player.coins < 999) player.coins++;
                    hud_redraw_coins();
                    sfx_play(SFX_COIN);
                    break;
                case PICKUP_COIN_5:
                    player.coins = (u16)(player.coins + 5);
                    if (player.coins > 999) player.coins = 999;
                    hud_redraw_coins();
                    sfx_play(SFX_COIN);
                    break;
                case PICKUP_ITEM:
                    apply_item_effects(entities[i].ai_data[1]);
                    sfx_play(SFX_HEART);
                    break;
                case PICKUP_SHOP: {
                    // Walk into a ware to buy it. Not enough coins → error
                    // beep with a retry delay so it doesn't spam.
                    u8 price = entities[i].ai_data[2];
                    if (player.coins >= price) {
                        player.coins = (u16)(player.coins - price);
                        hud_redraw_coins();
                        switch (entities[i].ai_data[1]) {
                            case WARE_HEART:
                                player.hp = (u8)(player.hp + 2);
                                if (player.hp > player.hp_max) player.hp = player.hp_max;
                                hud_redraw_hp();
                                break;
                            case WARE_ITEM:
                                apply_item_effects((u8)(10 + rng_range(5)));
                                break;
                            case WARE_BIG:
                                apply_item_effects(10);   // Iron Heart
                                break;
                        }
                        sfx_play(SFX_COIN);
                        entity_kill(i);
                    } else if (entities[i].state == 0) {
                        sfx_play(SFX_HURT);
                        entities[i].state = 45;   // retry delay
                    }
                    any = 1;
                    continue;
                }
            }
            entity_kill(i);
            any = 1;
        }
    }
    return any;
}
