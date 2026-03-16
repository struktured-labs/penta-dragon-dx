#include "gamestate.h"
#include "enemy.h"
#include "boss.h"
#include "player.h"
#include "palettes.h"

GameState game;

// Section sequence from original Level 1:
// DCB8=0: desc=0x04 (normal, orcs+humanoids)
// DCB8=1: desc=0x22 (advanced, adds hornets+crows)
// DCB8=2: desc=0x30 (Gargoyle miniboss)
// DCB8=3: desc=0x04 (normal again)
// DCB8=4: desc=0x22 (advanced again)
// DCB8=5: desc=0x35 (Spider miniboss)
// After Spider, one more normal+advanced cycle, then Crimson (Stage 1 final boss)
static const uint8_t section_descs[] = {
    SECT_NORMAL, SECT_ADVANCED, SECT_BOSS_1,
    SECT_NORMAL, SECT_ADVANCED, SECT_BOSS_2,
    SECT_NORMAL, SECT_ADVANCED, SECT_BOSS_3,
};
#define NUM_SECTIONS 9

// Room cycling per section (from extraction):
// Section 0: rooms {01, 05} alternating every ~150 frames
// Section 1: rooms {02, 03, 04} cycling
// Section 2+: room 03 (boss arena)
static const uint8_t sect0_rooms[] = { 1, 5 };
static const uint8_t sect1_rooms[] = { 2, 3, 4 };

// Enemy types per section
#define SPAWN_CD_NORMAL   90   // Frames between spawns in normal sections
#define SPAWN_CD_ADVANCED 60   // Faster spawning
static uint8_t spawn_timer;

void gamestate_init(void) {
    game.room = 1;
    game.section = 0;
    game.section_desc = section_descs[0];
    game.boss_flag = 0;
    game.gameplay_active = 1;
    game.stage_flag = 0;
    game.progress = 0;
    game.sara_form = 0;
    game.powerup = 0;
    game.hp = 10;
    game.lives = 3;
    game.section_timer = 0;
    spawn_timer = SPAWN_CD_NORMAL;
}

uint8_t gamestate_is_boss(void) {
    return (game.section_desc >= 0x30);
}

void gamestate_next_section(void) {
    game.section++;
    if (game.section >= NUM_SECTIONS) {
        game.section = 0; // Loop back (full dungeon cleared)
    }
    game.section_desc = section_descs[game.section];
    game.section_timer = 0;
    game.progress = 0;

    // Set boss flag and spawn boss
    if (game.section_desc == SECT_BOSS_1) {
        game.boss_flag = 1; // Gargoyle
        load_boss_palette(1);
        enemy_init();  // Clear regular enemies for boss OAM slots
        boss_spawn_gargoyle(120, 56);  // Spawn at right side of screen
    } else if (game.section_desc == SECT_BOSS_2) {
        game.boss_flag = 2; // Spider
        load_boss_palette(2);
        enemy_init();
        boss_spawn_spider(120, 40);
    } else if (game.section_desc == SECT_BOSS_3) {
        game.boss_flag = 3; // Crimson (Stage 1 final boss)
        load_boss_palette(3);
        enemy_init();
        boss_spawn_crimson(130, 48);
    } else {
        game.boss_flag = 0;
        boss_init();  // Clear boss when leaving boss section
    }
}

// Spawn enemies based on current section type
static void spawn_section_enemies(void) {
    uint8_t type;
    uint8_t y;

    if (enemy_count >= MAX_ENEMIES) return;
    if (gamestate_is_boss()) return; // Boss section — no regular spawns

    spawn_timer--;
    if (spawn_timer > 0) return;

    // Reset spawn timer based on section difficulty
    spawn_timer = (game.section_desc == SECT_ADVANCED) ?
                  SPAWN_CD_ADVANCED : SPAWN_CD_NORMAL;

    // Pick enemy type based on section
    y = 40 + (game.progress * 7) % 80; // Vary Y position

    if (game.section_desc == SECT_NORMAL) {
        // Section 0: only humanoids and orcs
        type = (game.progress & 0x03) < 3 ? ENEMY_HUMANOID : ENEMY_ORC;
    } else {
        // Section 1: mix all types
        switch (game.progress & 0x07) {
            case 0: case 1: case 4: type = ENEMY_HUMANOID; break;
            case 2: case 5:         type = ENEMY_ORC;      break;
            case 3:                 type = ENEMY_HORNET;   break;
            case 6:                 type = ENEMY_CROW;     break;
            default:                type = ENEMY_HUMANOID; break;
        }
    }

    enemy_spawn(type, 168, y);
    game.progress++;
}

void gamestate_update(void) {
    game.section_timer++;

    // Room cycling
    if (!gamestate_is_boss()) {
        uint16_t room_interval = 150;
        uint8_t room_idx;

        if (game.section_desc == SECT_NORMAL) {
            room_idx = (uint8_t)((game.section_timer / room_interval) % 2);
            game.room = sect0_rooms[room_idx];
        } else if (game.section_desc == SECT_ADVANCED) {
            room_interval = 90;
            room_idx = (uint8_t)((game.section_timer / room_interval) % 3);
            game.room = sect1_rooms[room_idx];
        }
    } else {
        game.room = 3; // Boss arena
    }

    // Section advancement (non-boss: timer-based)
    if (!gamestate_is_boss()) {
        uint16_t duration = (game.section_desc == SECT_NORMAL) ?
                            SECT0_DURATION : SECT1_DURATION;
        if (game.section_timer >= duration) {
            gamestate_next_section();
        }
    }
    // Boss sections advance when boss HP reaches 0 (checked by enemy system)

    // Enemy spawning
    spawn_section_enemies();

    // Sync powerup state with player
    game.powerup = player.powerup;
    game.sara_form = player.form;
}
