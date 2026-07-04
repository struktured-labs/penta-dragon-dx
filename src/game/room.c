// ROOM — top-down gameplay scene. Phase 5: spawns N enemies, supports
// 4-dir movement, 8-dir B-button fire, wall collision, combat resolution.
// Phase 7 wires procgen to fill from biome.room_template_pool.

#include <gb/gb.h>
#include <gb/cgb.h>

#include "audio/music.h"
#include "audio/sfx.h"
#include "core/types.h"
#include "core/rng.h"
#include "game/combat.h"
#include "game/entity.h"
#include "game/entity.h"
#include "game/enemy_ai.h"
#include "game/loop.h"
#include "game/pickup.h"
#include "game/player.h"
#include "game/procgen.h"
#include "game/projectile.h"
#include "game/room.h"
#include "game/run_state.h"
#include "render/class_palettes.h"
#include "render/hud.h"
#include "render/palette.h"
#include "render/tiles.h"
#include "content.h"

u8 room_tilemap[ROOM_H][ROOM_W];

static u8 room_paused;
static u8 room_resume_flag;   // set by room_request_resume: skip procgen next enter
// Secret door opened by shooting a cracked wall this room (0xFF = none)
static u8 secret_door_x = 0xFF;
static u8 secret_door_y = 0xFF;

void room_request_resume(void) { room_resume_flag = 1; }

// Three stage themes, indexed by run_state.bosses_beaten (clamped 0-2).
// Each defines floor / wall / crystal / door palettes; the crack palette
// stays amber across stages so the "shoot me" signal is consistent.
// [stage][floor|wall|crystal|door][color 0-3]
#define STAGE_COUNT 3
static const u16 stage_pal[STAGE_COUNT][4][4] = {
    // Stage 0 — Crystal Caverns (cool blue)
    {
        { BGR555( 4, 3, 6), BGR555(11,10,15), BGR555(17,16,22), BGR555(23,22,28) },
        { BGR555( 1, 1, 3), BGR555( 5, 5,11), BGR555( 9,10,17), BGR555(16,18,26) },
        { BGR555( 2, 0, 5), BGR555(16, 5,22), BGR555(10,22,29), BGR555(31,30,31) },
        { BGR555( 1, 1, 2), BGR555(10, 7, 2), BGR555(18,13, 3), BGR555(28,21, 6) },
    },
    // Stage 1 — Ember Depths (warm red/orange, molten)
    {
        { BGR555( 7, 2, 2), BGR555(16, 7, 5), BGR555(23,12, 7), BGR555(30,20,12) },
        { BGR555( 3, 0, 0), BGR555(11, 3, 2), BGR555(17, 6, 3), BGR555(26,12, 6) },
        { BGR555( 5, 1, 0), BGR555(28,10, 2), BGR555(31,22, 4), BGR555(31,31,20) },
        { BGR555( 2, 1, 0), BGR555(12, 8, 2), BGR555(22,15, 3), BGR555(31,26, 8) },
    },
    // Stage 2 — Void Sanctum (deep purple/toxic green, final)
    {
        { BGR555( 4, 2, 7), BGR555(10, 6,14), BGR555(15,11,20), BGR555(20,16,26) },
        { BGR555( 2, 0, 4), BGR555( 7, 2,10), BGR555(11, 5,15), BGR555(18,10,24) },
        { BGR555( 0, 4, 2), BGR555( 6,22, 8), BGR555(14,31,12), BGR555(28,31,24) },
        { BGR555( 2, 0, 3), BGR555( 8, 4,10), BGR555(16,10,20), BGR555(26,18,30) },
    },
};
// Cracked secret wall — warm amber, constant across stages.
static const u16 pal_crack[4] = {
    BGR555( 6,  2,  1), BGR555(22, 11,  3), BGR555(30, 18,  4), BGR555(31, 28, 12),
};

static u8 room_stage(void) {
    u8 s = run_state.bosses_beaten;
    return (s < STAGE_COUNT) ? s : (STAGE_COUNT - 1);
}

// Crawler (enemy) palette — blue, with one accent
static const u16 crawler_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555( 8, 12, 28),
    BGR555( 4,  6, 20),
    BGR555(20, 24, 31),
};

