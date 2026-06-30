// ROOM — top-down gameplay scene. Phase 4: single hand-drawn empty room
// with walls, 4-direction player movement, wall collision. Phase 5 adds
// projectiles / enemies / combat; Phase 7 wires procgen to fill this
// from biome.room_template_pool.

#include <gb/gb.h>
#include <gb/cgb.h>

#include "core/types.h"
#include "game/player.h"
#include "game/room.h"
#include "render/palette.h"
#include "render/tiles.h"

u8 room_tilemap[ROOM_H][ROOM_W];

// Biome palette for room — cave-y blue-grey
static const u16 room_bg_palette[4] = {
    BGR555( 0,  0,  4),    // 0: void / black-blue
    BGR555( 5,  6, 12),    // 1: floor (mid blue-grey)
    BGR555(12, 14, 22),    // 2: door / accent
    BGR555(22, 24, 28),    // 3: wall (light cyan-grey)
};

// Player palette — wolfkin theme (warm brown / cream)
static const u16 player_palette[4] = {
    BGR555( 0,  0,  0),    // 0: transparent
    BGR555(28, 22, 14),    // 1: cream body
    BGR555(16,  8,  4),    // 2: brown outline
    BGR555( 0,  0,  0),    // 3: unused
};

static void build_default_room(void) {
    u8 x, y;
    for (y = 0; y < ROOM_H; ++y) {
        for (x = 0; x < ROOM_W; ++x) {
            if (y == 0 || y == ROOM_H - 1 || x == 0 || x == ROOM_W - 1) {
                room_tilemap[y][x] = BGT_WALL;
            } else {
                room_tilemap[y][x] = BGT_FLOOR;
            }
        }
    }
    // Place doors at midpoints (cosmetic in Phase 4; functional in Phase 7)
    room_tilemap[0][ROOM_W / 2]            = BGT_DOOR;
    room_tilemap[ROOM_H - 1][ROOM_W / 2]   = BGT_DOOR;
    room_tilemap[ROOM_H / 2][0]            = BGT_DOOR;
    room_tilemap[ROOM_H / 2][ROOM_W - 1]   = BGT_DOOR;
}

// Tile coord at world position. fix8 -> int -> >>3 (pixels per tile).
// Player draw offset accounts for GBDK sprite anchor (top-left of 8x8).
static u8 tile_at(i16 px, i16 py) {
    if (px < 0 || py < 0) return BGT_WALL;
    {
        u8 tx = (u8)(px >> 3);
        u8 ty = (u8)(py >> 3);
        if (tx >= ROOM_W || ty >= ROOM_H) return BGT_WALL;
        return room_tilemap[ty][tx];
    }
}

static u8 is_walkable_at(i16 px, i16 py) {
    u8 t = tile_at(px, py);
    return (t == BGT_FLOOR || t == BGT_DOOR);
}

static void draw_room_tilemap(void) {
    u8 y;
    for (y = 0; y < ROOM_H; ++y) {
        set_bkg_tiles(0, y, ROOM_W, 1, room_tilemap[y]);
    }
}

static void place_player_sprite(void) {
    // Sprite origin: GBDK move_sprite uses (x+8, y+16) for top-left of 8x8.
    move_sprite(0,
        (u8)(FIX8_TO_INT(player.x) + 8),
        (u8)(FIX8_TO_INT(player.y) + 16));
}

void room_enter(void) {
    DISPLAY_OFF;

    palette_bg_load(0, room_bg_palette);
    palette_obj_load(1, player_palette);

    tiles_load_room_bg();
    tiles_load_player_sprite();

    build_default_room();
    draw_room_tilemap();

    // Player starts at center of room
    player.x = FIX8(((ROOM_W / 2) * 8));
    player.y = FIX8(((ROOM_H / 2) * 8));
    player.facing = FACE_S;

    // Assign sprite 0 to player tile, palette 1 (CGB OBJ palette bit field)
    set_sprite_tile(0, SPR_PLAYER);
    set_sprite_prop(0, 0x01);     // CGB OBJ palette index 1
    place_player_sprite();

    SHOW_SPRITES;
    SHOW_BKG;
    DISPLAY_ON;
}

void room_exit(void) {
    HIDE_SPRITES;
}

// Compute next position from input + speed. Sub-tile movement via fix8.
// Speed is in fixed-point px/tick (e.g. spd=6 means 6/256 px/tick → too slow;
// scale up by a constant so spd=6 → 1.5 px/tick).
#define SPEED_SCALE 32   // each spd unit = 32/256 px = 0.125 px/tick

screen_id_t room_tick(u8 keys, u8 pressed) {
    pressed;
    fix8_t nx = player.x;
    fix8_t ny = player.y;
    fix8_t step = (fix8_t)((i16)player.spd * SPEED_SCALE);
    u8 moved = 0;

    if (keys & J_LEFT)  { nx -= step; player.facing = FACE_W; moved = 1; }
    if (keys & J_RIGHT) { nx += step; player.facing = FACE_E; moved = 1; }
    if (keys & J_UP)    { ny -= step; player.facing = FACE_N; moved = 1; }
    if (keys & J_DOWN)  { ny += step; player.facing = FACE_S; moved = 1; }

    // Wall collision: only commit each axis if the new position's 4 corners
    // of the player's hitbox (5×5 inset of 8×8 sprite) are all walkable.
    {
        i16 px = FIX8_TO_INT(nx);
        i16 py = FIX8_TO_INT(player.y);
        if (is_walkable_at(px + 1, py + 1)
            && is_walkable_at(px + 6, py + 1)
            && is_walkable_at(px + 1, py + 6)
            && is_walkable_at(px + 6, py + 6)) {
            player.x = nx;
        }
    }
    {
        i16 px = FIX8_TO_INT(player.x);
        i16 py = FIX8_TO_INT(ny);
        if (is_walkable_at(px + 1, py + 1)
            && is_walkable_at(px + 6, py + 1)
            && is_walkable_at(px + 1, py + 6)
            && is_walkable_at(px + 6, py + 6)) {
            player.y = ny;
        }
    }

    if (moved) {
        // Tick anim frame at 1/8 frequency (placeholder)
        player.anim_frame = (u8)((player.anim_frame + 1) & 0x07);
    }

    // For Phase 4: any button on START returns to TITLE
    if (pressed & J_START) {
        return SCREEN_TITLE;
    }
    return SCREEN_SELF;
}

void room_draw(void) {
    place_player_sprite();
}
