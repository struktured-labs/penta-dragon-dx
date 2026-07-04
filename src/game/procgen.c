#include <gb/gb.h>

#include "core/types.h"
#include "core/rng.h"
#include "game/enemy_ai.h"
#include "game/entity.h"
#include "game/pickup.h"
#include "game/player.h"
#include "game/procgen.h"
#include "game/room.h"
#include "game/run_state.h"
#include "render/tiles.h"
#include "core/types.h"
#include "content.h"

u32 procgen_room_seed(u32 run_seed, u8 biome_id, u8 room_counter) {
    return run_seed ^ ((u32)biome_id << 16) ^ ((u32)room_counter * 0x9E3779B9UL);
}

// Sample an enemy from the biome's enemy_pool using cumulative weights.
static u8 pick_enemy_from_biome(const biome_def_t *bio) {
    u16 total = 0;
    u8 i;
    for (i = 0; i < bio->n_enemy_pool; ++i) total = (u16)(total + bio->enemy_pool[i].weight);
    if (total == 0) return bio->enemy_pool[0].enemy_id;
    {
        u16 roll = (u16)((rng_next() & 0xFFFFUL) % total);
        u16 acc  = 0;
        for (i = 0; i < bio->n_enemy_pool; ++i) {
            acc = (u16)(acc + bio->enemy_pool[i].weight);
            if (roll < acc) return bio->enemy_pool[i].enemy_id;
        }
    }
    return bio->enemy_pool[0].enemy_id;
}

// Place player at the door opposite the one they entered from.
static void place_player_after_entry(void) {
    u8 dir = run_state.entered_from;
    u8 tx, ty;
    if (dir == DIR_N)      { tx = ROOM_W / 2; ty = ROOM_H - 3; }
    else if (dir == DIR_S) { tx = ROOM_W / 2; ty = 2; }
    else if (dir == DIR_E) { tx = 2;          ty = ROOM_H / 2; }
    else if (dir == DIR_W) { tx = ROOM_W - 3; ty = ROOM_H / 2; }
    else                   { tx = ROOM_W / 2; ty = ROOM_H / 2; }
    player.x = (ppos_t)((i16)tx * 8);
    player.y = (ppos_t)((i16)ty * 8);
}

