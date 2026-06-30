// Screen state machine interface.
#ifndef QUINTRA_GAME_SCREEN_H
#define QUINTRA_GAME_SCREEN_H

#include "core/types.h"

// Screen IDs. screens[SCREEN_*] indexes into the screens table.
enum {
    SCREEN_BOOT = 0,
    SCREEN_TITLE,
    SCREEN_CLASS_SELECT,    // Phase 4
    SCREEN_RUN_INIT,        // Phase 4
    SCREEN_PROCGEN,
    SCREEN_ROOM,
    SCREEN_REST_ROOM,
    SCREEN_BOSS,
    SCREEN_INVENTORY,
    SCREEN_DIALOG,
    SCREEN_GAMEOVER,
    SCREEN_VICTORY,
    SCREEN_SCRATCH,          // Phase 3: placeholder destination after TITLE
    SCREEN_COUNT,
};

#define SCREEN_SELF 0xFF      // tick() returns this to stay on current screen

typedef u8 screen_id_t;
typedef screen_id_t (*screen_tick_fn)(u8 keys, u8 pressed);
typedef void (*screen_void_fn)(void);

typedef struct {
    screen_void_fn   enter;
    screen_void_fn   exit;
    screen_tick_fn   tick;
    screen_void_fn   draw;
} screen_t;

extern const screen_t screens[SCREEN_COUNT];

#endif
