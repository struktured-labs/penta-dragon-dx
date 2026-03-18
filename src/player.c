#include "player.h"
#include "level.h"

#include "../assets/extracted/sprites/include/sprites_sara_witch_16.h"
#include "../assets/extracted/sprites/include/sprites_sara_dragon_real.h"

Player player;

// Original game: Sara moves freely within screen bounds
// BG auto-scrolls right, Sara walks with D-pad
// Starting position: center-ish (72, 64)
#define SARA_START_X     72
#define SARA_START_Y     64
#define SARA_SPEED       2    // Pixels per frame (matches original)
#define SARA_X_MIN       8    // Left screen bound
#define SARA_X_MAX       144  // Right screen bound (160 - 16)
#define SARA_Y_MIN       8    // Top screen bound
#define SARA_Y_MAX       112  // Bottom bound (above HUD at 120 - 8)
#define ANIM_SPEED       12

void player_init(void) {
    player.x = SARA_START_X;
    player.y = SARA_START_Y;
    player.form = 0;
    player.dir = DIR_RIGHT;
    player.frame = 1;  // Idle = frame 1 (original uses tiles 0x24-0x27)
    player.anim_tick = 0;
    player.shoot_cd = 0;
    player.powerup = 0;
    player.hp = 255;
    player.invuln = 0;
}

void player_load_tiles(void) {
    set_sprite_data(TILE_SARA_W, SPRITE_SARA_WITCH_16_COUNT,
                    SPRITE_SARA_WITCH_16);
    set_sprite_data(TILE_SARA_D, SPRITE_SARA_DRAGON_REAL_NUM_TILES,
                    SPRITE_SARA_DRAGON_REAL);
}

void player_update(uint8_t keys, uint8_t prev_keys) {
    // Sara moves freely within screen bounds with terrain collision
    uint16_t wx;
    uint8_t wy;
    uint8_t old_x = player.x;
    uint8_t old_y = player.y;

    if (keys & J_LEFT) {
        player.dir = DIR_LEFT;
        if (player.x > SARA_X_MIN) {
            wx = scroll_x + player.x - SARA_SPEED;
            wy = player.y + 8;
            if (!level_is_solid(wx, wy)) player.x -= SARA_SPEED;
        }
    }
    if (keys & J_RIGHT) {
        player.dir = DIR_RIGHT;
        if (player.x < SARA_X_MAX) {
            wx = scroll_x + player.x + 16 + SARA_SPEED;
            wy = player.y + 8;
            if (!level_is_solid(wx, wy)) player.x += SARA_SPEED;
        }
    }
    if (keys & J_UP) {
        if (player.y > SARA_Y_MIN) {
            wx = scroll_x + player.x + 8;
            wy = player.y - SARA_SPEED;
            if (!level_is_solid(wx, wy)) player.y -= SARA_SPEED;
        }
    }
    if (keys & J_DOWN) {
        if (player.y < SARA_Y_MAX) {
            wx = scroll_x + player.x + 8;
            wy = player.y + 16 + SARA_SPEED;
            if (!level_is_solid(wx, wy)) player.y += SARA_SPEED;
        }
    }

    // Clamp Sara to screen bounds (safety against auto-scroll push)
    if (player.x < SARA_X_MIN) player.x = SARA_X_MIN;
    if (player.x > SARA_X_MAX) player.x = SARA_X_MAX;
    if (player.y < SARA_Y_MIN) player.y = SARA_Y_MIN;
    if (player.y > SARA_Y_MAX) player.y = SARA_Y_MAX;

    // Form toggle on SELECT (edge-triggered)
    if ((keys & J_SELECT) && !(prev_keys & J_SELECT)) {
        player.form ^= 1;
    }

    // Shoot cooldown
    if (player.shoot_cd > 0) {
        player.shoot_cd--;
    }

    // Animation — only animate if Sara actually moved
    if (player.x != old_x || player.y != old_y) {
        player.anim_tick++;
        if (player.anim_tick >= ANIM_SPEED) {
            player.anim_tick = 0;
            // Cycle through walking frames: 0 → 2 → 3 → 0
            if (player.frame == 0) player.frame = 2;
            else if (player.frame == 2) player.frame = 3;
            else player.frame = 0;
        }
    } else {
        player.anim_tick = 0;
        player.frame = 1;  // Idle = frame 1
    }

    // Invulnerability countdown
    if (player.invuln > 0) {
        player.invuln--;
        // Shield powerup expires with invulnerability
        if (player.invuln == 0 && player.powerup == 2) {
            player.powerup = 0;
        }
    }
}

