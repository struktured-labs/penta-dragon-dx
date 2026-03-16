#include "player.h"

#include "../assets/extracted/sprites/include/sprites_sara_witch.h"
#include "../assets/extracted/sprites/include/sprites_sara_dragon.h"

Player player;

// Original game: Sara is fixed at screen position (76, 68)
// D-pad scrolls the world, Sara stays put
// UP/DOWN moves Sara vertically to dodge enemies
#define SARA_SCREEN_X    76   // Fixed horizontal screen position
#define SARA_MIN_Y       24   // Top movement limit
#define SARA_MAX_Y       120  // Bottom movement limit
#define PLAYER_SPEED_Y   2    // Vertical movement speed
#define ANIM_SPEED       12

void player_init(void) {
    player.x = SARA_SCREEN_X;  // Fixed — never changes
    player.y = 68;              // Starting vertical position
    player.form = 0;
    player.dir = DIR_RIGHT;
    player.frame = 0;
    player.anim_tick = 0;
    player.shoot_cd = 0;
    player.powerup = 0;
    player.hp = 10;
    player.invuln = 0;
}

void player_load_tiles(void) {
    set_sprite_data(TILE_SARA_W, SPRITE_SARA_WITCH_TILE_COUNT,
                    SPRITE_SARA_WITCH);
    set_sprite_data(TILE_SARA_D, SPRITE_SARA_DRAGON_TILE_COUNT,
                    SPRITE_SARA_DRAGON);
}

void player_update(uint8_t keys, uint8_t prev_keys) {
    // Horizontal: Sara doesn't move — BG scrolls (handled by level.c)
    // Only set facing direction
    if (keys & J_LEFT) {
        player.dir = DIR_LEFT;
    }
    if (keys & J_RIGHT) {
        player.dir = DIR_RIGHT;
    }

    // Vertical: Sara actually moves on screen to dodge enemies
    if (keys & J_UP) {
        if (player.y > SARA_MIN_Y + PLAYER_SPEED_Y)
            player.y -= PLAYER_SPEED_Y;
        else
            player.y = SARA_MIN_Y;
    }
    if (keys & J_DOWN) {
        if (player.y < SARA_MAX_Y - PLAYER_SPEED_Y)
            player.y += PLAYER_SPEED_Y;
        else
            player.y = SARA_MAX_Y;
    }

    // Form toggle on SELECT (edge-triggered)
    if ((keys & J_SELECT) && !(prev_keys & J_SELECT)) {
        player.form ^= 1;
    }

    // Shoot cooldown
    if (player.shoot_cd > 0) {
        player.shoot_cd--;
    }

    // Animation — only cycle when moving
    if (keys & (J_LEFT | J_RIGHT | J_UP | J_DOWN)) {
        player.anim_tick++;
        if (player.anim_tick >= ANIM_SPEED) {
            player.anim_tick = 0;
            player.frame = (player.frame + 1) & 0x01;
        }
    } else {
        player.anim_tick = 0;
        player.frame = 0;
    }

    // Invulnerability countdown
    if (player.invuln > 0) {
        player.invuln--;
    }
}

void player_draw(void) {
    uint8_t tile_base;
    uint8_t palette;
    uint8_t flags;
    uint8_t sx, sy;

    if (player.form == 0) {
        // Original uses tiles 0x24-0x27 for default pose
        // Our VRAM: frame 0 = tiles 0-3, frame 1 = tiles 4-7
        tile_base = TILE_SARA_W + (player.frame & 0x01) * 4;
        palette = 2;
    } else {
        tile_base = TILE_SARA_D + (player.frame & 0x01) * 4;
        palette = 1;
    }

    flags = palette & 0x07;
    if (player.dir == DIR_LEFT) {
        flags |= S_FLIPX;
    }

    // Sara's screen position — X is always fixed at SARA_SCREEN_X
    sx = SARA_SCREEN_X + OAM_X_OFS;
    sy = player.y + OAM_Y_OFS;

    // Invulnerability blink
    if (player.invuln > 0 && (player.invuln & 0x02)) {
        move_sprite(OAM_PLAYER,     0, 0);
        move_sprite(OAM_PLAYER + 1, 0, 0);
        move_sprite(OAM_PLAYER + 2, 0, 0);
        move_sprite(OAM_PLAYER + 3, 0, 0);
        return;
    }

    // 2x2 sprite arrangement matching original:
    // Original OAM: TL=0x24, TR=0x25, BL=0x27, BR=0x26
    // The bottom tiles are swapped from naive order
    if (player.dir == DIR_LEFT) {
        // Flip: swap left/right columns
        set_sprite_tile(OAM_PLAYER,     tile_base + 1); // TR→left
        set_sprite_prop(OAM_PLAYER,     flags);
        move_sprite(OAM_PLAYER,         sx, sy);

        set_sprite_tile(OAM_PLAYER + 1, tile_base);     // TL→right
        set_sprite_prop(OAM_PLAYER + 1, flags);
        move_sprite(OAM_PLAYER + 1,     sx + 8, sy);

        set_sprite_tile(OAM_PLAYER + 2, tile_base + 2); // BR→left (swapped)
        set_sprite_prop(OAM_PLAYER + 2, flags);
        move_sprite(OAM_PLAYER + 2,     sx, sy + 8);

        set_sprite_tile(OAM_PLAYER + 3, tile_base + 3); // BL→right (swapped)
        set_sprite_prop(OAM_PLAYER + 3, flags);
        move_sprite(OAM_PLAYER + 3,     sx + 8, sy + 8);
    } else {
        // Facing right: original layout
        set_sprite_tile(OAM_PLAYER,     tile_base);     // TL
        set_sprite_prop(OAM_PLAYER,     flags);
        move_sprite(OAM_PLAYER,         sx, sy);

        set_sprite_tile(OAM_PLAYER + 1, tile_base + 1); // TR
        set_sprite_prop(OAM_PLAYER + 1, flags);
        move_sprite(OAM_PLAYER + 1,     sx + 8, sy);

        set_sprite_tile(OAM_PLAYER + 2, tile_base + 3); // BL (tile+3, not +2)
        set_sprite_prop(OAM_PLAYER + 2, flags);
        move_sprite(OAM_PLAYER + 2,     sx, sy + 8);

        set_sprite_tile(OAM_PLAYER + 3, tile_base + 2); // BR (tile+2, not +3)
        set_sprite_prop(OAM_PLAYER + 3, flags);
        move_sprite(OAM_PLAYER + 3,     sx + 8, sy + 8);
    }
}
