#include <gb/gb.h>

#include "input/input.h"

u8 input_keys     = 0;
u8 input_prev     = 0;
u8 input_pressed  = 0;
u8 input_released = 0;

void input_init(void) {
    input_keys = input_prev = input_pressed = input_released = 0;
}

void input_poll(void) {
    input_prev    = input_keys;
    input_keys    = joypad();
    input_pressed  = input_keys & ~input_prev;
    input_released = input_prev & ~input_keys;
}
