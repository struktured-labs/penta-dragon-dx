// Penta Dragon DX Remake - GBC Native
// Full color from the ground up

#include <gb/gb.h>
#include <gb/cgb.h>

#include "types.h"
#include "palettes.h"
#include "player.h"
#include "projectile.h"
#include "enemy.h"
#include "boss.h"
#include "level.h"
#include "sound.h"
#include "music.h"
#include "gamestate.h"
#include "hud.h"
#include "title.h"
#include "itemmenu.h"
#include "bonus.h"

static uint8_t prev_keys;
static uint8_t game_state;  // STATE_TITLE, STATE_PLAYING, STATE_DEAD
static uint8_t game_over_shown;

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
    boss_init();
    level_init();
    gamestate_init();

    prev_keys = 0;

    // Initialize HUD and items
    hud_init();
    itemmenu_init();

    // Draw initial frame
    player_draw();
    projectile_draw();
    enemy_draw();
    boss_draw();

    SHOW_BKG;
    SHOW_SPRITES;
    DISPLAY_ON;

    // Start music after display is on (needs sound hardware fully ready)
    music_init();

    game_state = STATE_PLAYING;
    game_over_shown = 0;
}

static void game_update(void) {
    uint8_t keys = joypad();
    uint8_t was_hit;
    uint8_t hit_result;
    uint8_t pi;

    // Item menu (START to open/close, handled first)
    if (menu_open) {
        itemmenu_update(keys, prev_keys);
        prev_keys = keys;
        return; // Menu absorbs all input
    }

    // SELECT opens item menu (matches original — SELECT=status/items)
    if ((keys & J_SELECT) && !(prev_keys & J_SELECT)) {
        itemmenu_open();
        itemmenu_draw();
        prev_keys = keys;
        return;
    }

    // B uses flash bomb directly (edge-triggered, no menu needed)
    if ((keys & J_B) && !(prev_keys & J_B)) {
        itemmenu_use_flash_bomb();
    }

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

    // Check for item pickups (Sara overlapping item tiles in BG)
    level_check_item_pickup();

    // Game progression (handles section cycling + enemy spawning)
    // NOTE: replaces old level_check_spawns() -- do NOT call both
    gamestate_update();

    // Update all
    projectile_update();
    enemy_update();
    boss_update();

    // Sound state machines
    sound_update();
    music_update();

    // HUD update
    hud_update();

    // Player-enemy collision (regular enemies)
    if (player.invuln == 0) {
        was_hit = 0;

        if (enemy_check_player_hit(player.x, player.y)) {
            was_hit = 1;
        }
        // Player-boss collision
        if (!was_hit && boss_check_player_hit(player.x, player.y)) {
            was_hit = 1;
        }

        if (was_hit) {
            if (game.hp > 0) game.hp--;
            player.invuln = 60;
            sound_player_hit();
            music_sfx_ch1(60);
            music_sfx_ch4(15);
            if (game.hp == 0) {
                if (game.lives > 0) game.lives--;
                if (game.lives == 0) {
                    game.gameplay_active = 0; // Game over
                    game_state = STATE_DEAD;
                } else {
                    // Respawn
                    game.hp = 255;
                    player_init();
                    enemy_init();
                    boss_init();
                    projectile_init();
                }
            }
        }
    }

    // Projectile-boss collision: check if player shots hit the boss
    if (boss.type != BOSS_NONE) {
        hit_result = 0;
        for (pi = 0; pi < MAX_PROJECTILES; pi++) {
            if (projectiles[pi].active == 1) {  // Player shot only
                hit_result = boss_check_hit(projectiles[pi].x, projectiles[pi].y);
                if (hit_result) {
                    projectiles[pi].active = 0;  // Consume the projectile
                    if (hit_result == 2) {
                        // Boss killed
                        if (game_stage > MAX_STAGES && boss.type == BOSS_PENTA) {
                            // Penta Dragon defeated — victory!
                            game_state = STATE_VICTORY;
                            music_pause();
                            break;
                        }
                        gamestate_next_section();
                        // Check if bonus stage should trigger
                        if (bonus_pending) {
                            bonus_pending = 0;
                            bonus_init();
                            game_state = STATE_BONUS;
                        }
                        break;
                    }
                }
            }
        }
    }

    // Check if boss defeated (fallback: enemy_count == 0 during boss section with no boss entity)
    if (gamestate_is_boss() && boss.type == BOSS_NONE && game.section_timer > 60) {
        gamestate_next_section();
    }

    prev_keys = keys;
}

static void game_draw(void) {
    player_draw();
    projectile_draw();
    enemy_draw();
    boss_draw();
}

void main(void) {
    if (_cpu == CGB_TYPE) {
        cpu_fast();
    }

    sound_init();
    init_palettes();

    // Start with title screen
    title_init();
    game_state = STATE_TITLE;
    game_over_shown = 0;

    while (1) {
        wait_vbl_done();

        switch (game_state) {
            case STATE_TITLE:
                if (title_update()) {
                    title_cleanup();
                    game_init();
                }
                break;

            case STATE_PLAYING:
                game_update();
                game_draw();
                break;

            case STATE_DEAD:
                if (!game_over_shown) {
                    hud_game_over();
                    music_pause();
                    game_over_shown = 1;
                }
                if (joypad() & J_START) {
                    game_over_shown = 0;
                    title_init();
                    game_state = STATE_TITLE;
                }
                break;

            case STATE_BONUS:
                // Bonus stage (jet form corridor)
                if (bonus_update(joypad())) {
                    // Bonus complete — return to normal gameplay
                    bonus_cleanup();
                    DISPLAY_OFF;
                    level_load_tiles();
                    level_init();
                    DISPLAY_ON;
                    game_state = STATE_PLAYING;
                }
                bonus_draw();
                break;

            case STATE_VICTORY:
                if (!game_over_shown) {
                    hud_game_over();
                    sound_pickup();
                    game_over_shown = 1;
                }
                if (joypad() & J_START) {
                    game_over_shown = 0;
                    title_init();
                    game_state = STATE_TITLE;
                }
                break;
        }
    }
}
