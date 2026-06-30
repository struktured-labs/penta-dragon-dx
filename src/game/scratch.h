// SCRATCH screen — Phase 3 placeholder. Press B to return to TITLE.
// Will be removed once CLASS_SELECT lands in Phase 4.
#ifndef QUINTRA_GAME_SCRATCH_H
#define QUINTRA_GAME_SCRATCH_H

#include "core/types.h"
#include "game/screen.h"

void        scratch_enter(void);
void        scratch_exit(void);
screen_id_t scratch_tick(u8 keys, u8 pressed);
void        scratch_draw(void);

#endif
