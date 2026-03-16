// Penta Dragon DX Remake - GBC Native
// Full color from the ground up

#include <gb/gb.h>
#include <gb/cgb.h>

#include "types.h"
#include "palettes.h"
#include "player.h"
#include "projectile.h"
#include "enemy.h"
#include "level.h"
#include "sound.h"

static uint8_t prev_keys;
static uint8_t game_state;

static void game_init(void) {
    DISPLAY_OFF;

    // Sound
    sound_init();

    // Palettes
    init_palettes();

    // Tiles
    level_load_tiles();
    player_load_tiles();
    projectile_load_tiles();
    enemy_load_tiles();

    // Systems
    player_init();
    projectile_init();
    enemy_init();
    level_init();

    prev_keys = 0;
    game_state = STATE_PLAYING;

    // Draw initial frame
    player_draw();
    projectile_draw();
    enemy_draw();

    SHOW_BKG;
    SHOW_SPRITES;
    DISPLAY_ON;
}

static void game_update(void) {
    uint8_t keys = joypad();

    // Player
    player_update(keys, prev_keys);

    // Shoot (hold to auto-fire)
    if (keys & J_A) {
        if (player.shoot_cd == 0) {
            projectile_spawn_player();
            player.shoot_cd = 8;
            sound_shoot();
        }
    }

    // BG scroll (Sara stays fixed, world moves)
    level_update(keys);

    // Enemies
    level_check_spawns();

    // Update all
    projectile_update();
    enemy_update();

    // Sound state machine (drives multi-frame SFX)
    sound_update();

    // Player-enemy collision
    if (player.invuln == 0) {
        if (enemy_check_player_hit(player.x, player.y)) {
            player.hp--;
            player.invuln = 60;
            sound_player_hit();
            if (player.hp == 0) {
                game_state = STATE_DEAD;
            }
        }
    }

    prev_keys = keys;
}

static void game_draw(void) {
    player_draw();
    projectile_draw();
    enemy_draw();
}

void main(void) {
    if (_cpu == CGB_TYPE) {
        cpu_fast();
    }

    game_init();

    while (1) {
        wait_vbl_done();

        if (game_state == STATE_PLAYING) {
            game_update();
            game_draw();
        } else if (game_state == STATE_DEAD) {
            if (joypad() & J_START) {
                game_init();
            }
        }
    }
}