// Skeleton — bone white (OBJ palette 0)
static const u16 skeleton_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555(28, 28, 26),
    BGR555(13, 13, 15),
    BGR555(30, 20, 18),
};

// Orc — moss green (OBJ palette 7)
static const u16 orc_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555(12, 22,  8),
    BGR555( 5, 10,  4),
    BGR555(27, 13,  6),
};

// Stone Sentinel (boss) palette — granite grey with bright accent
static const u16 sentinel_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555(18, 18, 22),
    BGR555( 8,  8, 12),
    BGR555(28, 24, 14),
};

// Bullet palette — bright gold
static const u16 bullet_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555(31, 24,  0),
    BGR555(28, 16,  0),
    BGR555(31, 31,  4),
};

// Heart pickup palette (red)
static const u16 heart_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555(31, 12, 12),
    BGR555(16,  4,  4),
    BGR555( 0,  0,  0),
};

// Coin pickup palette (gold)
static const u16 coin_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555(31, 24,  4),
    BGR555(18, 12,  0),
    BGR555(31, 31, 14),
};

u8 room_tile_at_px(i16 px, i16 py) {
    if (px < 0 || py < 0) return BGT_WALL;
    {
        u8 tx = (u8)(px >> 3);
        u8 ty = (u8)(py >> 3);
        if (tx >= ROOM_W || ty >= ROOM_H) return BGT_WALL;
        return room_tilemap[ty][tx];
    }
}

u8 room_tile_walkable(u8 t) {
    return (t == BGT_FLOOR || t == BGT_FLOOR2 || t == BGT_FLOOR3
         || t == BGT_RUBBLE || t == BGT_DOOR);
}

static u8 is_walkable_at(i16 px, i16 py) {
    return room_tile_walkable(room_tile_at_px(px, py));
}

// Halve each 5-bit channel: pause-dim without storing dim palettes.
static void palette_bg_load_dimmed(u8 slot, const u16 *pal) {
    u16 tmp[4];
    u8 i;
    for (i = 0; i < 4; ++i) tmp[i] = (u16)((pal[i] >> 1) & 0x3DEF);
    palette_bg_load(slot, tmp);
}

static void room_apply_pause_palettes(u8 dim) {
    const u16 (*sp)[4] = stage_pal[room_stage()];
    if (dim) {
        palette_bg_load_dimmed(BGPAL_FLOOR,   sp[0]);
        palette_bg_load_dimmed(BGPAL_WALL,    sp[1]);
        palette_bg_load_dimmed(BGPAL_CRYSTAL, sp[2]);
        palette_bg_load_dimmed(BGPAL_DOOR,    sp[3]);
    } else {
        palette_bg_load(BGPAL_FLOOR,   sp[0]);
        palette_bg_load(BGPAL_WALL,    sp[1]);
        palette_bg_load(BGPAL_CRYSTAL, sp[2]);
        palette_bg_load(BGPAL_DOOR,    sp[3]);
    }
}

// Rewrite the 4 cardinal door tiles after a boss seal is lifted.
// Called at the top of vblank so the handful of VRAM writes land safely.
static void room_unseal_doors(void) {
    room_tilemap[0][ROOM_W / 2]          = BGT_DOOR;
    room_tilemap[ROOM_H - 1][ROOM_W / 2] = BGT_DOOR;
    room_tilemap[ROOM_H / 2][0]          = BGT_DOOR;
    room_tilemap[ROOM_H / 2][ROOM_W - 1] = BGT_DOOR;
    wait_vbl_done();
    {
        u8 door = BGT_DOOR, attr = BGPAL_DOOR;
        VBK_REG = 0;
        set_bkg_tiles(ROOM_W / 2, 0,          1, 1, &door);
        set_bkg_tiles(ROOM_W / 2, ROOM_H - 1, 1, 1, &door);
        set_bkg_tiles(0,          ROOM_H / 2, 1, 1, &door);
        set_bkg_tiles(ROOM_W - 1, ROOM_H / 2, 1, 1, &door);
        VBK_REG = 1;
        set_bkg_tiles(ROOM_W / 2, 0,          1, 1, &attr);
        set_bkg_tiles(ROOM_W / 2, ROOM_H - 1, 1, 1, &attr);
        set_bkg_tiles(0,          ROOM_H / 2, 1, 1, &attr);
        set_bkg_tiles(ROOM_W - 1, ROOM_H / 2, 1, 1, &attr);
        VBK_REG = 0;
    }
}

