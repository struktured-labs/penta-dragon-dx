#ifndef QUINTRA_GAME_COMBAT_H
#define QUINTRA_GAME_COMBAT_H

#include "core/types.h"

// Frames to freeze the room loop for impact weight (set by combat, ticked
// down + honored by room_tick).
extern u8 g_hitstop;

// Called per-frame after entity updates. Resolves:
//   - player-projectile vs enemy
//   - enemy vs player (respects iframes)
//   - decrements player iframes / fire cooldown
// Returns 1 if player just died this frame (HP went to 0).
u8 combat_resolve(void);

#endif
