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
static uint8_t game_state;
static uint8_t game_over_shown;
static uint8_t intro_timer;
static uint8_t shake_timer;  // Screen shake frames remaining

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

    // START opens item menu
    if ((keys & J_START) && !(prev_keys & J_START)) {
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
            // Spiral powerup: extra diagonal shots
            if (player.powerup == 1) {
                projectile_spawn_player_dir(
                    (player.dir == DIR_RIGHT) ? PROJ_SPEED : -PROJ_SPEED, -2);
                projectile_spawn_player_dir(
                    (player.dir == DIR_RIGHT) ? PROJ_SPEED : -PROJ_SPEED, 2);
            }
            // Shoot cooldown: Dragon form faster, Turbo powerup fastest
            if (player.powerup == 3) {
                player.shoot_cd = 4;
            } else if (player.form == 1) {
                player.shoot_cd = 6; // Dragon: faster fire rate
            } else {
                player.shoot_cd = 8; // Witch: standard
            }
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

    // Extra life every 5000 points
    if (game.score >= game.next_life_at) {
        game.lives++;
        game.next_life_at += 5000;
        sound_pickup();
    }

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
        // Player-projectile collision (enemy shots)
        if (!was_hit) {
            for (pi = 0; pi < MAX_PROJECTILES; pi++) {
                if (projectiles[pi].active == 2) {
                    if (projectiles[pi].x + 4 > player.x &&
                        projectiles[pi].x < player.x + 12 &&
                        projectiles[pi].y + 4 > player.y &&
                        projectiles[pi].y < player.y + 12) {
                        projectiles[pi].active = 0;
                        was_hit = 1;
                        break;
                    }
                }
            }
        }

        if (was_hit) {
            {
                // Damage scales with stage (1 in stage 1, up to 4 in stage 7)
                uint8_t dmg = 1 + (game_stage - 1) / 2;
                if (game.hp > dmg) game.hp -= dmg;
                else game.hp = 0;
            }
            player.invuln = 60;
            shake_timer = 8;  // Screen shake on hit
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
                    player.invuln = 120; // 2 seconds respawn protection
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
                        // Boss killed — score bonus + item reward
                        game.score += 100 + game_stage * 50;
                        itemmenu_add_item(ITEM_POTION);
                        if (game_stage >= 3) {
                            itemmenu_add_item(ITEM_SHIELD);
                        }
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
                        } else if (stage_changed) {
                            // Stage advanced — show stage intro
                            stage_changed = 0;
                            hud_stage_intro(game_stage);
                            intro_timer = 120;
                            game_state = STATE_STAGE_INTRO;
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

    // Screen shake effect
    if (shake_timer > 0) {
        shake_timer--;
        SCY_REG += (shake_timer & 0x01) ? 2 : -2;
    }
}

void main(void) {
    if (_cpu == CGB_TYPE) {
        cpu_fast();
    }

    sound_init();
    init_palettes();

    // Start music on title screen (matches original)
    music_init();

    // Start with title screen
    title_init();
    game_state = STATE_TITLE;
    game_over_shown = 0;

    while (1) {
        wait_vbl_done();

        // Music runs in all states
        music_update();
        sound_update();

        switch (game_state) {
            case STATE_TITLE:
                {
                    uint8_t title_result = title_update();
                    if (title_result >= 1) {
                        title_cleanup();
                        game_init();
                        hud_stage_intro(game_stage);
                        intro_timer = 180;
                        game_state = STATE_STAGE_INTRO;
                    }
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
                    // Bonus complete — show stage intro then gameplay
                    bonus_cleanup();
                    hud_stage_intro(game_stage);
                    intro_timer = 120;
                    game_state = STATE_STAGE_INTRO;
                }
                bonus_draw();
                break;

            case STATE_STAGE_INTRO:
                intro_timer--;
                // Skip on A or START press
                if (intro_timer > 10 && (joypad() & (J_A | J_START))) {
                    intro_timer = 1;
                }
                if (intro_timer == 0) {
                    hud_stage_intro_cleanup();
                    if (game.gameplay_active) {
                        // Returning from bonus/stage change — reload tiles
                        DISPLAY_OFF;
                        level_load_tiles();
                        player_load_tiles();
                        projectile_load_tiles();
                        enemy_load_tiles();
                        level_init();
                        hud_init();
                        player_draw();
                        SHOW_BKG;
                        SHOW_SPRITES;
                        DISPLAY_ON;
                        game_state = STATE_PLAYING;
                    } else {
                        // First game start
                        game_init();
                    }
                }
                break;

            case STATE_VICTORY:
                if (!game_over_shown) {
                    hud_victory();
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
