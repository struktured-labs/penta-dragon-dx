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
#include "music.h"
#include "gamestate.h"

static uint8_t prev_keys;

static void game_init(void) {
    DISPLAY_OFF;

    sound_init();
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
    gamestate_init();

    prev_keys = 0;

    // Draw initial frame
    player_draw();
    projectile_draw();
    enemy_draw();

    SHOW_BKG;
    SHOW_SPRITES;
    DISPLAY_ON;

    // Start music after display is on (needs sound hardware fully ready)
    music_init();
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
            music_sfx_ch1(15);  // yield Ch1 melody during shoot SFX
        }
    }

    // BG scroll (Sara stays fixed, world moves)
    level_update(keys);

    // Game progression (handles section cycling + enemy spawning)
    // NOTE: replaces old level_check_spawns() — do NOT call both
    gamestate_update();

    // Update all
    projectile_update();
    enemy_update();

    // Sound state machines
    sound_update();
    music_update();

    // Player-enemy collision
    if (player.invuln == 0) {
        if (enemy_check_player_hit(player.x, player.y)) {
            game.hp--;
            player.invuln = 60;
            sound_player_hit();
            music_sfx_ch1(60);  // yield Ch1 melody during damage SFX
            if (game.hp == 0) {
                game.lives--;
                if (game.lives == 0) {
                    game.gameplay_active = 0; // Game over
                } else {
                    // Respawn
                    game.hp = 10;
                    player_init();
                    enemy_init();
                    projectile_init();
                }
            }
        }
    }

    // Check if boss defeated (enemy_count == 0 during boss section)
    if (gamestate_is_boss() && enemy_count == 0 && game.section_timer > 60) {
        gamestate_next_section();
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

        if (game.gameplay_active) {
            game_update();
            game_draw();
        } else {
            // Game over — restart on START
            if (joypad() & J_START) {
                game_init();
            }
        }
    }
}
