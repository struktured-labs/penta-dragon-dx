#include "player.h"

#include "../assets/extracted/sprites/include/sprites_sara_witch.h"
#include "../assets/extracted/sprites/include/sprites_sara_dragon.h"

Player player;

#define PLAYER_SPEED     2
#define PLAYER_MIN_X     12
#define PLAYER_MAX_X     148
#define PLAYER_MIN_Y     24
#define PLAYER_MAX_Y     128
#define ANIM_SPEED       12

void player_init(void) {
    player.x = 40;
    player.y = 72;
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
    if (keys & J_LEFT) {
        if (player.x > PLAYER_MIN_X + PLAYER_SPEED)
            player.x -= PLAYER_SPEED;
        else
            player.x = PLAYER_MIN_X;
        player.dir = DIR_LEFT;
    }
    if (keys & J_RIGHT) {
        if (player.x < PLAYER_MAX_X - PLAYER_SPEED)
            player.x += PLAYER_SPEED;
        else
            player.x = PLAYER_MAX_X;
        player.dir = DIR_RIGHT;
    }
    if (keys & J_UP) {
        if (player.y > PLAYER_MIN_Y + PLAYER_SPEED)
            player.y -= PLAYER_SPEED;
        else
            player.y = PLAYER_MIN_Y;
    }
    if (keys & J_DOWN) {
        if (player.y < PLAYER_MAX_Y - PLAYER_SPEED)
            player.y += PLAYER_SPEED;
        else
            player.y = PLAYER_MAX_Y;
    }

    // Form toggle on SELECT (edge-triggered)
    if ((keys & J_SELECT) && !(prev_keys & J_SELECT)) {
        player.form ^= 1;
    }

    // Shoot cooldown
    if (player.shoot_cd > 0) {
        player.shoot_cd--;
    }

    // Animation
    player.anim_tick++;
    if (player.anim_tick >= ANIM_SPEED) {
        player.anim_tick = 0;
        player.frame = (player.frame + 1) & 0x03;
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
    uint8_t left_x, right_x;

    if (player.form == 0) {
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

    sx = player.x + OAM_X_OFS;
    sy = player.y + OAM_Y_OFS;

    if (player.dir == DIR_LEFT) {
        left_x = sx + 8;
        right_x = sx;
    } else {
        left_x = sx;
        right_x = sx + 8;
    }

    // Invulnerability blink
    if (player.invuln > 0 && (player.invuln & 0x02)) {
        move_sprite(OAM_PLAYER,     0, 0);
        move_sprite(OAM_PLAYER + 1, 0, 0);
        move_sprite(OAM_PLAYER + 2, 0, 0);
        move_sprite(OAM_PLAYER + 3, 0, 0);
        return;
    }

    set_sprite_tile(OAM_PLAYER, tile_base);
    set_sprite_prop(OAM_PLAYER, flags);
    move_sprite(OAM_PLAYER, left_x, sy);

    set_sprite_tile(OAM_PLAYER + 1, tile_base + 1);
    set_sprite_prop(OAM_PLAYER + 1, flags);
    move_sprite(OAM_PLAYER + 1, right_x, sy);

    set_sprite_tile(OAM_PLAYER + 2, tile_base + 2);
    set_sprite_prop(OAM_PLAYER + 2, flags);
    move_sprite(OAM_PLAYER + 2, left_x, sy + 8);

    set_sprite_tile(OAM_PLAYER + 3, tile_base + 3);
    set_sprite_prop(OAM_PLAYER + 3, flags);
    move_sprite(OAM_PLAYER + 3, right_x, sy + 8);
}
