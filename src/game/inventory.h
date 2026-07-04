#ifndef QUINTRA_GAME_INVENTORY_H
#define QUINTRA_GAME_INVENTORY_H

#include "core/types.h"
#include "game/screen.h"

void        inventory_enter(void);
void        inventory_exit(void);
screen_id_t inventory_tick(u8 keys, u8 pressed);
void        inventory_draw(void);

#endif
