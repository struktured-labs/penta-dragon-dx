// Joypad input with edge detection.
#ifndef QUINTRA_INPUT_H
#define QUINTRA_INPUT_H

#include "core/types.h"

// GBDK joypad() returns: J_A J_B J_SELECT J_START J_UP J_DOWN J_LEFT J_RIGHT

extern u8 input_keys;       // current frame
extern u8 input_prev;       // last frame
extern u8 input_pressed;    // edge: pressed this frame
extern u8 input_released;   // edge: released this frame

void input_init(void);
void input_poll(void);      // call once per frame

#endif