void player_draw(void) {
    uint8_t tile_base;
    uint8_t palette;
    uint8_t flags_all;
    uint8_t flags_bot;
    uint8_t sx, sy;
    uint8_t is_idle;

    if (player.form == 0) {
        tile_base = TILE_SARA_W + (player.frame & 0x03) * 4; // 4 frames
        palette = 2;
    } else {
        tile_base = TILE_SARA_D + (player.frame & 0x03) * 4; // 4 frames
        palette = 1;
    }

    // Idle = frame 1 (tiles 4-7, originally 0x24-0x27)
    is_idle = (player.frame == 1);

    // Original sprite flag analysis (verified frame-by-frame on original ROM):
    //
    // FACING RIGHT:
    //   Walking frames (0x20-0x23, 0x28-0x2B, 0x2C-0x2F):
    //     ALL 4 sprites: flags=0x00 (no S_FLIPX anywhere)
    //     Layout: TL=tile+0, TR=tile+1, BL=tile+2, BR=tile+3
    //   Idle frame (0x24-0x27) only:
    //     Top: flags=0x00, Bottom: flags=0x20 (S_FLIPX)
    //     Layout: TL=tile+0, TR=tile+1, BL=tile+3(FLIPX), BR=tile+2(FLIPX)
    //
    // FACING LEFT (all frames):
    //   ALL 4 sprites: flags=0x20 (S_FLIPX)
    //   Columns swap: slot0=tile+1, slot1=tile+0, slot2=tile+3, slot3=tile+2

    flags_all = palette & 0x07;

    // Sara's screen position
    sx = player.x + OAM_X_OFS;
    sy = player.y + OAM_Y_OFS;

    // Invulnerability blink
    if (player.invuln > 0 && (player.invuln & 0x02)) {
        move_sprite(OAM_PLAYER,     0, 0);
        move_sprite(OAM_PLAYER + 1, 0, 0);
        move_sprite(OAM_PLAYER + 2, 0, 0);
        move_sprite(OAM_PLAYER + 3, 0, 0);
        return;
    }

    if (player.dir == DIR_LEFT) {
        // LEFT facing: all 4 sprites get S_FLIPX, columns swap
        // Same layout for both idle and walking frames
        flags_all |= S_FLIPX;

        set_sprite_tile(OAM_PLAYER,     tile_base + 1); // TR→left column
        set_sprite_prop(OAM_PLAYER,     flags_all);
        move_sprite(OAM_PLAYER,         sx, sy);

        set_sprite_tile(OAM_PLAYER + 1, tile_base);     // TL→right column
        set_sprite_prop(OAM_PLAYER + 1, flags_all);
        move_sprite(OAM_PLAYER + 1,     sx + 8, sy);

        set_sprite_tile(OAM_PLAYER + 2, tile_base + 3); // BR→left column
        set_sprite_prop(OAM_PLAYER + 2, flags_all);
        move_sprite(OAM_PLAYER + 2,     sx, sy + 8);

        set_sprite_tile(OAM_PLAYER + 3, tile_base + 2); // BL→right column
        set_sprite_prop(OAM_PLAYER + 3, flags_all);
        move_sprite(OAM_PLAYER + 3,     sx + 8, sy + 8);
    } else {
        // RIGHT facing
        set_sprite_tile(OAM_PLAYER,     tile_base);     // TL
        set_sprite_prop(OAM_PLAYER,     flags_all);
        move_sprite(OAM_PLAYER,         sx, sy);

        set_sprite_tile(OAM_PLAYER + 1, tile_base + 1); // TR
        set_sprite_prop(OAM_PLAYER + 1, flags_all);
        move_sprite(OAM_PLAYER + 1,     sx + 8, sy);

        if (is_idle) {
            // Idle frame (0x24-0x27): bottom tiles are swapped + S_FLIPX
            // The idle pose's lower body tile art is drawn mirrored
            flags_bot = (palette & 0x07) | S_FLIPX;
            set_sprite_tile(OAM_PLAYER + 2, tile_base + 3); // BL = tile+3 (FLIPX)
            set_sprite_prop(OAM_PLAYER + 2, flags_bot);
            move_sprite(OAM_PLAYER + 2,     sx, sy + 8);

            set_sprite_tile(OAM_PLAYER + 3, tile_base + 2); // BR = tile+2 (FLIPX)
            set_sprite_prop(OAM_PLAYER + 3, flags_bot);
            move_sprite(OAM_PLAYER + 3,     sx + 8, sy + 8);
        } else {
            // Walking frames: straight grid layout, NO S_FLIPX
            set_sprite_tile(OAM_PLAYER + 2, tile_base + 2); // BL = tile+2
            set_sprite_prop(OAM_PLAYER + 2, flags_all);
            move_sprite(OAM_PLAYER + 2,     sx, sy + 8);

            set_sprite_tile(OAM_PLAYER + 3, tile_base + 3); // BR = tile+3
            set_sprite_prop(OAM_PLAYER + 3, flags_all);
            move_sprite(OAM_PLAYER + 3,     sx + 8, sy + 8);
        }
    }
}
