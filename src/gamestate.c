#include "gamestate.h"
#include "enemy.h"
#include "boss.h"
#include "player.h"
#include "level.h"
#include "palettes.h"
#include "sound.h"
#include "music.h"
#include <gb/cgb.h>

GameState game;
uint8_t game_stage;
uint8_t bonus_pending;
uint8_t stage_changed;

// Each stage: Normal → Advanced → Miniboss1 → Normal → Advanced → Miniboss2 →
//             Normal → Advanced → Stage Boss
// The stage boss changes per stage, minibosses repeat
static const uint8_t section_descs[] = {
    SECT_NORMAL, SECT_ADVANCED, SECT_BOSS_1,   // Gargoyle
    SECT_NORMAL, SECT_ADVANCED, SECT_BOSS_2,   // Spider
    SECT_NORMAL, SECT_ADVANCED, 0xFF,          // Stage boss (replaced at runtime)
};
#define NUM_SECTIONS 9
#define STAGE_BOSS_IDX 8  // Index of the stage boss in section_descs

// Stage boss mapping from FAQ:
// Stage 1=Shalamar, 2=Riff, 3=Crystal Dragon, 4=Cameo,
// 5=Ted, 6=Troop, 7=Faze, Final=Penta Dragon
static const uint8_t stage_boss_descs[] = {
    SECT_BOSS_3, SECT_BOSS_3, SECT_BOSS_3, SECT_BOSS_4,
    SECT_BOSS_4, SECT_BOSS_5, SECT_BOSS_5
};
static const uint8_t stage_boss_flags[] = {
    BOSS_SHALAMAR, BOSS_RIFF, BOSS_CRYSTAL, BOSS_CAMEO,
    BOSS_TED, BOSS_TROOP, BOSS_FAZE
};

// Room cycling (verified via 60-second dual-ROM comparison)
// OG rapidly alternates rooms 5 and 1 during gameplay
static const uint8_t sect0_rooms[] = { 5, 1 };
static const uint8_t sect1_rooms[] = { 5, 1, 5 };
// SCX offset per room (verified: room 5→SCX=12, room 3→SCX=8)
static const uint8_t room_scx[] = { 0, 8, 8, 8, 8, 12, 8, 8 }; // indexed by room number

// Enemy types per section
#define SPAWN_CD_NORMAL   60
#define SPAWN_CD_ADVANCED 40
static uint8_t spawn_timer;
static uint16_t scx_delay;    // Delay before room SCX applies (OG: ~180 frames)
static uint8_t scx_anim;      // Room transition scroll animation frames remaining
static uint8_t scx_target;    // Target SCX for animation

void gamestate_init(void) {
    game.room = 5; // First room (verified)
    game.section = 0;
    game.section_desc = section_descs[0];
    game.boss_flag = 0;
    game.gameplay_active = 1;
    game.stage_flag = 0;
    game.progress = 0;
    game.sara_form = 0;
    game.powerup = 0;
    game.hp = 255; // Original: 255 units max HP
    game.lives = 3;
    game.section_timer = 0;
    game.score = 0;
    scx_delay = 180;
    scx_anim = 0;
    scx_target = 12; // Room 5 SCX
    game.next_life_at = 5000;
    game_stage = 1;
    bonus_pending = 0;
    stage_changed = 0;
    spawn_timer = SPAWN_CD_NORMAL;
}

uint8_t gamestate_is_boss(void) {
    return (game.section_desc >= 0x30);
}

