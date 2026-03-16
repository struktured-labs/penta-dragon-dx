#include "bonus.h"
#include "player.h"
#include "enemy.h"
#include "projectile.h"
#include "sound.h"
#include "music.h"
#include "palettes.h"
#include "gamestate.h"
#include <gb/gb.h>
#include <gb/cgb.h>

uint8_t bonus_active;
uint16_t bonus_timer;

// Bonus stage duration: ~20 seconds (1200 frames)
#define BONUS_DURATION   1200
#define BONUS_SPAWN_CD   40   // Enemy spawn rate (faster than normal)

static uint8_t spawn_cd;

// Bonus BG palette: dark blue space theme
static const palette_color_t bonus_bg_pal[4] = {
    0x0000, 0x1C08, 0x3810, 0x5418  // Black to deep blue gradient
};

void bonus_init(void) {
    bonus_active = 1;
    bonus_timer = 0;
    spawn_cd = BONUS_SPAWN_CD;

    // Set stage flag
    game.stage_flag = 1;

    // Clear entities
    enemy_init();
    projectile_init();

    // Apply bonus stage BG palette (dark space theme)
    set_bkg_palette(0, 1, bonus_bg_pal);

    // Set void tiles for the bonus corridor (columns of FE with open center)
    // The existing level tiles have 0xFE as void — fill most of the BG with it
    // and leave a corridor in the middle
    {
        uint8_t col, row;
        uint8_t tile;
        uint8_t pal;

        for (col = 0; col < 20; col++) {
            for (row = 0; row < 18; row++) {
                // Left wall (cols 0-2), right wall (cols 17-19), open middle
                if (col < 3 || col > 16) {
                    tile = 0x16; // Wall border tile
                    pal = 6;
                } else {
                    tile = 0x00; // Empty/void
                    pal = 0;
                }
                set_bkg_tiles(col, row, 1, 1, &tile);
                VBK_REG = 1;
                set_bkg_tiles(col, row, 1, 1, &pal);
                VBK_REG = 0;
            }
        }
    }

    // Reset scroll for bonus stage (static, no horizontal scroll)
    SCX_REG = 0;
    SCY_REG = 0;
}

uint8_t bonus_update(uint8_t keys) {
    bonus_timer++;

    // Player moves freely in bonus stage (not fixed position)
    // Use UP/DOWN/LEFT/RIGHT for full movement
    if (keys & J_LEFT)  { if (player.x > 28) player.x -= 2; }
    if (keys & J_RIGHT) { if (player.x < 132) player.x += 2; }
    if (keys & J_UP)    { if (player.y > 16) player.y -= 2; }
    if (keys & J_DOWN)  { if (player.y < 120) player.y += 2; }

    // Auto-fire upward in jet mode
    if (keys & J_A) {
        if (player.shoot_cd == 0) {
            // Shoot upward (jet form fires up, not forward)
            projectile_spawn_enemy(player.x + 4, player.y, 0, -4);
            // Reuse enemy projectile spawn but mark as player shot
            // Actually, let's use the regular spawn
            projectile_spawn_player();
            player.shoot_cd = 6;
            sound_shoot();
            music_sfx_ch1(10);
        }
    }

    // Spawn enemies from the top (descending)
    spawn_cd--;
    if (spawn_cd == 0) {
        spawn_cd = BONUS_SPAWN_CD;

        // Spawn at random X position, top of screen
        uint8_t x = 40 + (bonus_timer * 7) % 80;
        uint8_t type;

        // Mix of enemy types descending
        switch ((bonus_timer / BONUS_SPAWN_CD) & 0x03) {
            case 0: type = ENEMY_HORNET; break;
            case 1: type = ENEMY_CROW; break;
            case 2: type = ENEMY_HUMANOID; break;
            default: type = ENEMY_HORNET; break;
        }

        // Spawn at top, moving downward
        if (enemy_count < MAX_ENEMIES) {
            enemy_spawn(type, x, 8);
            // Override velocity to move downward (bonus stage enemies descend)
            enemies[enemy_count > 0 ? enemy_count - 1 : 0].dx = 0;
            enemies[enemy_count > 0 ? enemy_count - 1 : 0].dy = 1;
        }
    }

    // Update subsystems
    projectile_update();
    enemy_update();
    sound_update();
    music_update();

    // Check completion
    if (bonus_timer >= BONUS_DURATION) {
        return 1; // Bonus complete
    }
    return 0;
}

void bonus_draw(void) {
    player_draw();
    projectile_draw();
    enemy_draw();
}

void bonus_cleanup(void) {
    bonus_active = 0;
    game.stage_flag = 0;

    // Restore normal BG palette
    init_palettes();
    gamestate_apply_stage_palette();

    // Restore player position
    player.x = 72;
    player.y = 64;
}
