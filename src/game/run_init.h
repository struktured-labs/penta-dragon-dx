#ifndef QUINTRA_GAME_RUN_INIT_H
#define QUINTRA_GAME_RUN_INIT_H

#include "core/types.h"
#include "game/screen.h"

void        run_init_enter(void);
void        run_init_exit(void);
screen_id_t run_init_tick(u8 keys, u8 pressed);
void        run_init_draw(void);

#endif