// Single-tile rewrite (tile + attr) at the top of vblank.
static void room_set_tile_vbl(u8 tx, u8 ty, u8 t, u8 attr) {
    room_tilemap[ty][tx] = t;
    wait_vbl_done();
    VBK_REG = 0;
    set_bkg_tiles(tx, ty, 1, 1, &t);
    VBK_REG = 1;
    set_bkg_tiles(tx, ty, 1, 1, &attr);
    VBK_REG = 0;
}

void room_open_secret(u8 tx, u8 ty) {
    if (tx >= ROOM_W || ty >= ROOM_H) return;
    room_set_tile_vbl(tx, ty, BGT_DOOR, BGPAL_DOOR);
    secret_door_x = tx;
    secret_door_y = ty;
    sfx_play(SFX_DOOR);
}

// CGB palette attribute per tile id
static u8 attr_for_tile(u8 t) {
    switch (t) {
        case BGT_WALL:
        case BGT_PILLAR:  return BGPAL_WALL;
        case BGT_WALL_CRACK: return BGPAL_CRACK;   // glowing — obviously special
        case BGT_CRYSTAL: return BGPAL_CRYSTAL;
        case BGT_DOOR:    return BGPAL_DOOR;
        default:          return BGPAL_FLOOR;
    }
}

static void draw_room_tilemap(void) {
    u8 x, y;
    u8 attr_row[ROOM_W];
    for (y = 0; y < ROOM_H; ++y) {
        // Tile indices (VRAM bank 0)
        VBK_REG = 0;
        set_bkg_tiles(0, y, ROOM_W, 1, room_tilemap[y]);
        // Palette attributes (VRAM bank 1)
        for (x = 0; x < ROOM_W; ++x) attr_row[x] = attr_for_tile(room_tilemap[y][x]);
        VBK_REG = 1;
        set_bkg_tiles(0, y, ROOM_W, 1, attr_row);
    }
    VBK_REG = 0;
}

static void place_player_sprite(void) {
    // 16x16 player metasprite — 4 OAM slots, anchored at (x+8, y+16) per GBDK
    if (player.iframes > 0 && (player.iframes & 0x04)) {
        move_sprite(0, 0, 0);
        move_sprite(1, 0, 0);
        move_sprite(2, 0, 0);
        move_sprite(3, 0, 0);
    } else {
        u8 sx = (u8)(player.x + 8);
        u8 sy = (u8)(player.y + 16);
        move_sprite(0, sx,         sy);
        move_sprite(1, (u8)(sx+8), sy);
        move_sprite(2, sx,         (u8)(sy+8));
        move_sprite(3, (u8)(sx+8), (u8)(sy+8));
    }
}

// Get the 8-dir index from current/pressed input. Returns 0..7 or 0xFF if none.
static u8 input_to_dir8(u8 keys) {
    u8 d = 0xFF;
    if (keys & J_UP) {
        if      (keys & J_RIGHT) d = 1;   // NE
        else if (keys & J_LEFT)  d = 7;   // NW
        else                     d = 0;   // N
    } else if (keys & J_DOWN) {
        if      (keys & J_RIGHT) d = 3;   // SE
        else if (keys & J_LEFT)  d = 5;   // SW
        else                     d = 4;   // S
    } else if (keys & J_RIGHT) {
        d = 2;
    } else if (keys & J_LEFT) {
        d = 6;
    }
    return d;
}

// Map 4-dir facing to 8-dir for fallback when no D-pad pressed at fire time
static u8 facing_to_dir8(u8 facing) {
    switch (facing) {
        case FACE_N: return 0;
        case FACE_E: return 2;
        case FACE_S: return 4;
        case FACE_W: return 6;
        default:     return 4;
    }
}

