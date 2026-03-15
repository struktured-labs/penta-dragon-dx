#include "player.h"

#include "../assets/extracted/sprites/include/sprites_sara_witch.h"
#include "../assets/extracted/sprites/include/sprites_sara_dragon.h"

Player player;

#define PLAYER_SPEED     FIX_FRAC(1, 0x80) // 1.5 px/frame
#define PLAYER_MIN_X     FIX(12)
#define PLAYER_MAX_X     FIX(148)
#define PLAYER_MIN_Y     FIX(24)
#define PLAYER_MAX_Y     FIX(136)
#define SHOOT_COOLDOWN   10
#define ANIM_SPEED       12

void player_init(void) {
    player.x = FIX(40);
    player.y = FIX(80);
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

uint8_t player_get_palette(void) {
    return (player.form == 0) ? 2 : 1;
}

void player_update(uint8_t keys, uint8_t prev_keys) {
    // Movement (4-directional, free movement like original)
    if (keys & J_LEFT) {
        player.x -= PLAYER_SPEED;
        player.dir = DIR_LEFT;
    }
    if (keys & J_RIGHT) {
        player.x += PLAYER_SPEED;
        player.dir = DIR_RIGHT;
    }
    if (keys & J_UP) {
        player.y -= PLAYER_SPEED;
    }
    if (keys & J_DOWN) {
        player.y += PLAYER_SPEED;
    }

    // Clamp to screen bounds
    if (player.x < PLAYER_MIN_X) player.x = PLAYER_MIN_X;
    if (player.x > PLAYER_MAX_X) player.x = PLAYER_MAX_X;
    if (player.y < PLAYER_MIN_Y) player.y = PLAYER_MIN_Y;
    if (player.y > PLAYER_MAX_Y) player.y = PLAYER_MAX_Y;

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

    // Pick tile set based on form
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

    sx = UNFIX(player.x) + OAM_X_OFS;
    sy = UNFIX(player.y) + OAM_Y_OFS;

    // When facing left, swap left/right tile columns
    if (player.dir == DIR_LEFT) {
        left_x = sx + 8;
        right_x = sx;
    } else {
        left_x = sx;
        right_x = sx + 8;
    }

    // Invulnerability blink (hide every other frame)
    if (player.invuln > 0 && (player.invuln & 0x02)) {
        // Hide sprites during blink
        move_sprite(OAM_PLAYER,     0, 0);
        move_sprite(OAM_PLAYER + 1, 0, 0);
        move_sprite(OAM_PLAYER + 2, 0, 0);
        move_sprite(OAM_PLAYER + 3, 0, 0);
        return;
    }

    // Top-left
    set_sprite_tile(OAM_PLAYER, tile_base);
    set_sprite_prop(OAM_PLAYER, flags);
    move_sprite(OAM_PLAYER, left_x, sy);

    // Top-right
    set_sprite_tile(OAM_PLAYER + 1, tile_base + 1);
    set_sprite_prop(OAM_PLAYER + 1, flags);
    move_sprite(OAM_PLAYER + 1, right_x, sy);

    // Bottom-left
    set_sprite_tile(OAM_PLAYER + 2, tile_base + 2);
    set_sprite_prop(OAM_PLAYER + 2, flags);
    move_sprite(OAM_PLAYER + 2, left_x, sy + 8);

    // Bottom-right
    set_sprite_tile(OAM_PLAYER + 3, tile_base + 3);
    set_sprite_prop(OAM_PLAYER + 3, flags);
    move_sprite(OAM_PLAYER + 3, right_x, sy + 8);
}
