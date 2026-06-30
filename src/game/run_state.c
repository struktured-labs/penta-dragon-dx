#include "core/types.h"
#include "game/run_state.h"

run_state_t run_state;

void run_state_clear(void) {
    run_state.biome_id      = 0;
    run_state.room_counter  = 0;
    run_state.run_seed      = 0xCAFE1234UL;
    run_state.entered_from  = DIR_NONE;
    run_state.run_timer     = 0;
    run_state.rooms_cleared = 0;
}

void run_state_init(u32 seed) {
    run_state_clear();
    run_state.run_seed = (seed == 0UL) ? 0xCAFE1234UL : seed;
    run_state.biome_id = 0;     // Phase 7: only one biome — Crystal Caverns
}