void room_enter(void) {
    DISPLAY_OFF;

    {
        const u16 (*sp)[4] = stage_pal[room_stage()];
        palette_bg_load(BGPAL_FLOOR,   sp[0]);
        palette_bg_load(BGPAL_WALL,    sp[1]);
        palette_bg_load(BGPAL_CRYSTAL, sp[2]);
        palette_bg_load(BGPAL_DOOR,    sp[3]);
    }
    palette_bg_load(BGPAL_CRACK,   pal_crack);
    palette_obj_load(0, skeleton_palette);
    palette_obj_load(1, class_obj_palettes[player.class_id < 5 ? player.class_id : 0]);
    palette_obj_load(2, bullet_palette);
    palette_obj_load(3, crawler_palette);
    palette_obj_load(4, heart_palette);
    palette_obj_load(5, coin_palette);
    palette_obj_load(6, sentinel_palette);
    palette_obj_load(7, orc_palette);

    tiles_load_room_bg();
    tiles_load_dungeon_bg();              // authored dungeon tileset (overrides placeholders)
    tiles_load_player_sprite();           // legacy single-tile fallback
    tiles_load_combat_sprites();
    tiles_load_pickup_sprites();
    tiles_load_boss_sprite();
    tiles_load_all_class_sprites();       // 5 × 16x16 player metasprites (slots 0..19)
    tiles_load_all_enemy_sprites();       // 4 enemy tiles (slots 20..23)
    tiles_load_boss_metasprite();         // 16x16 boss (slots 24..27)
    tiles_load_boss_big();                // 32x32 final boss (slots 40..55)
    tiles_load_fx_sprites();              // bullet A/B, muzzle, impact

    hud_init();
    hud_show();

    // Player metasprite — 4 tiles starting at class-specific base
    {
        u8 base = (u8)(SPR_CLASS_BASE + (u8)(player.class_id * SPR_CLASS_STRIDE));
        set_sprite_tile(0, (u8)(base + 0));    // TL
        set_sprite_tile(1, (u8)(base + 1));    // TR
        set_sprite_tile(2, (u8)(base + 2));    // BL
        set_sprite_tile(3, (u8)(base + 3));    // BR
        set_sprite_prop(0, 0x01);
        set_sprite_prop(1, 0x01);
        set_sprite_prop(2, 0x01);
        set_sprite_prop(3, 0x01);
    }
    player.facing        = FACE_S;
    player.fire_cooldown = 0;
    room_paused          = 0;

    if (room_resume_flag) {
        // Returning from the pack screen: keep the existing tilemap, entities
        // and player position — just redraw. Do NOT regenerate or restart music.
        room_resume_flag = 0;
        draw_room_tilemap();
        entity_draw_all();
        place_player_sprite();
        if (*(volatile u8*)0xFFFC == 0xBB) music_play_boss();
        else                              music_play_stage(room_stage());
        SHOW_SPRITES;
        SHOW_BKG;
        DISPLAY_ON;
        return;
    }

    player.iframes       = 0;

    // Procgen builds the tilemap + spawns enemies + positions player
    procgen_generate_current_room();
    draw_room_tilemap();
    place_player_sprite();

    secret_door_x = secret_door_y = 0xFF;
    player.active_charge = 0;
    if (*(volatile u8*)0xFFFC == 0xBB) {
        music_play_boss();
        sfx_play(SFX_ROAR);
    } else {
        music_play_stage(room_stage());
    }


    SHOW_SPRITES;
    SHOW_BKG;
    DISPLAY_ON;
}

void room_exit(void) {
    HIDE_SPRITES;
    hud_hide();
    music_stop();
    entity_init_all();
}

