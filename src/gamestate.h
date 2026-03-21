#ifndef __GAMESTATE_H__
#define __GAMESTATE_H__

#include "types.h"

// Game progression state (mirrors original's memory map)
typedef struct {
    uint8_t room;           // Current room (FFBD: 1-7)
    uint8_t section;        // Section cycle (DCB8: 0-5)
    uint8_t section_desc;   // Section descriptor (DC04)
    uint8_t boss_flag;      // Boss active (FFBF: 0=none, 1-8=boss)
    uint8_t gameplay_active;// FFC1: 0=menu, 1=playing
    uint8_t stage_flag;     // FFD0: 0=normal, 1=bonus
    uint8_t progress;       // FFD6: progress counter
    uint8_t sara_form;      // FFBE: 0=Witch, 1=Dragon
    uint8_t powerup;        // FFC0: 0=none, 1=spiral, 2=shield, 3=turbo
    uint8_t hp;             // Health points
    uint8_t lives;          // Remaining lives
    uint16_t section_timer; // Frames in current section
    uint16_t score;         // Player score
    uint16_t next_life_at;  // Score threshold for next extra life
} GameState;

extern GameState game;

// Section descriptors from original
#define SECT_NORMAL     0x04  // Normal enemies (orcs + humanoids)
#define SECT_ADVANCED   0x22  // Harder enemies (adds hornets + crows)
#define SECT_BOSS_1     0x30  // Gargoyle miniboss
#define SECT_BOSS_2     0x35  // Spider miniboss
#define SECT_BOSS_3     0x3A  // Crimson (Stage 1 final boss)
#define SECT_BOSS_4     0x3F  // Ice (Stage 2 final boss)
#define SECT_BOSS_5     0x44  // Void (Stage 3 final boss)

// Current stage (1-7, 8=Penta Dragon final)
#define MAX_STAGES 7
extern uint8_t game_stage;

// Apply BG palette theme for current stage
void gamestate_apply_stage_palette(void);

// Returns 1 if in the gameplay startup transition (OG hides sprites for 180 frames)
uint8_t gamestate_in_transition(void);

// Set by gamestate when a bonus stage should trigger (checked by main.c)
extern uint8_t bonus_pending;

// Set when stage number changes (checked by main.c for stage intro screen)
extern uint8_t stage_changed;

// Section durations (game ticks, ~15 Hz = every 4th VBlank)
#define SECT0_DURATION  1380  // Normal section (5520 frames / 4)
#define SECT1_DURATION   465  // Advanced section (1860 frames / 4)
// Boss sections end when boss HP reaches 0

// Initialize game state for new game
void gamestate_init(void);

// Update section/room progression each frame
void gamestate_update(uint8_t keys);

// Advance to next section
void gamestate_next_section(void);

// Check if current section is a boss
uint8_t gamestate_is_boss(void);

#endif /* __GAMESTATE_H__ */
