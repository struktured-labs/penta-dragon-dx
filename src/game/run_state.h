// Run-level state — persists for the duration of one run (death wipes it).
#ifndef QUINTRA_GAME_RUN_STATE_H
#define QUINTRA_GAME_RUN_STATE_H

#include "core/types.h"

// Directions (door entry/exit)
enum {
    DIR_N = 0,
    DIR_E,
    DIR_S,
    DIR_W,
    DIR_NONE = 0xFF,
};

typedef struct {
    u8  biome_id;            // current biome
    u8  room_counter;        // number of rooms entered this run
    u32 run_seed;            // run-level seed (combined w/ room_counter for per-room RNG)
    u8  entered_from;        // DIR_* — which door the player just came through
    u16 run_timer;           // total ticks since run started (1/60 sec)
    u8  rooms_cleared;       // count of rooms where all enemies were defeated
} run_state_t;

extern run_state_t run_state;

void run_state_init(u32 seed);
void run_state_clear(void);

#endif
