// RUN_INIT — short transition screen. Picks a run seed, sets initial biome,
// transitions to ROOM. Phase 4: trivial pass-through.

#include "core/types.h"
#include "core/rng.h"
#include "game/run_init.h"
#include "game/loop.h"

void run_init_enter(void) {
    // Seed the per-run RNG with current frame counter for variety.
    // Real implementation will mix in joypad input timing for entropy.
    rng_seed((u32)loop_frame_counter ^ 0xA5A5A5A5UL);
}

void run_init_exit(void) {}

screen_id_t run_init_tick(u8 keys, u8 pressed) {
    keys; pressed;
    return SCREEN_ROOM;   // immediate transition
}

void run_init_draw(void) {}