void procgen_generate_current_room(void) {
    const biome_def_t *bio = &biomes[run_state.biome_id];
    u32 seed = procgen_room_seed(run_state.run_seed, run_state.biome_id, run_state.room_counter);
    rng_seed(seed);

    bio;
    {
        u8 x, y;
        // A boss guards every Nth room until BOSSES_TO_WIN are down.
        u8 is_boss_room = (run_state.room_counter > 0
            && (run_state.room_counter % BOSS_EVERY_N_ROOMS) == 0
            && (u8)(run_state.room_counter / BOSS_EVERY_N_ROOMS) > run_state.bosses_beaten) ? 1 : 0;

        // Base: border walls + textured floor (plain / cracked / pebbled mix)
        for (y = 0; y < ROOM_H; ++y) {
            for (x = 0; x < ROOM_W; ++x) {
                if (y == 0 || y == ROOM_H - 1 || x == 0 || x == ROOM_W - 1) {
                    room_tilemap[y][x] = BGT_WALL;
                } else {
                    u8 r = rng_next_u8();
                    room_tilemap[y][x] =
                        (r < 38) ? BGT_FLOOR2 :        // ~15% cracked
                        (r < 64) ? BGT_FLOOR3 :        // ~10% pebbled
                                   BGT_FLOOR;
                }
            }
        }

        if (!is_boss_room) {
            room_tilemap[0][ROOM_W / 2]            = BGT_DOOR;
            room_tilemap[ROOM_H - 1][ROOM_W / 2]   = BGT_DOOR;
            room_tilemap[ROOM_H / 2][0]            = BGT_DOOR;
            room_tilemap[ROOM_H / 2][ROOM_W - 1]   = BGT_DOOR;

            // Interior obstacles. Door lanes stay clear (cols 9-11 for the
            // N/S door at col 10; rows 7-9 for the E/W door at row 8) so
            // every door remains reachable regardless of pattern.
            {
                u8 shape = (u8)(rng_next_u8() & 0x03);
                if (shape == 1) {
                    // Four pillars at quarter points
                    room_tilemap[4][4]   = BGT_PILLAR;
                    room_tilemap[4][15]  = BGT_PILLAR;
                    room_tilemap[13][4]  = BGT_PILLAR;
                    room_tilemap[13][15] = BGT_PILLAR;
                } else if (shape == 2) {
                    // Crystal clusters — up to 4, lanes + border excluded
                    u8 placed = 0, tries = 12;
                    while (placed < 4 && tries--) {
                        u8 cx = (u8)(2 + rng_range(ROOM_W - 4));
                        u8 cy = (u8)(2 + rng_range(ROOM_H - 4));
                        if (cx >= 9 && cx <= 11) continue;
                        if (cy >= 7 && cy <= 9)  continue;
                        room_tilemap[cy][cx] = BGT_CRYSTAL;
                        placed++;
                    }
                } else if (shape == 3) {
                    // Chunky pillar pairs in the corners
                    room_tilemap[4][4]   = BGT_PILLAR; room_tilemap[4][5]   = BGT_PILLAR;
                    room_tilemap[4][14]  = BGT_PILLAR; room_tilemap[4][15]  = BGT_PILLAR;
                    room_tilemap[13][4]  = BGT_PILLAR; room_tilemap[13][5]  = BGT_PILLAR;
                    room_tilemap[13][14] = BGT_PILLAR; room_tilemap[13][15] = BGT_PILLAR;
                }
                // shape 0: open room
            }

            // Rubble decoration (walkable) — 3 scatter spots
            {
                u8 i;
                for (i = 0; i < 3; ++i) {
                    u8 rx = (u8)(2 + rng_range(ROOM_W - 4));
                    u8 ry = (u8)(2 + rng_range(ROOM_H - 4));
                    if (room_tilemap[ry][rx] == BGT_FLOOR) {
                        room_tilemap[ry][rx] = BGT_RUBBLE;
                    }
                }
            }

            // Secret cracked wall — ~3 in 8 rooms hide one somewhere on the
            // border (never on a door, corner, or the E/W door row).
            if ((rng_next_u8() & 0x07) < 3) {
                u8 side = (u8)(rng_next_u8() & 0x03);
                u8 pos;
                if (side == 0) {          // north wall
                    pos = (u8)(2 + rng_range(ROOM_W - 4));
                    if (pos != ROOM_W / 2) room_tilemap[0][pos] = BGT_WALL_CRACK;
                } else if (side == 1) {   // south wall
                    pos = (u8)(2 + rng_range(ROOM_W - 4));
                    if (pos != ROOM_W / 2) room_tilemap[ROOM_H - 1][pos] = BGT_WALL_CRACK;
                } else if (side == 2) {   // west wall
                    pos = (u8)(2 + rng_range(ROOM_H - 4));
                    if (pos != ROOM_H / 2) room_tilemap[pos][0] = BGT_WALL_CRACK;
                } else {                  // east wall
                    pos = (u8)(2 + rng_range(ROOM_H - 4));
                    if (pos != ROOM_H / 2) room_tilemap[pos][ROOM_W - 1] = BGT_WALL_CRACK;
                }
            }
        }
    }

    // Clear entity table — fresh enemies per room
    entity_init_all();

    // Player position FIRST so spawn-avoidance checks the real tile
    place_player_after_entry();

    // Debug markers (HRAM)
    *(volatile u8*)0xFFFE = run_state.room_counter;
    *(volatile u8*)0xFFFD = run_state.victory;

    // Secret treasure room: no enemies, loot piled in the middle.
    if (run_state.secret_pending) {
        run_state.secret_pending = 0;
        *(volatile u8*)0xFFFC = 0x00;
        pickup_spawn(PICKUP_HEART_HALF, FIX8(72), FIX8(56));
        pickup_spawn(PICKUP_HEART_HALF, FIX8(88), FIX8(56));
        pickup_spawn(PICKUP_COIN_5,     FIX8(72), FIX8(72));
        pickup_spawn(PICKUP_COIN_5,     FIX8(88), FIX8(72));
        pickup_spawn_item((u8)(10 + rng_range(5)), FIX8(80), FIX8(64));
        player.iframes = 60;
        return;
    }

    {
        u8 is_boss_room = (run_state.room_counter > 0
            && (run_state.room_counter % BOSS_EVERY_N_ROOMS) == 0
            && (u8)(run_state.room_counter / BOSS_EVERY_N_ROOMS) > run_state.bosses_beaten) ? 1 : 0;

        if (is_boss_room) {
            *(volatile u8*)0xFFFC = 0xBB;
            u8 idx = enemy_spawn(1, (ROOM_W / 2) - 1, (ROOM_H / 2) - 1);
            if (idx != 0xFF) {
                entities[idx].sprite_tile = SPR_BOSS;
                entities[idx].hitbox      = (14 << 4) | 14;
                // Later bosses hit harder + have more HP
                entities[idx].hp = (u8)(entities[idx].hp
                    + (u8)(run_state.bosses_beaten * 30));
                entities[idx].damage = (u8)(entities[idx].damage
                    + run_state.bosses_beaten);
            }
        } else if ((run_state.room_counter % 7) == 3) {
            // MERCHANT room: three wares, no enemies. Walk into a ware
            // with enough coins to buy (heart 10 / stat item 25 / +2 max HP 40).
            *(volatile u8*)0xFFFC = 0x00;
            {
                u8 s0 = pickup_spawn(PICKUP_SHOP, FIX8(56),  FIX8(64));
                u8 s1 = pickup_spawn(PICKUP_SHOP, FIX8(80),  FIX8(64));
                u8 s2 = pickup_spawn(PICKUP_SHOP, FIX8(104), FIX8(64));
                if (s0 != 0xFF) {
                    entities[s0].ai_data[0] = PICKUP_SHOP;
                    entities[s0].ai_data[1] = WARE_HEART;
                    entities[s0].ai_data[2] = 10;
                    entities[s0].sprite_tile = SPR_HEART;
                    entities[s0].palette = 0x04;
                }
                if (s1 != 0xFF) {
                    entities[s1].ai_data[0] = PICKUP_SHOP;
                    entities[s1].ai_data[1] = WARE_ITEM;
                    entities[s1].ai_data[2] = 25;
                    entities[s1].sprite_tile = SPR_ITEM_ORB;
                    entities[s1].palette = 0x05;
                }
                if (s2 != 0xFF) {
                    entities[s2].ai_data[0] = PICKUP_SHOP;
                    entities[s2].ai_data[1] = WARE_BIG;
                    entities[s2].ai_data[2] = 40;
                    entities[s2].sprite_tile = SPR_ITEM_ORB;
                    entities[s2].palette = 0x04;
                }
            }
        } else {
            *(volatile u8*)0xFFFC = 0x00;
            // Enemy count scales with depth (1-4 early, up to 6 deep)
            u8 depth_bonus = (u8)(run_state.room_counter / 6);
            u8 enemy_count = (u8)(1 + rng_range(4) + (depth_bonus > 2 ? 2 : depth_bonus));
            u8 ptx = (u8)(player.x >> 3);
            u8 pty = (u8)(player.y >> 3);
            u8 i;
            for (i = 0; i < enemy_count; ++i) {
                u8 tx = (u8)(2 + rng_range(ROOM_W - 4));
                u8 ty = (u8)(2 + rng_range(ROOM_H - 4));
                if (!room_tile_walkable(room_tilemap[ty][tx])) continue;
                {
                    u8 dx = (tx > ptx) ? (u8)(tx - ptx) : (u8)(ptx - tx);
                    u8 dy = (ty > pty) ? (u8)(ty - pty) : (u8)(pty - ty);
                    if (dx < 3 && dy < 3) continue;
                }
                {
                    u8 eid = pick_enemy_from_biome(&biomes[run_state.biome_id]);
                    if (eid == 1) eid = 0;   // boss never spawns in normal rooms
                    enemy_spawn(eid, tx, ty);
                }
            }
        }
    }

    player.iframes = 60;    // brief invuln on room entry
}
