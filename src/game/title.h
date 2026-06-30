#ifndef QUINTRA_GAME_TITLE_H
#define QUINTRA_GAME_TITLE_H

#include "core/types.h"
#include "game/screen.h"

void        title_enter(void);
void        title_exit(void);
screen_id_t title_tick(u8 keys, u8 pressed);
void        title_draw(void);

#endif
