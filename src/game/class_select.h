#ifndef QUINTRA_GAME_CLASS_SELECT_H
#define QUINTRA_GAME_CLASS_SELECT_H

#include "core/types.h"
#include "game/screen.h"

extern u8 class_select_cursor;   // 0..N_CLASSES-1

void        class_select_enter(void);
void        class_select_exit(void);
screen_id_t class_select_tick(u8 keys, u8 pressed);
void        class_select_draw(void);

#endif
