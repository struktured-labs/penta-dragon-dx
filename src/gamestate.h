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
} GameState;

extern GameState game;

// Section descriptors from original
#define SECT_NORMAL     0x04  // Normal enemies (orcs + humanoids)
#define SECT_ADVANCED   0x22  // Harder enemies (adds hornets + crows)
#define SECT_BOSS_1     0x30  // Gargoyle miniboss
#define SECT_BOSS_2     0x35  // Spider miniboss
#define SECT_BOSS_3     0x3A  // Crimson (Stage 1 final boss)

// Section durations (frames, from extraction data)
#define SECT0_DURATION  5520  // Normal section
#define SECT1_DURATION  1860  // Advanced section
// Boss sections end when boss HP reaches 0

// Initialize game state for new game
void gamestate_init(void);

// Update section/room progression each frame
void gamestate_update(void);

// Advance to next section
void gamestate_next_section(void);

// Check if current section is a boss
uint8_t gamestate_is_boss(void);

#endif /* __GAMESTATE_H__ */
