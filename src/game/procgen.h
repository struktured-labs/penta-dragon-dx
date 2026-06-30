// On-cart procgen — Phase 7: per-room reroll. Phase 9+ adds room graphs.
#ifndef QUINTRA_GAME_PROCGEN_H
#define QUINTRA_GAME_PROCGEN_H

#include "core/types.h"

// Compute the per-room RNG seed from (run_seed, biome, room_counter).
// Must match the reference impl in quintra-procgen if/when we pin it.
u32 procgen_room_seed(u32 run_seed, u8 biome_id, u8 room_counter);

// Build the room_tilemap + spawn enemies for the current run_state.
// Uses run_state.entered_from to position the player near the opposite door.
void procgen_generate_current_room(void);

#endif
