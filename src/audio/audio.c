#include <gb/gb.h>

#include "audio/audio.h"

void audio_init(void) {
    NR52_REG = 0x80;   // sound on
    NR50_REG = 0x77;   // max master volume both channels
    NR51_REG = 0xFF;   // all channels to both outputs
}

void audio_tick(void) {
    // Phase 3 stub — no music engine yet
}

void sfx_play(u8 sfx_id) {
    sfx_id;
    // Phase 5+
}
