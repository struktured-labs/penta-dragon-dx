#ifndef __TYPES_H__
#define __TYPES_H__

#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>

// Screen dimensions
#define SCREEN_W     160
#define SCREEN_H     144
#define TILE_SIZE    8

// OAM sprite offsets (hardware adds 8 to X, 16 to Y)
#define OAM_X_OFS    8
#define OAM_Y_OFS    16

// Sprite tile allocation in VRAM
// Each entity type gets a block of tiles
#define TILE_SARA_W      0   // 16 tiles (0-15) — 4 animation frames
#define TILE_SARA_D      16  // 16 tiles (16-31) — 4 animation frames
#define TILE_PROJECTILE  32  // 4 tiles (32-35)
#define TILE_HORNET      36  // 16 tiles (36-51)
#define TILE_CROW        52  // 16 tiles (52-67)
#define TILE_ORC         68  // 16 tiles (68-83)
#define TILE_HUMANOID    84  // 16 tiles (84-99)

// OAM slot allocation (40 total)
#define OAM_PLAYER       0   // 4 slots (0-3) for 16x16 Sara
#define OAM_PROJECTILES  4   // 8 slots (4-11) for up to 8 projectiles
#define OAM_ENEMIES      12  // 28 slots (12-39) for up to 7 enemies (4 each)

// Max counts
#define MAX_PROJECTILES  8
#define MAX_ENEMIES      6

// Direction
#define DIR_RIGHT  0
#define DIR_LEFT   1

// Game states
#define STATE_TITLE    0
#define STATE_PLAYING  1
#define STATE_BOSS     2
#define STATE_DEAD     3
#define STATE_VICTORY  4
#define STATE_BONUS    5

#endif /* __TYPES_H__ */
