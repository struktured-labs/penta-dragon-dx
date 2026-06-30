// RUN_INIT — initializes run-level state from current entropy + player class
// then immediately transitions to ROOM.

#include "core/types.h"
#include "core/rng.h"
#include "game/loop.h"
#include "game/run_init.h"
#include "game/run_state.h"

void run_init_enter(void) {
    u32 seed = (u32)loop_frame_counter ^ 0xA5A5A5A5UL;
    rng_seed(seed);
    run_state_init(seed ^ 0xDEADBEEFUL);
}

void run_init_exit(void) {}

screen_id_t run_init_tick(u8 keys, u8 pressed) {
    keys; pressed;
    return SCREEN_ROOM;
}

void run_init_draw(void) {}