void gamestate_next_section(void) {
    uint8_t stage_idx;
    uint8_t boss_id;

    game.section++;

    // Check if we just beat the stage boss (section was the last one)
    if (game.section >= NUM_SECTIONS) {
        // Stage complete — advance to next stage
        game.section = 0;
        if (game_stage < MAX_STAGES) {
            // Bonus stage after odd stages (1, 3, 5)
            if (game_stage & 0x01) {
                bonus_pending = 1;
            }
            game_stage++;
            stage_changed = 1;
            gamestate_apply_stage_palette();
        } else if (game_stage == MAX_STAGES) {
            // All 5 stages cleared — Penta Dragon (true final boss)
            game_stage = MAX_STAGES + 1; // Stage 6 = Penta Dragon
            game.section = STAGE_BOSS_IDX;
        }
    }

    // Get section descriptor — override stage boss slot with current stage's boss
    if (game.section == STAGE_BOSS_IDX) {
        stage_idx = game_stage - 1;
        if (stage_idx >= MAX_STAGES) stage_idx = MAX_STAGES - 1;
        game.section_desc = stage_boss_descs[stage_idx];
    } else {
        game.section_desc = section_descs[game.section];
    }

    game.section_timer = 0;
    game.progress = 0;

    // Set boss flag and spawn boss
    if (game.section_desc == SECT_BOSS_1) {
        game.boss_flag = 1; // Gargoyle
        load_boss_palette(1);
        enemy_init();
        boss_spawn_gargoyle(120, 56);
        sound_boss_warning();
        music_sfx_ch1(30);
        music_sfx_ch4(20);
    } else if (game.section_desc == SECT_BOSS_2) {
        game.boss_flag = 2; // Spider
        load_boss_palette(2);
        enemy_init();
        boss_spawn_spider(120, 40);
        sound_boss_warning();
        music_sfx_ch1(30);
        music_sfx_ch4(20);
    } else if (game.section == STAGE_BOSS_IDX) {
        // Stage boss — type depends on current stage
        if (game_stage > MAX_STAGES) {
            // Penta Dragon — true final boss
            game.boss_flag = 9;
            // Use Angela's palette (white/silver) for Penta Dragon
            load_boss_palette(8);
            enemy_init();
            boss_spawn_penta(130, 48);
        } else {
            stage_idx = game_stage - 1;
            if (stage_idx >= MAX_STAGES) stage_idx = MAX_STAGES - 1;
            boss_id = stage_boss_flags[stage_idx];
            game.boss_flag = boss_id;
            load_boss_palette(boss_id);
            enemy_init();
            boss_spawn_crimson(130, 48);
            boss.hp = 35 + (game_stage - 1) * 10;
        }
    } else {
        game.boss_flag = 0;
        boss_init();
    }
}

// Stage-specific BG palette themes (palette 0 = floor, palette 6 = walls)
// Each stage shifts the dungeon colors for visual variety
uint8_t gamestate_in_transition(void) {
    return (scx_delay > 0) ? 1 : 0;
}

void gamestate_apply_stage_palette(void) {
    // Stage BG palette 0 (floor) color schemes:
    // Stage 1: Blue-white dungeon (default from palettes.h)
    // Stage 2: Green-teal cavern
    // Stage 3: Purple-dark void
    // Stage 4: Red-orange lava
    // Stage 5: Gold-white temple
    static const palette_color_t stage_floor[7][4] = {
        { 0x7FFF, 0x7E94, 0x3D4A, 0x0000 },  // 1: Blue-white dungeon
        { 0x7FFF, 0x03E0, 0x01A0, 0x0000 },  // 2: Green mountain/valley
        { 0x7FFF, 0x7C1F, 0x4C0F, 0x0000 },  // 3: Purple cave (6 parts!)
        { 0x7FFF, 0x00DF, 0x001F, 0x0000 },  // 4: Red-orange tower
        { 0x7FFF, 0x03FF, 0x02BF, 0x0000 },  // 5: Gold temple
        { 0x7FFF, 0x5AD6, 0x318C, 0x0000 },  // 6: Silver mirror maze
        { 0x7FFF, 0x4210, 0x2108, 0x0000 },  // 7: Dark final stage
    };
    static const palette_color_t stage_walls[7][4] = {
        { 0x6F7B, 0x4E73, 0x2D4A, 0x0000 },  // 1: Blue-gray
        { 0x4EC0, 0x2D80, 0x1440, 0x0000 },  // 2: Dark green
        { 0x5817, 0x3C0F, 0x1C07, 0x0000 },  // 3: Dark purple
        { 0x00BF, 0x005F, 0x001F, 0x0000 },  // 4: Dark red
        { 0x02DF, 0x019F, 0x005F, 0x0000 },  // 5: Dark gold
        { 0x4A52, 0x318C, 0x1CE7, 0x0000 },  // 6: Dark silver
        { 0x2108, 0x1084, 0x0842, 0x0000 },  // 7: Near-black
    };

    uint8_t idx = game_stage - 1;
    if (idx >= 7) idx = 6; // Penta Dragon uses Stage 7 palette

    set_bkg_palette(0, 1, stage_floor[idx]);
    set_bkg_palette(6, 1, stage_walls[idx]);
}

