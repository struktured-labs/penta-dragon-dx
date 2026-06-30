// Quintra — top-down GBC roguelike.
// Phase 3 boot: init engine subsystems, hand control to the screen FSM
// starting at TITLE.

#include <gb/gb.h>
#include <gb/cgb.h>

#include "core/types.h"
#include "core/rng.h"
#include "input/input.h"
#include "audio/audio.h"
#include "game/loop.h"
#include "game/screen.h"
#include "content.h"

// Sanity refs — keeps SDCC from dead-stripping the generated tables
// and lets a memory inspector confirm the content reached the ROM.
const u8 quintra_n_classes = N_CLASSES;
const u8 quintra_n_items   = N_ITEMS;
const u8 quintra_n_enemies = N_ENEMIES;
const u8 quintra_n_biomes  = N_BIOMES;
const u8 quintra_n_rooms   = N_ROOM_TEMPLATES;

void main(void) {
    DISPLAY_OFF;

    // Engine subsystems
    input_init();
    audio_init();
    rng_seed(0xC0DEBABEUL);

    loop_init(SCREEN_TITLE);
    loop_run();
    // unreachable
}
