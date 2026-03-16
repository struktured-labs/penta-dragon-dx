#ifndef __BOSS_H__
#define __BOSS_H__

#include "types.h"

// Boss types
// Boss IDs match FFBF values from original ROM
#define BOSS_NONE       0
#define BOSS_MINIBOSS_1 1   // Unnamed mini-boss (scorpion-like, appears during stages)
#define BOSS_MINIBOSS_2 2   // Unnamed mini-boss (spider-like, appears during stages)
#define BOSS_SHALAMAR   3   // Boss 1: Shalamar — scorpion, weak at head
#define BOSS_RIFF       4   // Boss 2: Riff — ugly, black ball projectiles
#define BOSS_CRYSTAL    5   // Boss 3: Crystal Dragon — warps via holes
#define BOSS_CAMEO      6   // Boss 4: Cameo — chameleon, turns invisible
#define BOSS_TED        7   // Boss 5: Ted — Mother Brain-like, vines
#define BOSS_TROOP      8   // Boss 6: Troop — fireballs + homing missiles
// FFBF doesn't go higher — Faze and Penta Dragon use different mechanisms
#define BOSS_FAZE       9   // Boss 7: Faze — fills screen
#define BOSS_PENTA      10  // Boss 8: Penta Dragon — five-headed final boss

// Boss OAM allocation: during boss sections, regular enemies are cleared
// and the boss uses OAM slots 12-27 (16 slots for 4x4 sprite grid).
// Projectile slots from the boss use regular projectile system (slots 4-11).
#define OAM_BOSS        OAM_ENEMIES   // 12
#define BOSS_OAM_SLOTS  16            // 4x4 grid

// Boss HP values
#define BOSS_MINIBOSS_HP  20   // Mini-bosses
#define BOSS_SHALAMAR_HP  30   // Stage 1 boss
#define BOSS_RIFF_HP      35   // Stage 2 boss
#define BOSS_CRYSTAL_HP   35   // Stage 3 boss
#define BOSS_CAMEO_HP     40   // Stage 4 boss
#define BOSS_TED_HP       45   // Stage 5 boss
#define BOSS_TROOP_HP     50   // Stage 6 boss
#define BOSS_FAZE_HP      60   // Stage 7 boss
#define BOSS_PENTA_HP     120  // Final boss — five-headed dragon

// Boss attack cooldown (frames)
#define BOSS_SHOOT_CD     90

// Boss animation speed
#define BOSS_ANIM_SPEED   16

typedef struct {
    uint8_t  type;          // BOSS_NONE, BOSS_GARGOYLE, etc.
    uint8_t  x;             // Screen X position (left edge of 32x32 sprite)
    uint8_t  y;             // Screen Y position (top edge of 32x32 sprite)
    uint8_t  hp;            // Hit points remaining
    int8_t   dx;            // Current X velocity
    int8_t   dy;            // Current Y velocity
    uint8_t  ai_state;      // AI state machine
    uint16_t ai_timer;      // AI timer (frames)
    uint8_t  attack_cd;     // Attack cooldown
    uint8_t  frame;         // Animation frame (0-1)
    uint8_t  anim_tick;     // Animation counter
    uint8_t  palette;       // CGB palette slot
    uint8_t  tile_base;     // VRAM tile base for this boss
} Boss;

extern Boss boss;

// Initialize boss system (clear boss state)
void boss_init(void);

// Spawn the gargoyle miniboss at the given position
void boss_spawn_gargoyle(uint8_t x, uint8_t y);

// Spawn the spider miniboss at the given position
void boss_spawn_spider(uint8_t x, uint8_t y);

// Spawn the Crimson boss (Stage 1 final boss)
void boss_spawn_crimson(uint8_t x, uint8_t y);

// Spawn Penta Dragon (true final boss — multi-phase)
void boss_spawn_penta(uint8_t x, uint8_t y);

// Update boss AI, movement, and attacks (call once per frame)
void boss_update(void);

// Draw boss sprites to OAM (call once per frame)
void boss_draw(void);

// Check if a projectile hit the boss (AABB test).
// Returns 1 if boss was hit and still alive, 2 if boss was killed.
uint8_t boss_check_hit(uint8_t px, uint8_t py);

// Check if boss collides with player position
uint8_t boss_check_player_hit(uint8_t px, uint8_t py);

#endif /* __BOSS_H__ */
