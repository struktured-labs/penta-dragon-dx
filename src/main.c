// Penta Dragon DX Remake - GBC Native
// Full color from the ground up

#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>

#include "types.h"
#include "palettes.h"
#include "player.h"
#include "projectile.h"
#include "enemy.h"
#include "level.h"

static uint8_t prev_keys;
static uint8_t game_state;

static void game_init(void) {
    // Turn off display during setup
    DISPLAY_OFF;

    // Load palettes
    init_palettes();

    // Load all tiles into VRAM
    level_load_tiles();
    player_load_tiles();
    projectile_load_tiles();
    enemy_load_tiles();

    // Initialize game systems
    player_init();
    projectile_init();
    enemy_init();
    level_init();

    prev_keys = 0;
    game_state = STATE_PLAYING;

    // Draw initial frame so sprites are visible immediately
    player_draw();
    projectile_draw();
    enemy_draw();

    // Enable background and sprites
    SHOW_BKG;
    SHOW_SPRITES;
    DISPLAY_ON;
}

static void game_update(void) {
    uint8_t keys = joypad();

    // Player input and update
    player_update(keys, prev_keys);

    // Shoot on A button (hold to auto-fire with cooldown)
    if (keys & J_A) {
        if (player.shoot_cd == 0) {
            projectile_spawn_player();
            player.shoot_cd = 8; // Auto-fire rate
        }
    }

    // Level scrolling
    level_update();

    // Spawn enemies based on scroll position
    level_check_spawns();

    // Update projectiles and enemies
    projectile_update();
    enemy_update();

    // Player-enemy collision
    if (player.invuln == 0) {
        if (enemy_check_player_hit(player.x, player.y)) {
            player.hp--;
            player.invuln = 60; // 1 second of invulnerability
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
    // Detect CGB hardware and enable double speed
    if (_cpu == CGB_TYPE) {
        cpu_fast();
    }

    game_init();

    // Main game loop
    while (1) {
        wait_vbl_done();

        if (game_state == STATE_PLAYING) {
            game_update();
            game_draw();
        } else if (game_state == STATE_DEAD) {
            // Simple restart on START
            if (joypad() & J_START) {
                game_init();
            }
        }
    }
}