// Spawn enemies based on current section type
static void spawn_section_enemies(void) {
    uint8_t type;
    uint8_t y;

    if (enemy_count >= MAX_ENEMIES) return;
    if (gamestate_is_boss()) return; // Boss section — no regular spawns

    spawn_timer--;
    if (spawn_timer > 0) return;

    // Reset spawn timer — scales faster in later stages
    {
        uint8_t base_cd = (game.section_desc == SECT_ADVANCED) ?
                          SPAWN_CD_ADVANCED : SPAWN_CD_NORMAL;
        // Reduce by 10 per stage (min 30)
        uint8_t stage_reduction = (game_stage - 1) * 10;
        spawn_timer = (base_cd > stage_reduction + 30) ?
                      base_cd - stage_reduction : 30;
    }

    // Pick enemy type based on section
    y = 40 + (game.progress * 7) % 80; // Vary Y position

    if (game.section_desc == SECT_NORMAL) {
        // Normal: humanoids, orcs, soldiers in later stages
        switch (game.progress & 0x07) {
            case 0: case 1: case 4: type = ENEMY_HUMANOID; break;
            case 2: case 5:         type = ENEMY_ORC;      break;
            case 3:                 type = (game_stage >= 3) ? ENEMY_SOLDIER : ENEMY_HUMANOID; break;
            default:                type = ENEMY_HUMANOID; break;
        }
    } else {
        // Advanced: all types
        switch (game.progress & 0x07) {
            case 0:         type = ENEMY_HUMANOID; break;
            case 1:         type = ENEMY_ORC;      break;
            case 2:         type = ENEMY_HORNET;   break;
            case 3:         type = ENEMY_CROW;     break;
            case 4:         type = ENEMY_CATFISH;  break;
            case 5:         type = (game_stage >= 2) ? ENEMY_DRAGONFLY : ENEMY_HORNET; break;
            case 6:         type = (game_stage >= 4) ? ENEMY_SOLDIER : ENEMY_HUMANOID; break;
            default:        type = ENEMY_HUMANOID; break;
        }
    }

    // Spawn from varied positions matching OG density
    {
        uint8_t spawn_side = game.progress & 0x07;
        uint8_t sx, sy;
        if (spawn_side < 3) {
            // Right edge (most common)
            sx = 168;
            sy = y;
        } else if (spawn_side == 3) {
            // Top edge
            sx = 40 + (game.progress * 13) % 100;
            sy = 8;
        } else if (spawn_side == 4) {
            // Bottom edge
            sx = 40 + (game.progress * 17) % 100;
            sy = 120;
        } else if (spawn_side == 5) {
            // Right-upper
            sx = 168;
            sy = 20 + (game.progress * 11) % 40;
        } else {
            // Mid-screen right (closer to Sara)
            sx = 140;
            sy = 30 + (game.progress * 9) % 70;
        }
        enemy_spawn(type, sx, sy);
    }
    game.progress++;
}

void gamestate_update(void) {
    game.section_timer++;

    // Room cycling — SCX only changes on actual room transitions
    {
        uint8_t new_room = game.room;
        if (!gamestate_is_boss()) {
            uint16_t room_interval = 390; // OG: room 5 for ~390 frames then room 3
            uint8_t room_idx;
            if (game.section_desc == SECT_NORMAL) {
                // FFBD is OG's dual-buffer toggle (structural, not gameplay)
                // Set room based on section timer for SCX purposes only
                new_room = (game.section_timer < room_interval) ? 5 : 3;
            } else if (game.section_desc == SECT_ADVANCED) {
                room_interval = 90;
                room_idx = (uint8_t)((game.section_timer / room_interval) % 3);
                new_room = sect1_rooms[room_idx];
            }
        } else {
            new_room = 3;
        }
        // Update SCX when room changes
        if (new_room != game.room && scx_delay == 0 && new_room < 8) {
            // OG: room 5→3 triggers scroll animation (0→4→8→12 cycle, ~60 frames)
            scx_target = room_scx[new_room];
            scx_anim = 60;
        }
        game.room = new_room;
        // Delay 180 frames after gameplay starts before first SCX set
        if (scx_delay > 0) {
            scx_delay--;
            if (scx_delay == 0) {
                scroll_x = room_scx[game.room];
                SCX_REG = (uint8_t)scroll_x;
            }
        } else if (scx_anim > 0) {
            // Room transition scroll: cycle 0→4→8→12 ascending
            scx_anim--;
            scroll_x = (((60 - scx_anim) / 5) % 4) * 4;
            SCX_REG = (uint8_t)scroll_x;
            if (scx_anim == 0) {
                scroll_x = scx_target;
                SCX_REG = (uint8_t)scroll_x;
            }
        }
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

    // Mirror game state to HRAM (matches OG memory map for verifier)
    *((volatile uint8_t *)0xFFBD) = game.room;
    *((volatile uint8_t *)0xFFBE) = game.sara_form;
    *((volatile uint8_t *)0xFFBF) = game.boss_flag;
    *((volatile uint8_t *)0xFFC0) = game.powerup;
    *((volatile uint8_t *)0xFFC1) = game.gameplay_active;
    *((volatile uint8_t *)0xFFD0) = game.stage_flag;
}
