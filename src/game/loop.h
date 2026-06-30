#ifndef QUINTRA_GAME_LOOP_H
#define QUINTRA_GAME_LOOP_H

#include "core/types.h"
#include "game/screen.h"

extern screen_id_t loop_current_screen;
extern u16         loop_frame_counter;

void loop_init(screen_id_t start);
void loop_run(void);

#endif