screen_id_t room_tick(u8 keys, u8 pressed) {
    // ---- START opens the PACK (stats + items); SELECT quick-pauses (dim).
    if (pressed & J_START) {
        return SCREEN_INVENTORY;
    }
    if (pressed & J_SELECT) {
        room_paused ^= 1;
        room_apply_pause_palettes(room_paused);
    }
    if (room_paused) return SCREEN_SELF;

    // ---- Hit-stop: freeze the world a few frames on impact for weight,
    // but keep drawing so the flash/knockback is visible.
    if (g_hitstop) {
        g_hitstop--;
        place_player_sprite();
        entity_draw_all();
        return SCREEN_SELF;
    }

    // ---- Movement: SPD-scaled sub-pixel accumulator.
    // acc += spd; each 5 accumulated = 1 px step. spd 5 = 1.0 px/f,
    // Sauran 4 = 0.8, Wolfkin 6 = 1.2, Vespine 7 = 1.4.
    {
        u8 moved = 0;
        i8 dx = 0, dy = 0;
        u8 steps;

        if (keys & J_LEFT)  { dx = -1; player.facing = FACE_W; moved = 1; }
        if (keys & J_RIGHT) { dx = +1; player.facing = FACE_E; moved = 1; }
        if (keys & J_UP)    { dy = -1; player.facing = FACE_N; moved = 1; }
        if (keys & J_DOWN)  { dy = +1; player.facing = FACE_S; moved = 1; }

        if (moved) {
            player.move_acc = (u8)(player.move_acc + player.spd);
        }
        steps = 0;
        while (player.move_acc >= 5) { player.move_acc -= 5; steps++; }

        while (steps--) {
            if (dx) {
                ppos_t nx = (ppos_t)(player.x + dx);
                if (is_walkable_at(nx + 1, player.y + 1)
                    && is_walkable_at(nx + 6, player.y + 1)
                    && is_walkable_at(nx + 1, player.y + 6)
                    && is_walkable_at(nx + 6, player.y + 6)) {
                    player.x = nx;
                }
            }
            if (dy) {
                ppos_t ny = (ppos_t)(player.y + dy);
                if (is_walkable_at(player.x + 1, ny + 1)
                    && is_walkable_at(player.x + 6, ny + 1)
                    && is_walkable_at(player.x + 1, ny + 6)
                    && is_walkable_at(player.x + 6, ny + 6)) {
                    player.y = ny;
                }
            }
        }

        if (moved) {
            player.anim_frame = (u8)((player.anim_frame + 1) & 0x07);
        }
    }

    // ---- Weapons. Starter comes from the generated items[] entry
    // (p0=fire_rate, p1=damage, p2=projectile kind). Starter ids 0-4 map
    // to array indices 0-4 by content authoring; guarded by N_ITEMS.
    // Per-class elemental identity: Wolfkin fire, Sauran lightning,
    // Corvin shadow, Picsean ice, Vespine poison (1/4/8/2/16).
    {
        static const u8 class_element[5] = { 1, 4, 8, 2, 16 };
        const item_def_t *w =
            &items[player.starter_weapon < N_ITEMS ? player.starter_weapon : 0];
        g_shot_element = class_element[player.class_id < 5 ? player.class_id : 0];

        if ((keys & J_A) && player.fire_cooldown == 0) {
            u8 dir = input_to_dir8(keys);
            u8 dmg = (u8)(w->p1 + player.atk);   // ATK adds linearly
            if (dir == 0xFF) dir = facing_to_dir8(player.facing);
            projectile_spawn_player(dir8_dx[dir], dir8_dy[dir], dmg, w->p2);
            player.fire_cooldown = (u8)(w->p0 >> 1);
        }
        if (player.fire_cooldown > 0) player.fire_cooldown--;

        // ---- Weapon 2 (B, edge): class signature move, ~2.3s cooldown
        if ((pressed & J_B) && player.active_charge == 0) {
            u8 dir = input_to_dir8(keys);
            u8 dmg = (u8)(w->p1 + 1 + player.atk);
            u8 d;
            if (dir == 0xFF) dir = facing_to_dir8(player.facing);
            switch (player.class_id) {
                case 0:   // Wolfkin HOWL: 8-way spike ring
                    for (d = 0; d < 8; ++d) {
                        projectile_spawn_player(dir8_dx[d], dir8_dy[d], dmg, PROJ_SPIKE);
                    }
                    break;
                case 1:   // Sauran STONESKIN: 1.5s of iframes
                    player.iframes = 90;
                    break;
                case 2:   // Corvin MURDER: 3-way shuriken spread
                    projectile_spawn_player(dir8_dx[dir], dir8_dy[dir], dmg, PROJ_SHURIKEN);
                    projectile_spawn_player(dir8_dx[(u8)((dir + 1) & 7)],
                        dir8_dy[(u8)((dir + 1) & 7)], dmg, PROJ_SHURIKEN);
                    projectile_spawn_player(dir8_dx[(u8)((dir + 7) & 7)],
                        dir8_dy[(u8)((dir + 7) & 7)], dmg, PROJ_SHURIKEN);
                    break;
                case 3:   // Picsean TIDAL WAVE: 3-lane bubble wall
                    projectile_spawn_player(dir8_dx[dir], dir8_dy[dir], dmg, PROJ_BUBBLE);
                    projectile_spawn_player(dir8_dx[(u8)((dir + 2) & 7)],
                        dir8_dy[(u8)((dir + 2) & 7)], dmg, PROJ_BUBBLE);
                    projectile_spawn_player(dir8_dx[(u8)((dir + 6) & 7)],
                        dir8_dy[(u8)((dir + 6) & 7)], dmg, PROJ_BUBBLE);
                    break;
                default:  // Vespine SWARM: 4-stinger fan burst
                    projectile_spawn_player(dir8_dx[dir], dir8_dy[dir], dmg, PROJ_SPIKE);
                    projectile_spawn_player(dir8_dx[dir], dir8_dy[dir], dmg, PROJ_BULLET);
                    projectile_spawn_player(dir8_dx[(u8)((dir + 1) & 7)],
                        dir8_dy[(u8)((dir + 1) & 7)], dmg, PROJ_BULLET);
                    projectile_spawn_player(dir8_dx[(u8)((dir + 7) & 7)],
                        dir8_dy[(u8)((dir + 7) & 7)], dmg, PROJ_BULLET);
                    break;
            }
            sfx_play(SFX_ROAR);
            player.active_charge = 140;
        }
        if (player.active_charge > 0) player.active_charge--;
    }

    // ---- Entity updates
    entity_update_all(keys, pressed);

    // ---- Combat
    if (combat_resolve()) {
        // Player died → GAMEOVER
        return SCREEN_GAMEOVER;
    }

    // ---- Boss beaten (non-final): lift the door seal, run continues,
    // and the fight music yields back to the exploration theme.
    if (run_state.pending_unseal) {
        run_state.pending_unseal = 0;
        room_unseal_doors();
        music_play_stage(room_stage());
    }

    // ---- Final victory: all bosses down
    if (run_state.victory) {
        return SCREEN_VICTORY;
    }

    // ---- Rubble poking: walking over rubble kicks it apart (Zelda bush-cut)
    {
        u8 rtx = (u8)((player.x + 4) >> 3);
        u8 rty = (u8)((player.y + 4) >> 3);
        if (rtx < ROOM_W && rty < ROOM_H
            && room_tilemap[rty][rtx] == BGT_RUBBLE) {
            room_set_tile_vbl(rtx, rty, BGT_FLOOR, BGPAL_FLOOR);
            sfx_play(SFX_HIT);
            if (rng_next_u8() < 100) {   // ~40%: hidden coin
                pickup_spawn(PICKUP_COIN_1,
                    FIX8((i16)rtx * 8), FIX8((i16)rty * 8));
            }
        }
    }

    // ---- Door detection: if player stands on a door, advance to next room
    {
        i16 px = player.x + 4;
        i16 py = player.y + 4;
        u8 tx = (u8)(px >> 3);
        u8 ty = (u8)(py >> 3);

        if (tx < ROOM_W && ty < ROOM_H && room_tilemap[ty][tx] == BGT_DOOR) {
            // Determine which door
            u8 dir = DIR_NONE;
            if      (ty == 0)              dir = DIR_N;
            else if (ty == ROOM_H - 1)     dir = DIR_S;
            else if (tx == 0)              dir = DIR_W;
            else if (tx == ROOM_W - 1)     dir = DIR_E;

            if (dir != DIR_NONE) {
                // Leaving through a shot-open secret door → treasure room
                if (tx == secret_door_x && ty == secret_door_y) {
                    run_state.secret_pending = 1;
                }
                secret_door_x = secret_door_y = 0xFF;
                run_state.room_counter++;
                run_state.entered_from = dir;
                sfx_play(SFX_DOOR);
                // Regenerate room in-place (skip full screen exit/enter)
                DISPLAY_OFF;
                procgen_generate_current_room();
                draw_room_tilemap();
                place_player_sprite();
                hud_redraw_all();
                DISPLAY_ON;
                if (*(volatile u8*)0xFFFC == 0xBB) {
                    music_play_boss();
                    sfx_play(SFX_ROAR);
                } else {
                    music_play_stage(room_stage());
                }
                return SCREEN_SELF;
            }
        }
    }

    return SCREEN_SELF;
}

void room_draw(void) {
    place_player_sprite();
    entity_draw_all();
}
